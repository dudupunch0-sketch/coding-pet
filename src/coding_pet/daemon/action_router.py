from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Literal, cast

from coding_pet.daemon.session_registry import SessionRegistry
from coding_pet.logging import ContextAdapter, get_logger

SupportedAction = Literal["send_reply", "approve", "reject"]
DispatchAction = Callable[["SessionActionRequest"], Awaitable[None]]
LiveSessionLookup = Callable[[str], bool]

_SUPPORTED_ACTIONS = frozenset({"send_reply", "approve", "reject"})


@dataclass(frozen=True, slots=True)
class SessionActionRequest:
    session_id: str
    action: SupportedAction
    reply_text: str | None = None

    @classmethod
    def from_message(cls, message: dict[str, object]) -> SessionActionRequest:
        session_id = message.get("session_id")
        if not isinstance(session_id, str) or not session_id.strip():
            raise ValueError("session_id is required")

        action = message.get("action")
        if not isinstance(action, str) or action not in _SUPPORTED_ACTIONS:
            raise ValueError(f"unsupported action: {action!r}")

        reply_text = message.get("reply_text")
        if action == "send_reply":
            if not isinstance(reply_text, str) or not reply_text.strip():
                raise ValueError("send_reply requires non-empty reply_text")
            return cls(
                session_id=session_id.strip(),
                action=cast(SupportedAction, action),
                reply_text=reply_text.strip(),
            )

        if reply_text is not None:
            raise ValueError(f"{action} does not accept reply_text")

        return cls(session_id=session_id.strip(), action=cast(SupportedAction, action))


@dataclass(slots=True)
class SessionActionRouter:
    registry: SessionRegistry
    is_session_live: LiveSessionLookup
    dispatch_action: DispatchAction
    _logger: ContextAdapter = field(init=False)

    def __post_init__(self) -> None:
        self._logger = get_logger("daemon.action_router")

    async def handle_message(self, message: dict[str, object]) -> None:
        try:
            request = SessionActionRequest.from_message(message)
        except ValueError as exc:
            self._logger.warning("Rejected malformed action request: %s", exc)
            return

        if await self.registry.get(request.session_id) is None:
            self._logger.warning(
                "Rejected action for missing session",
                extra={"session_id": request.session_id},
            )
            return

        if not self.is_session_live(request.session_id):
            self._logger.warning(
                "Rejected action for inactive session",
                extra={"session_id": request.session_id},
            )
            return

        await self.dispatch_action(request)
