from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from shlex import split as shell_split

from coding_pet.agents.base import AgentAdapter
from coding_pet.agents.claude_code import ClaudeCodeAdapter
from coding_pet.agents.opencode import OpenCodeAdapter
from coding_pet.daemon.manager import MonitorManager
from coding_pet.daemon.session_registry import SessionRegistry
from coding_pet.models import AgentKind


async def _readlines(stream: asyncio.StreamReader) -> AsyncIterator[str]:
    while True:
        line = await stream.readline()
        if not line:
            break
        yield line.decode(errors="replace").rstrip("\n")


@dataclass(slots=True)
class DaemonApp:
    registry: SessionRegistry = field(default_factory=SessionRegistry)
    manager: MonitorManager = field(init=False)

    def __post_init__(self) -> None:
        self.manager = MonitorManager(registry=self.registry)

    def adapter_for(self, agent_kind: AgentKind) -> AgentAdapter:
        if agent_kind is AgentKind.CLAUDE_CODE:
            return ClaudeCodeAdapter()
        return OpenCodeAdapter()

    async def monitor_command(
        self,
        *,
        agent_kind: AgentKind,
        command: str,
        workspace: str,
        session_id: str,
        title: str | None = None,
    ) -> None:
        process = await asyncio.create_subprocess_exec(
            *shell_split(command),
            cwd=workspace,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        assert process.stdout is not None
        await self.manager.start_session(
            session_id=session_id,
            adapter=self.adapter_for(agent_kind),
            workspace=str(Path(workspace)),
            title=title,
            output_lines=_readlines(process.stdout),
            process=process,
            pid=process.pid,
        )
        await self.manager.wait_for_all()
