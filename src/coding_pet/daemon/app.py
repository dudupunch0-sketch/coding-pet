from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from shlex import split as shell_split
from typing import Protocol

from coding_pet.agents.base import AgentAdapter
from coding_pet.agents.registry import AgentBackendRegistry
from coding_pet.daemon.action_router import ActionResult, SessionActionRequest, failure_result
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


async def _send_process_message(
    stdin: StdinWriter,
    message: str,
    *,
    press_enter: bool = True,
) -> None:
    suffix = "\n" if press_enter else ""
    stdin.write((message + suffix).encode())
    await stdin.drain()


@dataclass(slots=True)
class DaemonApp:
    registry: SessionRegistry = field(default_factory=SessionRegistry)
    backend_registry: AgentBackendRegistry = field(default_factory=AgentBackendRegistry.default)
    manager: MonitorManager = field(init=False)

    def __post_init__(self) -> None:
        self.manager = MonitorManager(registry=self.registry)

    def adapter_for(self, agent_kind: AgentKind) -> AgentAdapter:
        backend = self.backend_registry.describe(agent_kind)
        if not backend.available:
            raise RuntimeError(
                f"backend {agent_kind.value} is unavailable: {backend.reason}"
            )
        return backend.adapter

    async def monitor_command(
        self,
        *,
        agent_kind: AgentKind,
        command: str,
        workspace: str,
        session_id: str,
        title: str | None = None,
    ) -> None:
        adapter = self.adapter_for(agent_kind)
        process = await asyncio.create_subprocess_exec(
            *shell_split(command),
            cwd=workspace,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            stdin=asyncio.subprocess.PIPE,
        )
        assert process.stdout is not None
        stdin = process.stdin
        send_action: Callable[[SessionActionRequest], Awaitable[ActionResult | None]] | None = None
        if stdin is not None:
            async def send_action(request: SessionActionRequest) -> ActionResult:
                message = adapter.control_message(
                    action=request.action,
                    reply_text=request.reply_text,
                )
                if message is None:
                    return failure_result(
                        session_id=request.session_id,
                        action=request.action,
                        reason="unsupported_action",
                        detail=f"{request.action} is not supported by {agent_kind.value}",
                    )
                await _send_process_message(stdin, message, press_enter=request.press_enter)
                return {
                    "type": "action_result",
                    "session_id": request.session_id,
                    "action": request.action,
                    "ok": True,
                    "reason": "delivered",
                    "delivered_text": message,
                    "detail": f"{message} delivered",
                }
        else:
            send_action = None
        await self.manager.start_session(
            session_id=session_id,
            adapter=adapter,
            workspace=str(Path(workspace)),
            title=title,
            output_lines=_readlines(process.stdout),
            process=process,
            pid=process.pid,
            action_handler=send_action,
        )
        await self.manager.wait_for_all()
