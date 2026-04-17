from __future__ import annotations

from coding_pet.agents.base import AgentAdapter
from coding_pet.models import AgentKind


class ClaudeCodeAdapter(AgentAdapter):
    def agent_kind(self) -> AgentKind:
        return AgentKind.CLAUDE_CODE

    def launch_command(self, *, prompt: str, workspace: str) -> list[str]:
        return ["claude", "code", prompt]
