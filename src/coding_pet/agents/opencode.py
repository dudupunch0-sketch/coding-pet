from __future__ import annotations

from coding_pet.agents.base import AgentAdapter
from coding_pet.models import AgentKind


class OpenCodeAdapter(AgentAdapter):
    def agent_kind(self) -> AgentKind:
        return AgentKind.OPENCODE

    def launch_command(self, *, prompt: str, workspace: str) -> list[str]:
        return ["opencode", "run", prompt]
