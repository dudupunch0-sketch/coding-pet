from __future__ import annotations

import asyncio

from coding_pet.models import SessionStatus


class SessionRegistry:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._sessions: dict[str, SessionStatus] = {}

    async def upsert(self, status: SessionStatus) -> None:
        async with self._lock:
            self._sessions[status.session_id] = status

    async def get(self, session_id: str) -> SessionStatus | None:
        async with self._lock:
            return self._sessions.get(session_id)

    async def list_sessions(self) -> list[SessionStatus]:
        async with self._lock:
            return sorted(
                self._sessions.values(),
                key=lambda status: (-status.attention_score, status.session_id),
            )

    async def pet_layout_order(self) -> list[str]:
        async with self._lock:
            return sorted(self._sessions)

    async def mark_read(self, session_id: str) -> None:
        async with self._lock:
            status = self._sessions.get(session_id)
            if status is not None:
                self._sessions[session_id] = status.model_copy(update={"unread": False})

    async def remove(self, session_id: str) -> bool:
        async with self._lock:
            return self._sessions.pop(session_id, None) is not None
