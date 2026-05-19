from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from coding_pet.daemon.session_registry import SessionRegistry
from coding_pet.ipc.client import IpcClient
from coding_pet.ipc.server import IpcServer
from coding_pet.models import AgentKind, AttentionState, SessionStatus


def build_status(session_id: str, state: AttentionState, *, title: str = "task") -> SessionStatus:
    return SessionStatus(
        session_id=session_id,
        agent_kind=AgentKind.CLAUDE_CODE,
        title=title,
        workspace=f"/tmp/{session_id}",
        state=state,
        summary=title,
        last_event_at=datetime(2026, 4, 17, tzinfo=UTC),
    )


@pytest.mark.asyncio
async def test_ipc_client_receives_snapshot_on_connect(tmp_path: Path) -> None:
    registry = SessionRegistry()
    await registry.upsert(build_status("s1", AttentionState.RUNNING, title="first"))
    server = IpcServer(socket_path=tmp_path / "coding-pet.sock", registry=registry)
    await server.start()

    try:
        client = IpcClient(server.socket_path)
        messages = await client.connect_and_read(count=1)
        assert messages[0]["type"] == "snapshot"
        assert messages[0]["sessions"][0]["session_id"] == "s1"
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_ipc_streams_incremental_updates(tmp_path: Path) -> None:
    registry = SessionRegistry()
    server = IpcServer(socket_path=tmp_path / "coding-pet.sock", registry=registry)
    await server.start()

    try:
        client = IpcClient(server.socket_path)
        await client.connect()
        await client.read_message()

        await registry.upsert(build_status("s1", AttentionState.NEEDS_INPUT, title="needs input"))
        message = await client.read_message()

        assert message["type"] == "session_updated"
        assert message["session"]["session_id"] == "s1"
        assert message["session"]["state"] == "needs_input"
    finally:
        await client.close()
        await server.stop()


@pytest.mark.asyncio
async def test_ipc_streams_removals(tmp_path: Path) -> None:
    registry = SessionRegistry()
    await registry.upsert(build_status("s1", AttentionState.RUNNING))
    server = IpcServer(socket_path=tmp_path / "coding-pet.sock", registry=registry)
    await server.start()

    try:
        client = IpcClient(server.socket_path)
        await client.connect()
        await client.read_message()

        removed = await registry.remove("s1")
        assert removed is True
        message = await client.read_message()

        assert message == {"type": "session_removed", "session_id": "s1"}
    finally:
        await client.close()
        await server.stop()


@pytest.mark.asyncio
async def test_ipc_reconnect_pushes_fresh_snapshot(tmp_path: Path) -> None:
    registry = SessionRegistry()
    server = IpcServer(socket_path=tmp_path / "coding-pet.sock", registry=registry)
    await server.start()

    try:
        first = IpcClient(server.socket_path)
        await first.connect()
        initial = await first.read_message()
        assert initial == {"type": "snapshot", "sessions": []}
        await first.close()

        await registry.upsert(build_status("s2", AttentionState.COMPLETED, title="done"))

        second = IpcClient(server.socket_path)
        try:
            messages = await second.connect_and_read(count=1)
            assert messages[0]["type"] == "snapshot"
            assert messages[0]["sessions"][0]["session_id"] == "s2"
            assert messages[0]["sessions"][0]["state"] == "completed"
        finally:
            await second.close()
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_ipc_ping_returns_pong(tmp_path: Path) -> None:
    registry = SessionRegistry()
    server = IpcServer(socket_path=tmp_path / "coding-pet.sock", registry=registry)
    await server.start()

    try:
        client = IpcClient(server.socket_path)
        await client.connect()
        await client.read_message()
        await client.send({"type": "ping"})
        assert await client.read_message() == {"type": "ping"}
    finally:
        await client.close()
        await server.stop()



@pytest.mark.asyncio
async def test_ipc_forwards_press_enter_and_state_override_in_action_requests(
    tmp_path: Path,
) -> None:
    registry = SessionRegistry()
    received: list[dict[str, object]] = []

    async def handle_action(message: dict[str, object]) -> dict[str, object]:
        received.append(message)
        return {
            "type": "action_result",
            "session_id": message["session_id"],
            "action": message["action"],
            "ok": True,
        }

    server = IpcServer(
        socket_path=tmp_path / "coding-pet.sock",
        registry=registry,
        action_handler=handle_action,
    )
    await server.start()
    client = IpcClient(server.socket_path)
    try:
        await client.connect()
        await client.read_message()
        await client.send({
            "type": "action_request",
            "session_id": "tmux-%3",
            "action": "send_without_enter",
            "reply_text": "  raw  ",
            "press_enter": False,
            "state_override": "running",
        })
        await client.read_message()
    finally:
        await client.close()
        await server.stop()

    assert received == [{
        "type": "action_request",
        "session_id": "tmux-%3",
        "action": "send_without_enter",
        "reply_text": "  raw  ",
        "press_enter": False,
        "state_override": "running",
    }]


@pytest.mark.asyncio
async def test_ipc_serves_transcript_snapshot(tmp_path: Path) -> None:
    from coding_pet.transcripts.store import TranscriptStore

    registry = SessionRegistry()
    store = TranscriptStore(tmp_path / "transcripts.sqlite")
    await store.initialize()
    await store.append(
        session_id="tmux-%3",
        direction="out",
        source="tmux_capture",
        text="hello",
    )
    server = IpcServer(
        socket_path=tmp_path / "coding-pet.sock",
        registry=registry,
        transcript_store=store,
    )
    await server.start()
    client = IpcClient(server.socket_path)
    try:
        await client.connect()
        await client.read_message()
        await client.send({"type": "transcript_request", "session_id": "tmux-%3", "limit": 5})
        message = await client.read_message()
    finally:
        await client.close()
        await server.stop()

    assert message["type"] == "transcript_snapshot"
    assert message["session_id"] == "tmux-%3"
    assert message["events"][0]["text"] == "hello"


@pytest.mark.asyncio
async def test_ipc_broadcasts_appended_transcript_events(tmp_path: Path) -> None:
    registry = SessionRegistry()
    server = IpcServer(socket_path=tmp_path / "coding-pet.sock", registry=registry)
    await server.start()
    client = IpcClient(server.socket_path)
    try:
        await client.connect()
        await client.read_message()

        await server.broadcast_transcript_event({
            "event_id": "event-1",
            "session_id": "tmux-%3",
            "ts": "2026-05-15T10:42:01+00:00",
            "direction": "out",
            "source": "tmux_capture",
            "text": "새 출력",
        })
        message = await client.read_message()
    finally:
        await client.close()
        await server.stop()

    assert message == {
        "type": "transcript_appended",
        "session_id": "tmux-%3",
        "event": {
            "event_id": "event-1",
            "session_id": "tmux-%3",
            "ts": "2026-05-15T10:42:01+00:00",
            "direction": "out",
            "source": "tmux_capture",
            "text": "새 출력",
        },
    }
