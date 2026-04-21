from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from coding_pet.daemon.session_registry import SessionRegistry
from coding_pet.gui.app import CodingPetWidgetApp
from coding_pet.ipc.server import IpcServer
from coding_pet.models import AgentKind, AttentionState, SessionStatus


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
async def test_widget_marks_restored_snapshot_sessions_read_only(tmp_path: Path) -> None:
    registry = SessionRegistry()
    restored = build_status("alpha", AttentionState.NEEDS_INPUT).model_copy(update={"live": False})
    await registry.upsert(restored)
    server = IpcServer(socket_path=tmp_path / "coding-pet.sock", registry=registry)
    await server.start()

    try:
        app = CodingPetWidgetApp(socket_path=server.socket_path)
        await app.connect_to_daemon(message_limit=1)

        widget = app.widgets["alpha"]
        assert widget.status.live is False
        assert widget.available_panel_actions() == ["open_workspace"]
        assert widget.available_reply_shortcuts() == []
    finally:
        await app.disconnect_from_daemon()
        await server.stop()


@pytest.mark.asyncio
async def test_widget_receives_action_result_message_without_overwriting_session_summary(
    tmp_path: Path,
) -> None:
    registry = SessionRegistry()
    await registry.upsert(build_status("alpha", AttentionState.NEEDS_INPUT))
    server = IpcServer(socket_path=tmp_path / "coding-pet.sock", registry=registry)
    await server.start()

    try:
        app = CodingPetWidgetApp(socket_path=server.socket_path)
        await app.connect_to_daemon(message_limit=1)
        await app.apply_daemon_message(
            {
                "type": "action_result",
                "session_id": "alpha",
                "action": "send_reply",
                "ok": True,
                "detail": "keep going delivered",
            }
        )

        assert app.last_action_result == {
            "session_id": "alpha",
            "action": "send_reply",
            "ok": True,
            "detail": "keep going delivered",
            "type": "action_result",
        }
        widget = app.widgets["alpha"]
        assert widget.status.summary == "alpha:needs_input"
        assert widget.presentation().bubble_text == "Action sent: keep going delivered"
        assert widget.status.state is AttentionState.RUNNING
    finally:
        await app.disconnect_from_daemon()
        await server.stop()


@pytest.mark.asyncio
async def test_widget_shows_normalized_failure_reason_feedback(tmp_path: Path) -> None:
    registry = SessionRegistry()
    await registry.upsert(build_status("alpha", AttentionState.NEEDS_INPUT))
    server = IpcServer(socket_path=tmp_path / "coding-pet.sock", registry=registry)
    await server.start()

    try:
        app = CodingPetWidgetApp(socket_path=server.socket_path)
        await app.connect_to_daemon(message_limit=1)
        await app.apply_daemon_message(
            {
                "type": "action_result",
                "session_id": "alpha",
                "action": "send_reply",
                "ok": False,
                "reason": "session_not_live",
                "detail": "session is not live",
            }
        )

        assert app.last_action_result is not None
        assert app.last_action_result["reason"] == "session_not_live"
        assert app.widgets["alpha"].presentation().bubble_text == (
            "Action failed: session is not live"
        )
    finally:
        await app.disconnect_from_daemon()
        await server.stop()


@pytest.mark.asyncio
async def test_widget_clears_action_feedback_when_new_session_output_arrives(
    tmp_path: Path,
) -> None:
    registry = SessionRegistry()
    await registry.upsert(build_status("alpha", AttentionState.NEEDS_INPUT))
    server = IpcServer(socket_path=tmp_path / "coding-pet.sock", registry=registry)
    await server.start()

    try:
        app = CodingPetWidgetApp(socket_path=server.socket_path)
        await app.connect_to_daemon(message_limit=1)
        await app.apply_daemon_message(
            {
                "type": "action_result",
                "session_id": "alpha",
                "action": "send_reply",
                "ok": False,
                "detail": "session is not live",
            }
        )
        assert app.widgets["alpha"].presentation().bubble_text == (
            "Action failed: session is not live"
        )

        updated = build_status("alpha", AttentionState.NEEDS_INPUT).model_copy(
            update={"summary": "Waiting for the next reply."}
        )
        await app.apply_daemon_message(
            {"type": "session_updated", "session": updated.model_dump(mode="json")}
        )

        assert app.widgets["alpha"].presentation().bubble_text == "Waiting for the next reply."
        assert app.widgets["alpha"].status.summary == "Waiting for the next reply."
    finally:
        await app.disconnect_from_daemon()
        await server.stop()


@pytest.mark.asyncio
async def test_widget_reconnect_clears_stale_action_feedback(tmp_path: Path) -> None:
    registry = SessionRegistry()
    await registry.upsert(build_status("alpha", AttentionState.NEEDS_INPUT))
    server = IpcServer(socket_path=tmp_path / "coding-pet.sock", registry=registry)
    await server.start()

    try:
        app = CodingPetWidgetApp(socket_path=server.socket_path)
        await app.connect_to_daemon(message_limit=1)
        await app.apply_daemon_message(
            {
                "type": "action_result",
                "session_id": "alpha",
                "action": "send_reply",
                "ok": True,
                "detail": "keep going delivered",
            }
        )
        assert app.last_action_result is not None
        assert (
            app.widgets["alpha"].presentation().bubble_text
            == "Action sent: keep going delivered"
        )

        await app.disconnect_from_daemon()
        await app.connect_to_daemon(message_limit=1)

        assert app.last_action_result is None
        assert app.widgets["alpha"].presentation().bubble_text == "alpha:needs_input"
    finally:
        await app.disconnect_from_daemon()
        await server.stop()


@pytest.mark.asyncio
async def test_widget_app_sends_reply_and_receives_success_feedback(tmp_path: Path) -> None:
    registry = SessionRegistry()
    await registry.upsert(build_status("alpha", AttentionState.NEEDS_INPUT))

    async def handle_action(message: dict[str, object]) -> dict[str, object]:
        return {
            "type": "action_result",
            "session_id": str(message["session_id"]),
            "action": str(message["action"]),
            "ok": True,
            "detail": f"{message.get('reply_text', '')} delivered",
        }

    server = IpcServer(
        socket_path=tmp_path / "coding-pet.sock",
        registry=registry,
        action_handler=handle_action,
    )
    await server.start()

    try:
        app = CodingPetWidgetApp(socket_path=server.socket_path)
        await app.connect_to_daemon(message_limit=2)
        await app.send_panel_action(
            session_id="alpha",
            action="send_reply",
            reply_text="summarize shortly",
        )
        await asyncio.sleep(0.05)

        assert app.last_action_result is not None
        assert app.last_action_result["ok"] is True
        assert app.last_action_result["detail"] == "summarize shortly delivered"
    finally:
        await app.disconnect_from_daemon()
        await server.stop()
