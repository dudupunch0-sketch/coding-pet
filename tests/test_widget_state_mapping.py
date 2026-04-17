from __future__ import annotations

from datetime import UTC, datetime

from coding_pet.gui.app import layout_sessions
from coding_pet.gui.bubble import bubble_text_for_status
from coding_pet.gui.theme import WidgetMood, mood_for_status
from coding_pet.models import AgentKind, AttentionState, SessionStatus


def build_status(
    session_id: str,
    state: AttentionState,
    *,
    summary: str = "status",
) -> SessionStatus:
    return SessionStatus(
        session_id=session_id,
        agent_kind=AgentKind.CLAUDE_CODE,
        title=session_id,
        workspace=f"/tmp/{session_id}",
        state=state,
        summary=summary,
        last_event_at=datetime(2026, 4, 17, tzinfo=UTC),
    )


def test_widget_mood_maps_attention_states() -> None:
    assert mood_for_status(build_status("idle", AttentionState.IDLE)) is WidgetMood.IDLE
    assert mood_for_status(build_status("run", AttentionState.RUNNING)) is WidgetMood.TYPING
    assert mood_for_status(
        build_status("done", AttentionState.COMPLETED)
    ) is WidgetMood.CELEBRATE
    assert mood_for_status(
        build_status("perm", AttentionState.NEEDS_PERMISSION)
    ) is WidgetMood.ALERT
    assert mood_for_status(build_status("fail", AttentionState.FAILED)) is WidgetMood.SAD


def test_bubble_text_uses_summary_and_truncates() -> None:
    status = build_status(
        "bubble",
        AttentionState.NEEDS_INPUT,
        summary="This is a fairly long summary that should be clipped for the pet bubble display.",
    )

    bubble = bubble_text_for_status(status, max_length=36)

    assert bubble.endswith("…")
    assert len(bubble) <= 36
    assert "summary" in bubble.lower()


def test_layout_sessions_is_stable_and_stacks_vertically() -> None:
    positions = layout_sessions(
        [
            build_status("s2", AttentionState.RUNNING),
            build_status("s1", AttentionState.NEEDS_PERMISSION),
            build_status("s3", AttentionState.COMPLETED),
        ],
        screen_width=1920,
        screen_height=1080,
        pet_size=(96, 96),
        margin=24,
        gap=12,
    )

    assert list(positions) == ["s1", "s2", "s3"]
    assert positions["s1"] == (1800, 960)
    assert positions["s2"] == (1800, 852)
    assert positions["s3"] == (1800, 744)
