from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from coding_pet.models import SessionStatus


class PanelAction(StrEnum):
    OPEN_WORKSPACE = "open_workspace"
    APPROVE = "approve"
    REJECT = "reject"
    SEND_REPLY = "send_reply"


@dataclass(slots=True)
class SessionPanelRow:
    session_id: str
    title: str
    agent_kind: object
    workspace: str
    snippet: str
    unread: bool
    actions: list[PanelAction]
    read_only: bool


class SessionPanelViewModel:
    QUICK_REPLY_SHORTCUTS = ["keep going", "summarize shortly"]

    def rows_for(self, sessions: list[SessionStatus]) -> list[SessionPanelRow]:
        ordered = sorted(sessions, key=lambda status: (-status.attention_score, status.session_id))
        return [
            SessionPanelRow(
                session_id=status.session_id,
                title=status.title,
                agent_kind=status.agent_kind,
                workspace=status.workspace,
                snippet=status.last_output_snippet or status.summary,
                unread=status.unread,
                actions=self.actions_for(status),
                read_only=not status.live,
            )
            for status in ordered
        ]

    def open_session(self, status: SessionStatus) -> SessionStatus:
        return status.model_copy(update={"unread": False})

    def actions_for(self, status: SessionStatus) -> list[PanelAction]:
        if not status.live:
            return [PanelAction.OPEN_WORKSPACE]
        if status.state.name == "NEEDS_PERMISSION":
            return [PanelAction.APPROVE, PanelAction.REJECT]
        if status.state.name == "NEEDS_INPUT":
            return [PanelAction.SEND_REPLY]
        return [PanelAction.OPEN_WORKSPACE]

    def reply_shortcuts_for(self, status: SessionStatus) -> list[str]:
        if not status.live or status.state.name != "NEEDS_INPUT":
            return []
        return list(self.QUICK_REPLY_SHORTCUTS)
