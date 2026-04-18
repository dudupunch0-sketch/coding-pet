from __future__ import annotations

import asyncio
from pathlib import Path
from typing import cast

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
    tmp_path: Path,
) -> None:
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
