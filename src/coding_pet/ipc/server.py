from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from coding_pet.daemon.session_registry import SessionRegistry

SessionCallback = Callable[[dict[str, Any]], Awaitable[None]]
ActionCallback = Callable[[dict[str, object]], Awaitable[None]]


@dataclass(slots=True)
class IpcServer:
    socket_path: Path
    registry: SessionRegistry
    action_handler: ActionCallback | None = None
    _server: asyncio.AbstractServer | None = field(init=False, default=None)
    _writers: set[asyncio.StreamWriter] = field(init=False, default_factory=set)
    _unsubscribe: Callable[[], None] | None = field(init=False, default=None)

    async def start(self) -> None:
        self.socket_path.parent.mkdir(parents=True, exist_ok=True)
        if self.socket_path.exists():
            self.socket_path.unlink()
        self._unsubscribe = self.registry.subscribe(self.broadcast)
        self._server = await asyncio.start_unix_server(self._handle_client, path=self.socket_path)

    async def stop(self) -> None:
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None
        for writer in list(self._writers):
            writer.close()
            await writer.wait_closed()
        self._writers.clear()
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        if self.socket_path.exists():
            self.socket_path.unlink()

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        self._writers.add(writer)
        try:
            await self._send_snapshot(writer)
            while True:
                line = await reader.readline()
                if not line:
                    break
                message = json.loads(line)
                if message.get("type") == "ping":
                    await self._send(writer, {"type": "ping"})
                elif message.get("type") == "action_request" and self.action_handler is not None:
                    payload: dict[str, object] = {"type": "action_request"}
                    for key in ("session_id", "action", "reply_text"):
                        if key in message:
                            payload[key] = message[key]
                    await self.action_handler(payload)
        finally:
            self._writers.discard(writer)
            writer.close()
            try:
                await writer.wait_closed()
            except BrokenPipeError:
                pass

    async def _send_snapshot(self, writer: asyncio.StreamWriter) -> None:
        listed = await self.registry.list_sessions()
        sessions = [status.model_dump(mode="json") for status in listed]
        await self._send(writer, {"type": "snapshot", "sessions": sessions})

    async def broadcast(self, message: dict[str, Any]) -> None:
        dead: list[asyncio.StreamWriter] = []
        for writer in list(self._writers):
            try:
                await self._send(writer, message)
            except (BrokenPipeError, ConnectionError):
                dead.append(writer)
        for writer in dead:
            self._writers.discard(writer)

    async def _send(self, writer: asyncio.StreamWriter, message: dict[str, Any]) -> None:
        writer.write((json.dumps(message) + "\n").encode())
        await writer.drain()
