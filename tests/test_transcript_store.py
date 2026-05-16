from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from coding_pet.transcripts.store import TranscriptStore


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
