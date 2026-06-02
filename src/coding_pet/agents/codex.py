from __future__ import annotations

from coding_pet.agents.base import AgentAdapter
from coding_pet.models import AgentKind


class CodexAdapter(AgentAdapter):
    def agent_kind(self) -> AgentKind:
        return AgentKind.CODEX

    def binary_name(self) -> str:
        return "codex"

    def default_control_messages(self) -> dict[str, str]:
        return {
            "approve": "y",
            "reject": "n",
        }

    def launch_command(self, *, prompt: str, workspace: str) -> list[str]:
        return ["codex", prompt] if prompt.strip() else ["codex"]
