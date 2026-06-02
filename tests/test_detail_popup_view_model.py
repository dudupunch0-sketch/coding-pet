from __future__ import annotations

from datetime import UTC, datetime

from coding_pet.gui.detail_view_model import build_detail_view_model
from coding_pet.models import AgentKind, AttentionState, SessionStatus
from coding_pet.transcripts.model import TranscriptEvent


def test_detail_view_model_separates_target_last_input_request_and_transcript() -> None:
    status = SessionStatus(
        session_id="tmux-%3",
        agent_kind=AgentKind.CLAUDE_CODE,
        title="auth-fix",
        workspace="/proj/ws/auth",
        state=AttentionState.NEEDS_INPUT,
        summary="입력 필요",
        last_event_at=datetime(2026, 5, 15, 10, 43, tzinfo=UTC),
        source_kind="tmux",
        tmux_pane_id="%3",
        tmux_session_name="claude-auth",
        tmux_window_pane="0.0",
        last_dashboard_input="OAuth2 callback 실패 원인을 분석해줘",
        agent_waiting_message="dev / stage / prod 중 어떤 환경 기준으로 볼까요?",
    )
    event = TranscriptEvent(
        event_id="e1",
        session_id="tmux-%3",
        ts=datetime(2026, 5, 15, 10, 43, tzinfo=UTC),
        direction="out",
        source="tmux_capture",
        text="Need clarification",
    )

    vm = build_detail_view_model(status, [event])

    assert vm.target_label == "Claude Code · claude-auth:%3 · /proj/ws/auth"
    assert vm.last_input == "OAuth2 callback 실패 원인을 분석해줘"
    assert vm.agent_request == "dev / stage / prod 중 어떤 환경 기준으로 볼까요?"
    assert vm.transcript_rows[0].text == "Need clarification"



def test_detail_popup_shell_builds_raw_send_requests_without_trimming() -> None:
    from coding_pet.gui.detail_popup import DetailPopupShell

    status = SessionStatus(
        session_id="tmux-%3",
        agent_kind=AgentKind.OPENCODE,
        title="build",
        workspace="/proj/ws/build",
        state=AttentionState.NEEDS_INPUT,
        summary="입력 필요",
        last_event_at=datetime(2026, 5, 15, 10, 43, tzinfo=UTC),
        source_kind="tmux",
        tmux_pane_id="%3",
        tmux_session_name="opencode-build",
    )
    popup = DetailPopupShell(status=status, events=[])
    raw_text = "  stage 환경\n$HOME ; \\ done  "

    assert popup.build_send_request(raw_text, press_enter=True) == {
        "type": "action_request",
        "session_id": "tmux-%3",
        "action": "send_reply",
        "reply_text": raw_text,
        "press_enter": True,
    }
    assert popup.build_send_request(raw_text, press_enter=False)["action"] == "send_without_enter"
    assert popup.build_attach_request() == {
        "type": "action_request",
        "session_id": "tmux-%3",
        "action": "attach",
    }
    assert popup.build_hide_request() == {
        "type": "action_request",
        "session_id": "tmux-%3",
        "action": "hide_pet",
    }


def test_detail_popup_shell_emits_send_and_attach_requests() -> None:
    from coding_pet.gui.detail_popup import DetailPopupShell

    status = SessionStatus(
        session_id="tmux-%3",
        agent_kind=AgentKind.OPENCODE,
        title="build",
        workspace="/proj/ws/build",
        state=AttentionState.NEEDS_INPUT,
        summary="input needed",
        last_event_at=datetime(2026, 5, 15, 10, 43, tzinfo=UTC),
        source_kind="tmux",
        tmux_pane_id="%3",
        tmux_session_name="opencode-build",
    )
    emitted: list[dict[str, object]] = []
    popup = DetailPopupShell(status=status, events=[], on_action_request=emitted.append)

    draft = popup.submit_reply("  keep going\n$HOME  ", press_enter=False)
    attach = popup.submit_attach()
    hide = popup.submit_hide()

    assert emitted == [draft, attach, hide]
    assert draft == {
        "type": "action_request",
        "session_id": "tmux-%3",
        "action": "send_without_enter",
        "reply_text": "  keep going\n$HOME  ",
        "press_enter": False,
    }
    assert attach == {
        "type": "action_request",
        "session_id": "tmux-%3",
        "action": "attach",
    }
    assert hide == {
        "type": "action_request",
        "session_id": "tmux-%3",
        "action": "hide_pet",
    }


def test_session_panel_exposes_tmux_console_actions_for_live_tmux_sessions() -> None:
    from coding_pet.gui.session_panel import PanelAction, SessionPanelViewModel

    status = SessionStatus(
        session_id="tmux-%3",
        agent_kind=AgentKind.CLAUDE_CODE,
        title="auth",
        workspace="/proj/ws/auth",
        state=AttentionState.NEEDS_CHOICE,
        summary="선택 필요",
        last_event_at=datetime(2026, 5, 15, 10, 43, tzinfo=UTC),
        source_kind="tmux",
        tmux_pane_id="%3",
    )

    actions = SessionPanelViewModel().actions_for(status)

    assert actions == [
        PanelAction.SEND_REPLY,
        PanelAction.SEND_WITHOUT_ENTER,
        PanelAction.ATTACH,
        PanelAction.MARK_READ,
    ]


def test_session_panel_exposes_tmux_approval_actions_for_permission_sessions() -> None:
    from coding_pet.gui.session_panel import PanelAction, SessionPanelViewModel

    status = SessionStatus(
        session_id="tmux-%3",
        agent_kind=AgentKind.CLAUDE_CODE,
        title="auth",
        workspace="/proj/ws/auth",
        state=AttentionState.NEEDS_PERMISSION,
        summary="approval needed",
        last_event_at=datetime(2026, 5, 15, 10, 43, tzinfo=UTC),
        source_kind="tmux",
        tmux_pane_id="%3",
    )

    actions = SessionPanelViewModel().actions_for(status)

    assert actions[:4] == [
        PanelAction.APPROVE,
        PanelAction.REJECT,
        PanelAction.SEND_REPLY,
        PanelAction.SEND_WITHOUT_ENTER,
    ]


def test_panel_actions_that_cross_ipc_match_daemon_action_contract() -> None:
    from coding_pet.daemon.action_router import SessionActionRequest
    from coding_pet.gui.session_panel import PanelAction

    for action in PanelAction:
        if action == PanelAction.OPEN_WORKSPACE:
            continue
        message: dict[str, object] = {
            "type": "action_request",
            "session_id": "tmux-%3",
            "action": action.value,
        }
        if action in {PanelAction.SEND_REPLY, PanelAction.SEND_WITHOUT_ENTER}:
            message["reply_text"] = "continue"

        request = SessionActionRequest.from_message(message)

        assert request.action == action.value
