from __future__ import annotations

import shutil
from dataclasses import dataclass

from coding_pet.agents.base import AgentAdapter
from coding_pet.agents.claude_code import ClaudeCodeAdapter
from coding_pet.agents.opencode import OpenCodeAdapter
from coding_pet.models import AgentKind


@dataclass(frozen=True, slots=True)
class AgentBackendStatus:
    agent_kind: AgentKind
    adapter: AgentAdapter
    binary_name: str
    available: bool
    reason: str
    binary_path: str | None = None


class AgentBackendRegistry:
    def __init__(self, backends: dict[AgentKind, AgentBackendStatus]) -> None:
        self._backends = backends

    @classmethod
    def default(cls) -> AgentBackendRegistry:
        adapters = [ClaudeCodeAdapter(), OpenCodeAdapter()]
        backends: dict[AgentKind, AgentBackendStatus] = {}
        for adapter in adapters:
            binary_name = adapter.binary_name()
            binary_path = shutil.which(binary_name)
            available = binary_path is not None
            reason = (
                f"available at {binary_path}"
                if binary_path is not None
                else f"not installed (missing '{binary_name}')"
            )
            backends[adapter.agent_kind()] = AgentBackendStatus(
                agent_kind=adapter.agent_kind(),
                adapter=adapter,
                binary_name=binary_name,
                available=available,
                reason=reason,
                binary_path=binary_path,
            )
        return cls(backends)

    def describe(self, agent_kind: AgentKind) -> AgentBackendStatus:
        return self._backends[agent_kind]

    def list_all(self) -> list[AgentBackendStatus]:
        ordered_kinds = sorted(self._backends, key=lambda item: item.value)
        return [self._backends[kind] for kind in ordered_kinds]
