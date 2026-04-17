from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path

from coding_pet.models import SessionStatus


@dataclass(slots=True)
class StateStore:
    path: Path

    async def write_sessions(self, sessions: list[SessionStatus]) -> None:
        payload = [session.model_dump(mode="json") for session in sessions]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(self.path.write_text, json.dumps(payload, indent=2), "utf-8")

    async def read_sessions(self) -> list[SessionStatus]:
        if not self.path.exists():
            return []
        text = await asyncio.to_thread(self.path.read_text, "utf-8")
        raw = json.loads(text)
        return [SessionStatus.model_validate(item) for item in raw]

    async def restore_sessions(self) -> list[SessionStatus]:
        return await self.read_sessions()
