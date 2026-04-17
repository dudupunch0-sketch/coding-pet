from __future__ import annotations

import os
from pathlib import Path

from coding_pet.config import AppConfig, load_config


def test_load_config_uses_xdg_directories(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "runtime"))

    config = load_config()

    assert config.config_dir == tmp_path / "cfg" / "coding-pet"
    assert config.state_dir == tmp_path / "state" / "coding-pet"
    assert config.runtime_dir == tmp_path / "runtime" / "coding-pet"
    assert config.log_dir == config.state_dir / "logs"


def test_load_config_prefers_run_user_uid_when_available(monkeypatch, tmp_path: Path) -> None:
    runtime_root = Path("/run/user") / str(os.getuid())
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    monkeypatch.delenv("CODING_PET_RUNTIME_DIR", raising=False)
    monkeypatch.setattr("coding_pet.config._default_runtime_root", lambda: runtime_root)

    config = load_config()

    assert config.runtime_dir == runtime_root / "coding-pet"


def test_load_config_falls_back_to_state_runtime_when_run_user_missing(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    monkeypatch.delenv("CODING_PET_RUNTIME_DIR", raising=False)
    monkeypatch.setattr("coding_pet.config._default_runtime_root", lambda: None)

    config = load_config()

    assert config.runtime_dir == tmp_path / ".local/state" / "coding-pet" / "runtime"


def test_environment_overrides_win(monkeypatch, tmp_path: Path) -> None:
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
    )

    assert config.log_level == "INFO"
    assert config.capture_transcripts is False
    assert config.notification_cooldown_seconds == 60
