from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal, cast

from coding_pet.daemon.session_registry import SessionRegistry
from coding_pet.logging import ContextAdapter, get_logger
from coding_pet.models import (
    ActionOutcome,
    AttentionState,
    attention_priority,
    normalize_action_result_message,
)

ActionResult = dict[str, object]
SupportedAction = Literal[
    "send_reply",
    "send_without_enter",
    "approve",
    "reject",
    "attach",
    "mark_read",
    "hide_pet",
    "manual_state_override",
]
DispatchAction = Callable[["SessionActionRequest"], Awaitable[ActionResult]]
LiveSessionLookup = Callable[[str], bool]

_SUPPORTED_ACTIONS = frozenset(
    {
        "send_reply",
        "send_without_enter",
        "approve",
        "reject",
        "attach",
        "mark_read",
        "hide_pet",
        "manual_state_override",
    }
)


def failure_result(
    *,
    session_id: str,
    action: str,
    reason: str,
    detail: str,
) -> ActionResult:
    return normalize_action_result_message(
        {
            "type": "action_result",
            "session_id": session_id,
            "action": action,
            "ok": False,
            "reason": reason,
            "detail": detail,
        }
    )


def local_success_result(
    *,
    session_id: str,
    action: str,
    reason: str,
    detail: str,
) -> ActionResult:
    return normalize_action_result_message(
        {
            "type": "action_result",
            "session_id": session_id,
            "action": action,
            "outcome": ActionOutcome.LOCAL_UPDATED.value,
            "reason": reason,
            "detail": detail,
        }
    )


@dataclass(frozen=True, slots=True)
class SessionActionRequest:
    session_id: str
    action: SupportedAction
    reply_text: str | None = None
    press_enter: bool = True
    state_override: AttentionState | None = None

    @classmethod
    def from_message(cls, message: dict[str, object]) -> SessionActionRequest:
        session_id = message.get("session_id")
        if not isinstance(session_id, str) or not session_id.strip():
            raise ValueError("session_id is required")

        action = message.get("action")
        if not isinstance(action, str) or action not in _SUPPORTED_ACTIONS:
            raise ValueError(f"unsupported action: {action!r}")

        reply_text = message.get("reply_text")
        press_enter_value = message.get("press_enter")
        press_enter = press_enter_value if isinstance(press_enter_value, bool) else True
        state_override = cls._parse_state_override(message.get("state_override"))

        if action in {"send_reply", "send_without_enter"}:
            if not isinstance(reply_text, str):
                raise ValueError(f"{action} requires reply_text")
            return cls(
                session_id=session_id.strip(),
                action=cast(SupportedAction, action),
                reply_text=reply_text,
                press_enter=(False if action == "send_without_enter" else press_enter),
            )

        if action == "manual_state_override":
            if state_override is None:
                raise ValueError("manual_state_override requires state_override")
            return cls(
                session_id=session_id.strip(),
                action=cast(SupportedAction, action),
                state_override=state_override,
            )

        if reply_text is not None:
            raise ValueError(f"{action} does not accept reply_text")

        return cls(session_id=session_id.strip(), action=cast(SupportedAction, action))

    @staticmethod
    def _parse_state_override(value: object) -> AttentionState | None:
        if value is None:
            return None
        if isinstance(value, AttentionState):
            return value
        if isinstance(value, str):
            try:
                return AttentionState(value)
            except ValueError as exc:
                raise ValueError(f"unsupported state_override: {value!r}") from exc
        raise ValueError("state_override must be a string")


@dataclass(slots=True)
class SessionActionRouter:
    registry: SessionRegistry
    is_session_live: LiveSessionLookup
    dispatch_action: DispatchAction
    _logger: ContextAdapter = field(init=False)

    def __post_init__(self) -> None:
        self._logger = get_logger("daemon.action_router")

    async def handle_message(self, message: dict[str, object]) -> ActionResult:
        try:
            request = SessionActionRequest.from_message(message)
        except ValueError as exc:
            self._logger.warning("Rejected malformed action request: %s", exc)
            action = str(message.get("action", ""))
            reason = (
                "unsupported_action"
                if action and action not in _SUPPORTED_ACTIONS
                else "invalid_action_request"
            )
            return failure_result(
                session_id=str(message.get("session_id", "")),
                action=action,
                reason=reason,
                detail=str(exc),
            )

        status = await self.registry.get(request.session_id)
        if status is None:
            self._logger.warning(
                "Rejected action for missing session",
                extra={"session_id": request.session_id},
            )
            return failure_result(
                session_id=request.session_id,
                action=request.action,
                reason="session_not_found",
                detail="session not found",
            )

        if request.action == "mark_read":
            await self.registry.mark_read(request.session_id)
            return local_success_result(
                session_id=request.session_id,
                action=request.action,
                reason="marked_read",
                detail="session marked read",
            )

        if request.action == "manual_state_override" and request.state_override is not None:
            updated = status.model_copy(
                update={
                    "state": request.state_override,
                    "summary": f"Manual state: {request.state_override.value}",
                    "state_reason": "manual_state_override",
                    "attention_score": attention_priority(request.state_override),
                    "last_event_at": datetime.now(UTC),
                }
            )
            await self.registry.upsert(updated)
            return local_success_result(
                session_id=request.session_id,
                action=request.action,
                reason="state_overridden",
                detail=f"state set to {request.state_override.value}",
            )

        if request.action == "hide_pet":
            if self.is_session_live(request.session_id):
                return failure_result(
                    session_id=request.session_id,
                    action=request.action,
                    reason="session_live",
                    detail="live sessions cannot be hidden without stopping their control source",
                )
            await self.registry.remove(request.session_id)
            return local_success_result(
                session_id=request.session_id,
                action=request.action,
                reason="hidden",
                detail="session hidden",
            )

        if not self.is_session_live(request.session_id):
            self._logger.warning(
                "Rejected action for inactive session",
                extra={"session_id": request.session_id},
            )
            return failure_result(
                session_id=request.session_id,
                action=request.action,
                reason="session_not_live",
                detail="session is not live",
            )

        if status.has_action_restrictions() and not status.supports_action(request.action):
            self._logger.warning(
                "Rejected action outside session capability",
                extra={"session_id": request.session_id, "action": request.action},
            )
            return failure_result(
                session_id=request.session_id,
                action=request.action,
                reason="action_not_supported",
                detail=f"{request.action} is not supported by this session",
            )

        return normalize_action_result_message(await self.dispatch_action(request))
