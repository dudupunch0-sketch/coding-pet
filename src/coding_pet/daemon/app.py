from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from shlex import split as shell_split
from typing import Protocol

from coding_pet.agents.base import AgentAdapter
from coding_pet.agents.claude_code import ClaudeCodeAdapter
from coding_pet.agents.opencode import OpenCodeAdapter
from coding_pet.daemon.manager import MonitorManager
from coding_pet.daemon.session_registry import SessionRegistry
from coding_pet.models import AgentKind


class StdinWriter(Protocol):
    def write(self, data: bytes) -> None: ...

    async def drain(self) -> None: ...


async def _readlines(stream: asyncio.StreamReader) -> AsyncIterator[str]:
    while True:
        line = await stream.readline()
        if not line:
            break
        yield line.decode(errors="replace").rstrip("\n")


async def _send_process_reply(stdin: StdinWriter, reply_text: str) -> None:
    stdin.write((reply_text + "\n").encode())
    await stdin.drain()


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
            stdin=asyncio.subprocess.PIPE,
        )
        assert process.stdout is not None
        stdin = process.stdin
        send_reply: Callable[[str], Awaitable[None]] | None = None
        if stdin is not None:
            async def send_reply(reply_text: str) -> None:
                await _send_process_reply(stdin, reply_text)
        else:
            send_reply = None
        await self.manager.start_session(
            session_id=session_id,
            adapter=self.adapter_for(agent_kind),
            workspace=str(Path(workspace)),
            title=title,
            output_lines=_readlines(process.stdout),
            process=process,
            pid=process.pid,
            reply_handler=send_reply,
        )
        await self.manager.wait_for_all()
