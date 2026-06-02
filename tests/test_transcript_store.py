from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from coding_pet.transcripts.model import TranscriptEvent
from coding_pet.transcripts.store import TranscriptStore, redact_transcript_text


@pytest.mark.asyncio
async def test_transcript_store_appends_lists_and_preserves_utf8(tmp_path: Path) -> None:
    store = TranscriptStore(tmp_path / "transcripts.sqlite")
    await store.initialize()
    first = await store.append(
        session_id="tmux-%3",
        direction="in",
        source="dashboard_input",
        text="stage 환경 기준으로 계속해줘",
        ts=datetime(2026, 5, 15, 10, 0, tzinfo=UTC),
    )
    await store.append(
        session_id="other",
        direction="out",
        source="tmux_capture",
        text="ignored",
    )

    events = await store.list_recent_events("tmux-%3", limit=10)

    assert [event.event_id for event in events] == [first.event_id]
    assert events[0].text == "stage 환경 기준으로 계속해줘"
    assert events[0].direction == "in"


@pytest.mark.asyncio
async def test_transcript_store_redacts_common_secrets_before_persistence(
    tmp_path: Path,
) -> None:
    store = TranscriptStore(tmp_path / "transcripts.sqlite")

    event = await store.append(
        session_id="tmux-%3",
        direction="out",
        source="tmux_capture",
        text=(
            "Authorization: Bearer sk-test_abcdefghijklmnopqrstuvwxyz "
            "OPENAI_API_KEY=sk-live_abcdefghijklmnopqrstuvwxyz "
            "password=super-secret"
        ),
        ts=datetime(2026, 5, 15, 10, 0, tzinfo=UTC),
    )

    events = await store.list_recent_events("tmux-%3", limit=10)
    with sqlite3.connect(tmp_path / "transcripts.sqlite") as connection:
        raw_text = connection.execute("SELECT text FROM transcript_events").fetchone()[0]

    assert "sk-test_" not in event.text
    assert "sk-live_" not in event.text
    assert "super-secret" not in event.text
    assert event.text == events[0].text == raw_text
    assert "Authorization: Bearer [REDACTED]" in event.text
    assert "OPENAI_API_KEY=[REDACTED]" in event.text
    assert "password=[REDACTED]" in event.text


@pytest.mark.asyncio
async def test_transcript_store_redacts_events_passed_directly(tmp_path: Path) -> None:
    store = TranscriptStore(tmp_path / "transcripts.sqlite")
    event = TranscriptEvent(
        event_id="fixed",
        session_id="tmux-%3",
        ts=datetime(2026, 5, 15, 10, 0, tzinfo=UTC),
        direction="in",
        source="dashboard_input",
        text="api_token: secret-token-value",
    )

    await store.append_event(event)

    events = await store.list_recent_events("tmux-%3", limit=10)

    assert events[0].text == "api_token: [REDACTED]"


@pytest.mark.asyncio
async def test_transcript_store_redacts_custom_patterns_before_persistence(
    tmp_path: Path,
) -> None:
    store = TranscriptStore(
        tmp_path / "transcripts.sqlite",
        custom_redaction_patterns=(r"PROJECT-[0-9]{4}", r"INTERNAL_SECRET_[A-Z]+"),
    )

    event = await store.append(
        session_id="tmux-%3",
        direction="out",
        source="tmux_capture",
        text="ticket PROJECT-1234 token INTERNAL_SECRET_ALPHA",
        ts=datetime(2026, 5, 15, 10, 0, tzinfo=UTC),
    )

    events = await store.list_recent_events("tmux-%3", limit=10)
    with sqlite3.connect(tmp_path / "transcripts.sqlite") as connection:
        raw_text = connection.execute("SELECT text FROM transcript_events").fetchone()[0]

    assert event.text == events[0].text == raw_text
    assert "PROJECT-1234" not in event.text
    assert "INTERNAL_SECRET_ALPHA" not in event.text
    assert event.text == "ticket [REDACTED] token [REDACTED]"


def test_redact_transcript_text_reads_custom_patterns_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "CODING_PET_TRANSCRIPT_REDACTION_PATTERNS",
        r"PROJECT-[0-9]{4};INTERNAL_SECRET_[A-Z]+",
    )

    redacted = redact_transcript_text("PROJECT-1234 INTERNAL_SECRET_ALPHA")

    assert redacted == "[REDACTED] [REDACTED]"


@pytest.mark.asyncio
async def test_transcript_store_prunes_old_events(tmp_path: Path) -> None:
    store = TranscriptStore(tmp_path / "transcripts.sqlite")
    await store.initialize()
    base = datetime(2026, 5, 15, tzinfo=UTC)
    for index in range(5):
        await store.append(
            session_id="tmux-%3",
            direction="out",
            source="tmux_capture",
            text=f"event {index}",
            ts=base + timedelta(seconds=index),
        )

    await store.prune_events("tmux-%3", max_events=2)

    assert [event.text for event in await store.list_recent_events("tmux-%3", limit=10)] == [
        "event 3",
        "event 4",
    ]
