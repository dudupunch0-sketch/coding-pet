from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from coding_pet.daemon.session_registry import SessionRegistry
from coding_pet.gui.app import CodingPetWidgetApp
from coding_pet.gui.session_panel import PanelAction, SessionPanelViewModel
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


def test_session_panel_exposes_reply_shortcuts_for_input_sessions() -> None:
    panel = SessionPanelViewModel()
    shortcuts = panel.reply_shortcuts_for(build_status("input", AttentionState.NEEDS_INPUT))

    assert shortcuts == ["keep going", "summarize shortly"]


@pytest.mark.asyncio
async def test_widget_app_sends_reply_shortcut_action_over_ipc(tmp_path: Path) -> None:
    registry = SessionRegistry()
    received: list[dict[str, str]] = []

    async def handle_action(message: dict[str, str]) -> None:
        received.append(message)

    server = IpcServer(
        socket_path=tmp_path / "coding-pet.sock",
        registry=registry,
        action_handler=handle_action,
    )
    await server.start()

    try:
        app = CodingPetWidgetApp(socket_path=server.socket_path)
        await app.connect_to_daemon(message_limit=1)
        await app.send_panel_action(
            session_id="input-session",
            action=PanelAction.SEND_REPLY,
            reply_text="keep going",
        )
        await asyncio.sleep(0.05)
    finally:
        await app.disconnect_from_daemon()
        await server.stop()

    assert received == [
        {
            "type": "action_request",
            "session_id": "input-session",
            "action": "send_reply",
            "reply_text": "keep going",
        }
    ]
