from __future__ import annotations

from datetime import UTC, datetime

from coding_pet.gui.session_panel import PanelAction, SessionPanelViewModel
from coding_pet.models import AgentKind, AttentionState, SessionStatus


def build_status(
    session_id: str,
    state: AttentionState,
    *,
    summary: str = "status",
    agent_kind: AgentKind = AgentKind.CLAUDE_CODE,
    unread: bool = False,
) -> SessionStatus:
    return SessionStatus(
        session_id=session_id,
        agent_kind=agent_kind,
        title=session_id,
        workspace=f"/tmp/{session_id}",
        state=state,
        summary=summary,
        last_event_at=datetime(2026, 4, 17, tzinfo=UTC),
        unread=unread,
    )


def test_widget_mood_maps_attention_states() -> None:
    from coding_pet.gui.theme import WidgetMood, mood_for_status

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
    from coding_pet.gui.bubble import bubble_text_for_status

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
    from coding_pet.gui.app import layout_sessions

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


def test_session_panel_sorts_urgent_sessions_first() -> None:
    panel = SessionPanelViewModel()
    rows = panel.rows_for(
        [
            build_status("run", AttentionState.RUNNING),
            build_status("input", AttentionState.NEEDS_INPUT),
            build_status("fail", AttentionState.FAILED),
        ]
    )

    assert [row.session_id for row in rows] == ["fail", "input", "run"]


def test_session_panel_marks_read_when_opened() -> None:
    panel = SessionPanelViewModel()
    status = build_status("needs-read", AttentionState.NEEDS_INPUT, unread=True)

    opened = panel.open_session(status)

    assert opened.unread is False


def test_session_panel_exposes_actions_for_permission_and_input_workflows() -> None:
    panel = SessionPanelViewModel()

    permission_actions = panel.actions_for(
        build_status("perm", AttentionState.NEEDS_PERMISSION)
    )
    input_actions = panel.actions_for(build_status("input", AttentionState.NEEDS_INPUT))
    review_actions = panel.actions_for(build_status("review", AttentionState.REVIEW_NEEDED))

    assert permission_actions == [PanelAction.APPROVE, PanelAction.REJECT]
    assert input_actions == [PanelAction.SEND_REPLY]
    assert review_actions == [PanelAction.OPEN_WORKSPACE]


def test_session_panel_marks_restored_sessions_read_only_and_disables_live_actions() -> None:
    panel = SessionPanelViewModel()
    restored = build_status("restored", AttentionState.NEEDS_PERMISSION).model_copy(
        update={"live": False}
    )

    rows = panel.rows_for([restored])

    assert rows[0].read_only is True
    assert panel.actions_for(restored) == [PanelAction.OPEN_WORKSPACE]
    assert panel.reply_shortcuts_for(restored) == []


def test_session_panel_shows_multiple_agent_kinds() -> None:
    panel = SessionPanelViewModel()
    rows = panel.rows_for(
        [
            build_status("claude", AttentionState.RUNNING, agent_kind=AgentKind.CLAUDE_CODE),
            build_status("open", AttentionState.NEEDS_PERMISSION, agent_kind=AgentKind.OPENCODE),
        ]
    )

    assert {row.agent_kind for row in rows} == {AgentKind.CLAUDE_CODE, AgentKind.OPENCODE}
