from __future__ import annotations

import asyncio
import json
import os
import uuid
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from coding_pet.models import INACTIVE_SESSION_ACTIONS, SessionStatus, action_capabilities_for


@dataclass(slots=True)
class StateStore:
    path: Path

    async def write_sessions(self, sessions: list[SessionStatus]) -> None:
        payload = [session.model_dump(mode="json") for session in sessions]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(self._write_text_atomic, json.dumps(payload, indent=2))

    def _write_text_atomic(self, text: str) -> None:
        temporary_path = self.path.with_name(
            f".{self.path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
        )
        try:
            temporary_path.write_text(text, "utf-8")
            temporary_path.replace(self.path)
        finally:
            temporary_path.unlink(missing_ok=True)

    async def read_sessions(self) -> list[SessionStatus]:
        if not self.path.exists():
            return []
        text = await asyncio.to_thread(self.path.read_text, "utf-8")
        try:
            raw = json.loads(text)
            if not isinstance(raw, list):
                raise ValueError("state snapshot must be a JSON list")
            return [SessionStatus.model_validate(item) for item in raw]
        except (json.JSONDecodeError, TypeError, ValueError, ValidationError):
            await asyncio.to_thread(self._quarantine_invalid_snapshot)
            return []

    def _quarantine_invalid_snapshot(self) -> None:
        if not self.path.exists():
            return
        quarantine_path = self.path.with_name(
            f"{self.path.name}.invalid.{os.getpid()}.{uuid.uuid4().hex}"
        )
        self.path.replace(quarantine_path)

    async def restore_sessions(self) -> list[SessionStatus]:
        sessions = await self.read_sessions()
        return [
            session.model_copy(
                update={
                    "live": False,
                    "supported_actions": list(INACTIVE_SESSION_ACTIONS),
                    "action_capabilities": action_capabilities_for(
                        INACTIVE_SESSION_ACTIONS,
                        source_kind=session.source_kind,
                    ),
                }
            )
            for session in sessions
        ]
