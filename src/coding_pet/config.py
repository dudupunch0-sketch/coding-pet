from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Final

APP_NAME: Final = "coding-pet"


@dataclass(slots=True)
class AppConfig:
    config_dir: Path
    state_dir: Path
    runtime_dir: Path
    log_dir: Path
    log_level: str = "INFO"
    capture_transcripts: bool = False
    notification_cooldown_seconds: int = 60


def _path_from_env(name: str) -> Path | None:
    value = os.getenv(name)
    if not value:
        return None
    return Path(value).expanduser()


def _xdg_dir(env_name: str, home_relative: str) -> Path:
    override = _path_from_env(env_name)
    if override is not None:
        return override
    home = Path(os.path.expanduser("~"))
    return home / home_relative


def _default_runtime_root() -> Path | None:
    runtime_root = Path("/run/user") / str(os.getuid())
    if runtime_root.exists() and os.access(runtime_root, os.W_OK):
        return runtime_root
    return None


def load_config() -> AppConfig:
    config_dir = _path_from_env("CODING_PET_CONFIG_DIR")
    state_dir = _path_from_env("CODING_PET_STATE_DIR")
    runtime_dir = _path_from_env("CODING_PET_RUNTIME_DIR")
    log_dir = _path_from_env("CODING_PET_LOG_DIR")

    resolved_config_dir = config_dir or (_xdg_dir("XDG_CONFIG_HOME", ".config") / APP_NAME)
    resolved_state_dir = state_dir or (_xdg_dir("XDG_STATE_HOME", ".local/state") / APP_NAME)
    runtime_root = runtime_dir or _path_from_env("XDG_RUNTIME_DIR") or _default_runtime_root()
    resolved_runtime_dir = (
        runtime_root / APP_NAME
        if runtime_root is not None
        else resolved_state_dir / "runtime"
    )
    resolved_log_dir = log_dir or (resolved_state_dir / "logs")

    return AppConfig(
        config_dir=resolved_config_dir,
        state_dir=resolved_state_dir,
        runtime_dir=resolved_runtime_dir,
        log_dir=resolved_log_dir,
        log_level=os.getenv("CODING_PET_LOG_LEVEL", "INFO").upper(),
        capture_transcripts=os.getenv("CODING_PET_CAPTURE_TRANSCRIPTS", "false").lower()
        in {"1", "true", "yes", "on"},
        notification_cooldown_seconds=int(
            os.getenv("CODING_PET_NOTIFICATION_COOLDOWN_SECONDS", "60")
        ),
    )
