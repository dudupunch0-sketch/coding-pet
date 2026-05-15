from __future__ import annotations

import asyncio
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from coding_pet.transcripts.model import TranscriptDirection, TranscriptEvent, TranscriptSource

SCHEMA = """
CREATE TABLE IF NOT EXISTS transcript_events (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    ts TEXT NOT NULL,
    direction TEXT NOT NULL,
    source TEXT NOT NULL,
    text TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_transcript_session_ts
ON transcript_events(session_id, ts);
"""


@dataclass(slots=True)
class TranscriptStore:
    path: Path

    async def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(self._initialize_sync)

    def _initialize_sync(self) -> None:
        with sqlite3.connect(self.path) as connection:
            connection.executescript(SCHEMA)

    async def append_event(self, event: TranscriptEvent) -> None:
        await self.initialize()
        await asyncio.to_thread(self._append_event_sync, event)

    def _append_event_sync(self, event: TranscriptEvent) -> None:
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                """
                INSERT INTO transcript_events(id, session_id, ts, direction, source, text)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.session_id,
                    event.ts.isoformat(),
                    event.direction,
                    event.source,
                    event.text,
                ),
            )

    async def append(
        self,
        *,
        session_id: str,
        direction: TranscriptDirection,
        source: TranscriptSource,
        text: str,
        ts: datetime | None = None,
    ) -> TranscriptEvent:
        event = TranscriptEvent(
            event_id=uuid.uuid4().hex,
            session_id=session_id,
            ts=ts or datetime.now(UTC),
            direction=direction,
            source=source,
            text=text,
        )
        await self.append_event(event)
        return event

    async def list_recent_events(self, session_id: str, limit: int = 100) -> list[TranscriptEvent]:
        await self.initialize()
        return await asyncio.to_thread(self._list_recent_events_sync, session_id, limit)

    def _list_recent_events_sync(self, session_id: str, limit: int) -> list[TranscriptEvent]:
        with sqlite3.connect(self.path) as connection:
            rows = connection.execute(
                """
                SELECT id, session_id, ts, direction, source, text
                FROM transcript_events
                WHERE session_id = ?
                ORDER BY ts DESC, id DESC
                LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()
        events = [
            TranscriptEvent(
                event_id=str(row[0]),
                session_id=str(row[1]),
                ts=datetime.fromisoformat(str(row[2])),
                direction=row[3],
                source=row[4],
                text=str(row[5]),
            )
            for row in rows
        ]
        return list(reversed(events))

    async def prune_events(self, session_id: str, max_events: int) -> None:
        await self.initialize()
        await asyncio.to_thread(self._prune_events_sync, session_id, max_events)

    def _prune_events_sync(self, session_id: str, max_events: int) -> None:
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                """
                DELETE FROM transcript_events
                WHERE session_id = ?
                  AND id NOT IN (
                    SELECT id FROM transcript_events
                    WHERE session_id = ?
                    ORDER BY ts DESC, id DESC
                    LIMIT ?
                  )
                """,
                (session_id, session_id, max_events),
            )
