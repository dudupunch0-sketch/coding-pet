from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from coding_pet.models import SessionStatus

RegistryCallback = Callable[[dict[str, Any]], Awaitable[None]]


class SessionRegistry:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._sessions: dict[str, SessionStatus] = {}
        self._subscribers: set[RegistryCallback] = set()

    async def upsert(self, status: SessionStatus) -> None:
        async with self._lock:
            self._sessions[status.session_id] = status
            subscribers = list(self._subscribers)
        await self._notify(
            subscribers,
            {"type": "session_updated", "session": status.model_dump(mode="json")},
        )

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
            removed = self._sessions.pop(session_id, None) is not None
            subscribers = list(self._subscribers)
        if removed:
            await self._notify(
                subscribers,
                {"type": "session_removed", "session_id": session_id},
            )
        return removed

    def subscribe(self, callback: RegistryCallback) -> Callable[[], None]:
        self._subscribers.add(callback)

        def unsubscribe() -> None:
            self._subscribers.discard(callback)

        return unsubscribe

    async def _notify(
        self,
        subscribers: list[RegistryCallback],
        message: dict[str, Any],
    ) -> None:
        if not subscribers:
            return
        await asyncio.gather(*(subscriber(message) for subscriber in subscribers))
