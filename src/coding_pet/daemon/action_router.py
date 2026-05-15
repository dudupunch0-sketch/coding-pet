from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Literal, cast

from coding_pet.daemon.session_registry import SessionRegistry
from coding_pet.logging import ContextAdapter, get_logger
from coding_pet.models import AttentionState

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
    return {
        "type": "action_result",
        "session_id": session_id,
        "action": action,
        "ok": False,
        "reason": reason,
        "detail": detail,
    }


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

        if await self.registry.get(request.session_id) is None:
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

        return await self.dispatch_action(request)
