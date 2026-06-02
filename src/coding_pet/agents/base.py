from __future__ import annotations

import os
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from coding_pet.daemon.classifier import ClassifierInput, OutputClassifier
from coding_pet.events import SessionEvent
from coding_pet.models import AGENT_LIVE_ACTIONS, AgentKind, AttentionState, SessionStatus

if TYPE_CHECKING:
    from coding_pet.daemon.action_router import SupportedAction


class AgentAdapter(ABC):
    def __init__(self, *, classifier: OutputClassifier | None = None) -> None:
        self.classifier = classifier or OutputClassifier()

    @abstractmethod
    def agent_kind(self) -> AgentKind:
        raise NotImplementedError

    @abstractmethod
    def binary_name(self) -> str:
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
            supported_actions=list(AGENT_LIVE_ACTIONS),
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
        if action in {"send_reply", "send_without_enter"}:
            return reply_text
        if action in {"approve", "reject"}:
            return self._control_text_for(action)
        return None

    def default_control_messages(self) -> dict[str, str]:
        return {
            "approve": "approve",
            "reject": "reject",
        }

    def _control_text_for(self, action: str) -> str | None:
        default = self.default_control_messages().get(action)
        for env_name in self._control_text_env_names(action):
            value = os.environ.get(env_name)
            if value is not None:
                return value
        return default

    def _control_text_env_names(self, action: str) -> tuple[str, ...]:
        kind = self.agent_kind().value.upper()
        env_action = action.upper()
        aliases = [f"CODING_PET_{kind}_{env_action}_TEXT"]
        if kind == "CLAUDE_CODE":
            aliases.append(f"CODING_PET_CLAUDE_{env_action}_TEXT")
        return tuple(aliases)

    @abstractmethod
    def launch_command(self, *, prompt: str, workspace: str) -> list[str]:
        raise NotImplementedError

    def default_title(self, workspace: str) -> str:
        name = Path(workspace).name
        return name or workspace
