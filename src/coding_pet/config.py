from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

APP_NAME: Final = "coding-pet"


@dataclass(slots=True)
class UiConfig:
    mode: str = "pet"
    screen_edge: str = "right"
    always_on_top: bool = True
    bubble_timeout_sec: int = 8
    show_completed_for_sec: int = 20
    click_behavior: str = "detail_popup"
    double_click_behavior: str = "tmux_attach"
    pet_width: int = 120
    pet_height: int = 120
    spacing_px: int = 12


@dataclass(slots=True)
class TerminalConfig:
    attach_command: str | None = None


@dataclass(slots=True)
class TmuxConfig:
    enabled: bool = False
    poll_interval_ms: int = 1000
    capture_lines: int = 200
    include_session_patterns: list[str] = field(
        default_factory=lambda: ["claude-*", "opencode-*", "agent-*"]
    )
    include_commands: list[str] = field(default_factory=lambda: ["claude", "opencode"])
    exclude_session_patterns: list[str] = field(default_factory=list)


@dataclass(slots=True)
class InputConfig:
    send_method: str = "tmux_buffer"
    enter_after_send: bool = True
    send_shortcut: str = "Ctrl+Enter"
    newline_shortcut: str = "Shift+Enter"


@dataclass(slots=True)
class StateDetectionConfig:
    stalled_after_sec: int = 300
    waiting_after_idle_sec: int = 5
    manual_override: bool = True


@dataclass(slots=True)
class TranscriptConfig:
    enabled: bool = True
    backend: str = "sqlite"
    max_events_per_session: int = 5000
    redact_secrets: bool = False
    db_path: Path | None = None


@dataclass(slots=True)
class AppConfig:
    config_dir: Path
    state_dir: Path
    runtime_dir: Path
    log_dir: Path
    state_file: Path
    log_level: str = "INFO"
    capture_transcripts: bool = False
    notification_cooldown_seconds: int = 60
    ui: UiConfig = field(default_factory=UiConfig)
    terminal: TerminalConfig = field(default_factory=TerminalConfig)
    tmux: TmuxConfig = field(default_factory=TmuxConfig)
    input: InputConfig = field(default_factory=InputConfig)
    state_detection: StateDetectionConfig = field(default_factory=StateDetectionConfig)
    transcript: TranscriptConfig = field(default_factory=TranscriptConfig)

    def __post_init__(self) -> None:
        if self.transcript.db_path is None:
            self.transcript.db_path = self.state_dir / "transcripts.sqlite"


def _path_from_env(name: str) -> Path | None:
    value = os.getenv(name)
    if not value:
        return None
    return Path(value).expanduser()


def _bool_from_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def _int_from_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return int(value)


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


def _csv_env(name: str, default: list[str]) -> list[str]:
    value = os.getenv(name)
    if not value:
        return list(default)
    return [item.strip() for item in value.split(",") if item.strip()]


def load_config() -> AppConfig:
    config_dir = _path_from_env("CODING_PET_CONFIG_DIR")
    state_dir = _path_from_env("CODING_PET_STATE_DIR")
    runtime_dir = _path_from_env("CODING_PET_RUNTIME_DIR")
    log_dir = _path_from_env("CODING_PET_LOG_DIR")
    state_file = _path_from_env("CODING_PET_STATE_FILE")

    resolved_config_dir = config_dir or (_xdg_dir("XDG_CONFIG_HOME", ".config") / APP_NAME)
    resolved_state_dir = state_dir or (_xdg_dir("XDG_STATE_HOME", ".local/state") / APP_NAME)
    runtime_root = runtime_dir or _path_from_env("XDG_RUNTIME_DIR") or _default_runtime_root()
    resolved_runtime_dir = (
        runtime_root / APP_NAME
        if runtime_root is not None
        else resolved_state_dir / "runtime"
    )
    resolved_log_dir = log_dir or (resolved_state_dir / "logs")
    resolved_state_file = state_file or (resolved_state_dir / "state.json")

    tmux_defaults = TmuxConfig()
    tmux = TmuxConfig(
        enabled=_bool_from_env("CODING_PET_TMUX_ENABLED", tmux_defaults.enabled),
        poll_interval_ms=_int_from_env(
            "CODING_PET_TMUX_POLL_INTERVAL_MS", tmux_defaults.poll_interval_ms
        ),
        capture_lines=_int_from_env("CODING_PET_TMUX_CAPTURE_LINES", tmux_defaults.capture_lines),
        include_session_patterns=_csv_env(
            "CODING_PET_TMUX_INCLUDE_SESSION_PATTERNS",
            tmux_defaults.include_session_patterns,
        ),
        include_commands=_csv_env(
            "CODING_PET_TMUX_INCLUDE_COMMANDS",
            tmux_defaults.include_commands,
        ),
        exclude_session_patterns=_csv_env(
            "CODING_PET_TMUX_EXCLUDE_SESSION_PATTERNS",
            tmux_defaults.exclude_session_patterns,
        ),
    )
    transcript = TranscriptConfig(
        enabled=_bool_from_env("CODING_PET_TRANSCRIPT_ENABLED", True),
        max_events_per_session=_int_from_env("CODING_PET_TRANSCRIPT_MAX_EVENTS", 5000),
        db_path=_path_from_env("CODING_PET_TRANSCRIPT_DB")
        or (resolved_state_dir / "transcripts.sqlite"),
    )
    state_detection = StateDetectionConfig(
        stalled_after_sec=_int_from_env("CODING_PET_STALLED_AFTER_SEC", 300),
        waiting_after_idle_sec=_int_from_env("CODING_PET_WAITING_AFTER_IDLE_SEC", 5),
        manual_override=_bool_from_env("CODING_PET_MANUAL_OVERRIDE", True),
    )
    terminal = TerminalConfig(attach_command=os.getenv("CODING_PET_ATTACH_COMMAND") or None)

    return AppConfig(
        config_dir=resolved_config_dir,
        state_dir=resolved_state_dir,
        runtime_dir=resolved_runtime_dir,
        log_dir=resolved_log_dir,
        state_file=resolved_state_file,
        log_level=os.getenv("CODING_PET_LOG_LEVEL", "INFO").upper(),
        capture_transcripts=os.getenv("CODING_PET_CAPTURE_TRANSCRIPTS", "false").lower()
        in {"1", "true", "yes", "on"},
        notification_cooldown_seconds=int(
            os.getenv("CODING_PET_NOTIFICATION_COOLDOWN_SECONDS", "60")
        ),
        tmux=tmux,
        transcript=transcript,
        state_detection=state_detection,
        terminal=terminal,
    )
