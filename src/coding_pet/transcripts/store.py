from __future__ import annotations

import asyncio
import os
import re
import sqlite3
import uuid
from collections.abc import Iterable
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

SECRET_REDACTION = "[REDACTED]"
CUSTOM_REDACTION_PATTERNS_ENV = "CODING_PET_TRANSCRIPT_REDACTION_PATTERNS"
_BEARER_TOKEN_RE = re.compile(
    r"\b(authorization\s*:\s*bearer\s+)([A-Za-z0-9._~+/=-]+)",
    re.IGNORECASE,
)
_SECRET_ASSIGNMENT_RE = re.compile(
    r"\b("
    r"[A-Za-z0-9_-]*"
    r"(?:api[_-]?key|token|secret|password|passwd|access[_-]?token|auth[_-]?token)"
    r"[A-Za-z0-9_-]*"
    r"\s*[:=]\s*)"
    r"(\"[^\"\s]+\"|'[^'\s]+'|[^\s]+)",
    re.IGNORECASE,
)
_STANDALONE_SECRET_RE = re.compile(
    r"\b(?:sk|rk|pk)-[A-Za-z0-9][A-Za-z0-9_-]{12,}\b"
)


def parse_custom_redaction_patterns(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    normalized = value.replace("\r\n", "\n").replace("\r", "\n").replace(";", "\n")
    return tuple(pattern.strip() for pattern in normalized.splitlines() if pattern.strip())


def validate_custom_redaction_patterns(patterns: Iterable[str]) -> tuple[str, ...]:
    validated: list[str] = []
    for pattern in patterns:
        try:
            re.compile(pattern)
        except re.error as exc:
            raise ValueError(f"invalid custom redaction pattern {pattern!r}: {exc}") from exc
        validated.append(pattern)
    return tuple(validated)


def custom_redaction_patterns_from_env() -> tuple[str, ...]:
    return validate_custom_redaction_patterns(
        parse_custom_redaction_patterns(os.getenv(CUSTOM_REDACTION_PATTERNS_ENV))
    )


def _redact_custom_patterns(text: str, patterns: Iterable[str]) -> str:
    redacted = text
    for pattern in validate_custom_redaction_patterns(patterns):
        redacted = re.sub(pattern, SECRET_REDACTION, redacted)
    return redacted


def redact_transcript_text(
    text: str,
    *,
    custom_redaction_patterns: Iterable[str] | None = None,
) -> str:
    redacted = _BEARER_TOKEN_RE.sub(r"\1" + SECRET_REDACTION, text)
    redacted = _SECRET_ASSIGNMENT_RE.sub(r"\1" + SECRET_REDACTION, redacted)
    redacted = _STANDALONE_SECRET_RE.sub(SECRET_REDACTION, redacted)
    patterns = (
        custom_redaction_patterns
        if custom_redaction_patterns is not None
        else custom_redaction_patterns_from_env()
    )
    return _redact_custom_patterns(redacted, patterns)


@dataclass(slots=True)
class TranscriptStore:
    path: Path
    redact_secrets: bool = True
    custom_redaction_patterns: tuple[str, ...] = ()

    async def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(self._initialize_sync)

    def _initialize_sync(self) -> None:
        with sqlite3.connect(self.path) as connection:
            connection.executescript(SCHEMA)

    async def append_event(self, event: TranscriptEvent) -> None:
        await self.initialize()
        await asyncio.to_thread(self._append_event_sync, self._redact_event(event))

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
        event = self._redact_event(event)
        await self.append_event(event)
        return event

    def _redact_event(self, event: TranscriptEvent) -> TranscriptEvent:
        if not self.redact_secrets:
            return event
        redacted = redact_transcript_text(
            event.text,
            custom_redaction_patterns=self.custom_redaction_patterns,
        )
        if redacted == event.text:
            return event
        return event.model_copy(update={"text": redacted})

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
