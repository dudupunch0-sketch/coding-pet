from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from coding_pet.config import load_config
from coding_pet.daemon.session_registry import SessionRegistry
from coding_pet.gui.app import CodingPetWidgetApp
from coding_pet.models import AgentKind, AttentionState, SessionStatus
from coding_pet.state_store import StateStore


def build_status(session_id: str, state: AttentionState) -> SessionStatus:
    return SessionStatus(
        session_id=session_id,
        agent_kind=AgentKind.CLAUDE_CODE,
        title=session_id,
        workspace=f"/tmp/{session_id}",
        state=state,
        summary=f"{session_id}:{state.value}",
        last_event_at=datetime(2026, 4, 17, tzinfo=UTC),
    )


@pytest.mark.asyncio
async def test_state_store_restore_keeps_only_inactive_session_actions(
    tmp_path: Path,
) -> None:
    store = StateStore(tmp_path / "state.json")
    status = build_status("done", AttentionState.COMPLETED).model_copy(
        update={"supported_actions": ["send_reply", "approve", "reject"]}
    )

    await store.write_sessions([status])
    restored = await store.restore_sessions()

    assert restored[0].live is False
    assert restored[0].supported_actions == [
        "hide_pet",
        "mark_read",
        "manual_state_override",
    ]


@pytest.mark.asyncio
async def test_state_store_writes_latest_snapshot(tmp_path: Path) -> None:
    store = StateStore(tmp_path / "state.json")
    await store.write_sessions(
        [
            build_status("alpha", AttentionState.RUNNING),
            build_status("beta", AttentionState.COMPLETED),
        ]
    )

    reloaded = await store.read_sessions()

    assert [status.session_id for status in reloaded] == ["alpha", "beta"]
    assert reloaded[1].state is AttentionState.COMPLETED


@pytest.mark.asyncio
async def test_state_store_write_failure_preserves_previous_snapshot(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    store = StateStore(tmp_path / "state.json")
    await store.write_sessions([build_status("old", AttentionState.RUNNING)])
    previous_text = store.path.read_text("utf-8")
    original_write_text = Path.write_text

    def fail_after_partial_write(
        path: Path,
        data: str,
        encoding: str | None = None,
        errors: str | None = None,
        newline: str | None = None,
    ) -> int:
        if path.parent == store.path.parent and path.name != store.path.name:
            original_write_text(path, "[", encoding=encoding)
            raise OSError("simulated partial write")
        return original_write_text(
            path,
            data,
            encoding=encoding,
            errors=errors,
            newline=newline,
        )

    monkeypatch.setattr(Path, "write_text", fail_after_partial_write)

    with pytest.raises(OSError, match="simulated partial write"):
        await store.write_sessions([build_status("new", AttentionState.COMPLETED)])

    assert store.path.read_text("utf-8") == previous_text
    assert not [
        path
        for path in store.path.parent.iterdir()
        if path.name.startswith(f".{store.path.name}.") and path.suffix == ".tmp"
    ]


@pytest.mark.asyncio
async def test_state_store_restore_returns_historical_sessions(tmp_path: Path) -> None:
    store = StateStore(tmp_path / "state.json")
    await store.write_sessions(
        [
            build_status("done", AttentionState.COMPLETED),
            build_status("failed", AttentionState.FAILED),
        ]
    )

    restored = await store.restore_sessions()

    assert {status.session_id for status in restored} == {"done", "failed"}
    assert {status.state for status in restored} == {
        AttentionState.COMPLETED,
        AttentionState.FAILED,
    }
    assert {status.live for status in restored} == {False}


@pytest.mark.asyncio
async def test_state_store_quarantines_corrupt_snapshot_on_read(tmp_path: Path) -> None:
    store = StateStore(tmp_path / "state.json")
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text("[", encoding="utf-8")

    restored = await store.restore_sessions()
    quarantine = list(store.path.parent.glob("state.json.invalid.*"))

    assert restored == []
    assert not store.path.exists()
    assert len(quarantine) == 1
    assert quarantine[0].read_text("utf-8") == "["


@pytest.mark.asyncio
async def test_state_store_quarantines_schema_invalid_snapshot(tmp_path: Path) -> None:
    store = StateStore(tmp_path / "state.json")
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text('[{"session_id": ""}]', encoding="utf-8")

    restored = await store.restore_sessions()
    quarantine = list(store.path.parent.glob("state.json.invalid.*"))

    assert restored == []
    assert not store.path.exists()
    assert len(quarantine) == 1


@pytest.mark.asyncio
async def test_widget_can_boot_from_snapshot_before_live_updates(tmp_path: Path) -> None:
    store = StateStore(tmp_path / "state.json")
    await store.write_sessions(
        [
            build_status("snap-a", AttentionState.RUNNING),
            build_status("snap-b", AttentionState.NEEDS_INPUT),
        ]
    )

    app = CodingPetWidgetApp(state_store=store)
    await app.load_snapshot()

    assert sorted(app.widgets) == ["snap-a", "snap-b"]
    assert app.widgets["snap-b"].status.state is AttentionState.NEEDS_INPUT
    assert app.widgets["snap-b"].status.live is False
    assert app.widgets["snap-b"].available_panel_actions() == ["open_workspace", "hide_pet"]


@pytest.mark.asyncio
async def test_registry_persistence_hook_writes_snapshot(tmp_path: Path) -> None:
    store = StateStore(tmp_path / "state.json")
    registry = SessionRegistry()

    async def persist(_message: dict[str, object]) -> None:
        await store.write_sessions(await registry.list_sessions())

    registry.subscribe(persist)
    await registry.upsert(build_status("persisted", AttentionState.REVIEW_NEEDED))

    restored = await store.read_sessions()

    assert [status.session_id for status in restored] == ["persisted"]
    assert restored[0].state is AttentionState.REVIEW_NEEDED


def test_load_config_exposes_default_state_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("CODING_PET_STATE_FILE", raising=False)

    config = load_config()

    assert config.state_file == tmp_path / ".local/state" / "coding-pet" / "state.json"
