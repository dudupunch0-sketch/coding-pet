from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from coding_pet.daemon.classifier import ClassifierInput, OutputClassifier
from coding_pet.events import SessionEvent
from coding_pet.models import AgentKind, AttentionState, SessionStatus

if TYPE_CHECKING:
    from coding_pet.daemon.action_router import SupportedAction


class AgentAdapter(ABC):
    def __init__(self, *, classifier: OutputClassifier | None = None) -> None:
        self.classifier = classifier or OutputClassifier()

    @abstractmethod
    def agent_kind(self) -> AgentKind:
        raise NotImplementedError

    def build_initial_status(
        self,
        *,
        session_id: str,
        workspace: str,
        observed_at: datetime,
        pid: int | None = None,
        title: str | None = None,
    ) -> SessionStatus:
        resolved_title = title or self.default_title(workspace)
        return SessionStatus(
            session_id=session_id,
            agent_kind=self.agent_kind(),
            title=resolved_title,
            workspace=workspace,
            state=AttentionState.RUNNING,
            summary=f"Monitoring {resolved_title}",
            last_event_at=observed_at,
            pid=pid,
        )

    def classify_line(self, *, line: str, observed_at: datetime) -> SessionEvent | None:
        return self.classifier.classify(
            ClassifierInput(
                agent_kind=self.agent_kind(),
                line=line,
                observed_at=observed_at,
            )
        )

    def extract_summary(self, line: str) -> str:
        return line.strip()

    def control_message(
        self,
        *,
        action: SupportedAction,
        reply_text: str | None = None,
    ) -> str | None:
        if action == "send_reply":
            return reply_text
        if action == "approve":
            return "approve"
        if action == "reject":
            return "reject"
        return None

    @abstractmethod
    def launch_command(self, *, prompt: str, workspace: str) -> list[str]:
        raise NotImplementedError

    def default_title(self, workspace: str) -> str:
        name = Path(workspace).name
        return name or workspace
