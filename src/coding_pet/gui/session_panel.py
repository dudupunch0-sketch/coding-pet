from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from coding_pet.models import SessionStatus


class PanelAction(StrEnum):
    OPEN_WORKSPACE = "open_workspace"
    APPROVE = "approve"
    REJECT = "reject"
    SEND_REPLY = "send_reply"
    SEND_WITHOUT_ENTER = "send_without_enter"
    ATTACH = "attach"
    MARK_READ = "mark_read"
    HIDE_PET = "hide_pet"


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
            return self._filter_supported(
                status,
                [PanelAction.OPEN_WORKSPACE, PanelAction.HIDE_PET],
            )
        if status.source_kind == "tmux" and status.tmux_pane_id:
            actions = [PanelAction.ATTACH, PanelAction.MARK_READ]
            if status.state.name == "NEEDS_PERMISSION":
                return self._filter_supported(
                    status,
                    [
                        PanelAction.APPROVE,
                        PanelAction.REJECT,
                        PanelAction.SEND_REPLY,
                        PanelAction.SEND_WITHOUT_ENTER,
                        *actions,
                    ],
                )
            if status.state.name in {"NEEDS_INPUT", "NEEDS_CHOICE"}:
                return self._filter_supported(
                    status,
                    [PanelAction.SEND_REPLY, PanelAction.SEND_WITHOUT_ENTER, *actions],
                )
            return self._filter_supported(status, actions)
        if status.state.name == "NEEDS_PERMISSION":
            return self._filter_supported(
                status,
                [PanelAction.APPROVE, PanelAction.REJECT],
            )
        if status.state.name == "NEEDS_INPUT":
            return self._filter_supported(status, [PanelAction.SEND_REPLY])
        return [PanelAction.OPEN_WORKSPACE]

    def reply_shortcuts_for(self, status: SessionStatus) -> list[str]:
        if not status.live or status.state.name not in {"NEEDS_INPUT", "NEEDS_CHOICE"}:
            return []
        if status.has_action_restrictions() and not status.supports_action(
            PanelAction.SEND_REPLY.value
        ):
            return []
        return list(self.QUICK_REPLY_SHORTCUTS)

    def _filter_supported(
        self,
        status: SessionStatus,
        actions: list[PanelAction],
    ) -> list[PanelAction]:
        if not status.has_action_restrictions():
            return actions
        filtered = [
            action
            for action in actions
            if action is PanelAction.OPEN_WORKSPACE or status.supports_action(action.value)
        ]
        return filtered or [PanelAction.OPEN_WORKSPACE]
