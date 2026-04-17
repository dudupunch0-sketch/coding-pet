from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any


class IpcClient:
    def __init__(self, socket_path: str | Path) -> None:
        self.socket_path = Path(socket_path)
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None

    async def connect(self) -> None:
        self._reader, self._writer = await asyncio.open_unix_connection(self.socket_path)

    async def connect_and_read(self, *, count: int) -> list[dict[str, Any]]:
        await self.connect()
        try:
            return [await self.read_message() for _ in range(count)]
        finally:
            await self.close()

    async def read_message(self) -> dict[str, Any]:
        if self._reader is None:
            raise RuntimeError("IPC client is not connected")
        line = await self._reader.readline()
        if not line:
            raise RuntimeError("IPC server closed connection")
        import json

        message = json.loads(line)
        if not isinstance(message, dict):
            raise RuntimeError("IPC server returned a non-object message")
        return message

    async def send(self, message: dict[str, Any]) -> None:
        if self._writer is None:
            raise RuntimeError("IPC client is not connected")
        import json

        self._writer.write((json.dumps(message) + "\n").encode())
        await self._writer.drain()

    async def stream_messages(self) -> AsyncIterator[dict[str, Any]]:
        if self._reader is None:
            raise RuntimeError("IPC client is not connected")
        while True:
            try:
                yield await self.read_message()
            except RuntimeError:
                break

    async def close(self) -> None:
        if self._writer is not None:
            self._writer.close()
            await self._writer.wait_closed()
        self._reader = None
        self._writer = None
