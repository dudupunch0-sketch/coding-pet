from __future__ import annotations

import os
from pathlib import Path

import pytest

from coding_pet.config import AppConfig, load_config


def test_load_config_uses_xdg_directories(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "runtime"))

    config = load_config()

    assert config.config_dir == tmp_path / "cfg" / "coding-pet"
    assert config.state_dir == tmp_path / "state" / "coding-pet"
    assert config.runtime_dir == tmp_path / "runtime" / "coding-pet"
    assert config.log_dir == config.state_dir / "logs"


def test_load_config_prefers_run_user_uid_when_available(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runtime_root = Path("/run/user") / str(os.getuid())
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    monkeypatch.delenv("CODING_PET_RUNTIME_DIR", raising=False)
    monkeypatch.setattr("coding_pet.config._default_runtime_root", lambda: runtime_root)

    config = load_config()

    assert config.runtime_dir == runtime_root / "coding-pet"


def test_load_config_falls_back_to_state_runtime_when_run_user_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    monkeypatch.delenv("CODING_PET_RUNTIME_DIR", raising=False)
    monkeypatch.setattr("coding_pet.config._default_runtime_root", lambda: None)

    config = load_config()

    assert config.runtime_dir == tmp_path / ".local/state" / "coding-pet" / "runtime"


def test_environment_overrides_win(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    override_dir = tmp_path / "custom-config"
    monkeypatch.setenv("CODING_PET_CONFIG_DIR", str(override_dir))

    config = load_config()

    assert config.config_dir == override_dir


def test_app_config_defaults_are_production_safe(tmp_path: Path) -> None:
    config = AppConfig(
        config_dir=tmp_path / "cfg",
        state_dir=tmp_path / "state",
        runtime_dir=tmp_path / "run",
        log_dir=tmp_path / "logs",
        state_file=tmp_path / "state" / "state.json",
    )

    assert config.log_level == "INFO"
    assert config.capture_transcripts is False
    assert config.notification_cooldown_seconds == 60



def test_tmux_and_transcript_config_defaults_are_safe(tmp_path: Path) -> None:
    config = AppConfig(
        config_dir=tmp_path / "cfg",
        state_dir=tmp_path / "state",
        runtime_dir=tmp_path / "run",
        log_dir=tmp_path / "logs",
        state_file=tmp_path / "state" / "state.json",
    )

    assert config.tmux.enabled is False
    assert config.tmux.capture_lines == 200
    assert config.tmux.include_commands == ["claude", "opencode"]
    assert config.transcript.db_path == tmp_path / "state" / "transcripts.sqlite"


def test_load_config_reads_tmux_environment_overrides(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("CODING_PET_TMUX_ENABLED", "1")
    monkeypatch.setenv("CODING_PET_TMUX_CAPTURE_LINES", "123")
    monkeypatch.setenv("CODING_PET_TRANSCRIPT_DB", str(tmp_path / "tx.sqlite"))

    config = load_config()

    assert config.tmux.enabled is True
    assert config.tmux.capture_lines == 123
    assert config.transcript.db_path == tmp_path / "tx.sqlite"


def test_load_config_reads_transcript_enabled_override(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("CODING_PET_TRANSCRIPT_ENABLED", "0")

    config = load_config()

    assert config.transcript.enabled is False
