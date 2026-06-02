from __future__ import annotations

import asyncio
from pathlib import Path
from typing import cast

import pytest

from coding_pet.daemon.session_registry import SessionRegistry
from coding_pet.gui.app import CodingPetWidgetApp
from coding_pet.ipc.server import IpcServer
from coding_pet.models import AgentKind, AttentionState, SessionStatus


class FakeClient:
    def __init__(self) -> None:
        self.sent: list[dict[str, object]] = []

    async def send(self, payload: dict[str, object]) -> None:
        self.sent.append(payload)


def build_status(session_id: str, state: AttentionState) -> SessionStatus:
    from datetime import UTC, datetime

    return SessionStatus(
        session_id=session_id,
        agent_kind=AgentKind.CLAUDE_CODE,
        title=session_id,
        workspace=f"/tmp/{session_id}",
        state=state,
        summary=f"{session_id}:{state.value}",
        last_event_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_widget_app_applies_snapshot_and_incremental_updates(tmp_path: Path) -> None:
    registry = SessionRegistry()
    await registry.upsert(build_status("alpha", AttentionState.RUNNING))
    await registry.upsert(build_status("beta", AttentionState.NEEDS_PERMISSION))

    server = IpcServer(socket_path=tmp_path / "coding-pet.sock", registry=registry)
    await server.start()

    try:
        app = CodingPetWidgetApp(socket_path=server.socket_path)
        await app.connect_to_daemon(message_limit=3)

        assert sorted(app.widgets) == ["alpha", "beta"]
        assert app.widgets["alpha"].status.state is AttentionState.RUNNING
        assert app.widgets["beta"].status.state is AttentionState.NEEDS_PERMISSION

        await registry.upsert(build_status("alpha", AttentionState.COMPLETED))
        await registry.remove("beta")
        await asyncio.sleep(0.05)

        alpha_state = cast(AttentionState, app.widgets["alpha"].status.state)
        assert alpha_state == AttentionState.COMPLETED
        assert "beta" not in app.widgets
    finally:
        await app.disconnect_from_daemon()
        await server.stop()


@pytest.mark.asyncio
async def test_widget_app_preserves_deterministic_layout_with_two_live_sessions(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "coding_pet.gui.app.CodingPetWidgetApp.ensure_app",
        lambda self: (_ for _ in ()).throw(RuntimeError("no deterministic test screen")),
    )
    registry = SessionRegistry()
    server = IpcServer(socket_path=tmp_path / "coding-pet.sock", registry=registry)
    await server.start()

    try:
        app = CodingPetWidgetApp(socket_path=server.socket_path)
        task = asyncio.create_task(app.connect_to_daemon(message_limit=3))
        await asyncio.sleep(0.05)

        await registry.upsert(build_status("zeta", AttentionState.RUNNING))
        await registry.upsert(build_status("alpha", AttentionState.NEEDS_INPUT))
        await asyncio.sleep(0.05)

        assert set(app.widgets) == {"alpha", "zeta"}
        assert (app.widgets["alpha"].x, app.widgets["alpha"].y) == (1160, 600)
        assert (app.widgets["zeta"].x, app.widgets["zeta"].y) == (1160, 492)

        await task
    finally:
        await app.disconnect_from_daemon()
        await server.stop()


@pytest.mark.asyncio
async def test_widget_app_tracks_transcript_snapshots_and_appends() -> None:
    app = CodingPetWidgetApp()
    app.show_sessions([build_status("tmux-%3", AttentionState.NEEDS_INPUT)])

    await app.apply_daemon_message({
        "type": "transcript_snapshot",
        "session_id": "tmux-%3",
        "events": [
            {
                "event_id": "out-1",
                "session_id": "tmux-%3",
                "ts": "2026-05-15T10:42:01+00:00",
                "direction": "out",
                "source": "tmux_capture",
                "text": "어떤 브랜치로 할까요?",
            }
        ],
    })
    await app.apply_daemon_message({
        "type": "transcript_appended",
        "session_id": "tmux-%3",
        "event": {
            "event_id": "in-1",
            "session_id": "tmux-%3",
            "ts": "2026-05-15T10:42:02+00:00",
            "direction": "in",
            "source": "dashboard_input",
            "text": "main으로 진행해",
        },
    })

    assert [event.text for event in app.transcripts["tmux-%3"]] == [
        "어떤 브랜치로 할까요?",
        "main으로 진행해",
    ]
    popup = app.widgets["tmux-%3"].open_detail_popup()
    assert [row.text for row in popup.view_model().transcript_rows] == [
        "어떤 브랜치로 할까요?",
        "main으로 진행해",
    ]


@pytest.mark.asyncio
async def test_widget_detail_open_requests_transcript_and_marks_read() -> None:
    app = CodingPetWidgetApp()
    fake_client = FakeClient()
    status = build_status("tmux-%3", AttentionState.NEEDS_INPUT).model_copy(
        update={
            "source_kind": "tmux",
            "tmux_pane_id": "%3",
            "unread": True,
        }
    )
    app.show_sessions([status])
    app._client = fake_client  # type: ignore[assignment]

    app.widgets["tmux-%3"].open_detail_popup()
    await asyncio.sleep(0)

    assert app.widgets["tmux-%3"].status.unread is False
    assert fake_client.sent == [
        {"type": "transcript_request", "session_id": "tmux-%3", "limit": 100},
        {"type": "action_request", "session_id": "tmux-%3", "action": "mark_read"},
    ]


@pytest.mark.asyncio
async def test_widget_detail_popup_actions_are_sent_over_ipc() -> None:
    app = CodingPetWidgetApp()
    fake_client = FakeClient()
    status = build_status("tmux-%3", AttentionState.NEEDS_INPUT).model_copy(
        update={
            "source_kind": "tmux",
            "tmux_pane_id": "%3",
        }
    )
    app.show_sessions([status])
    app._client = fake_client  # type: ignore[assignment]

    popup = app.widgets["tmux-%3"].open_detail_popup()
    await asyncio.sleep(0)
    fake_client.sent.clear()

    popup.submit_reply("  keep going\n$HOME  ", press_enter=False)
    await asyncio.sleep(0)

    assert fake_client.sent == [
        {
            "type": "action_request",
            "session_id": "tmux-%3",
            "action": "send_without_enter",
            "reply_text": "  keep going\n$HOME  ",
            "press_enter": False,
        }
    ]
