from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from coding_pet.cli import app

runner = CliRunner()


def test_daemon_run_reports_runtime_details_and_can_exit_immediately(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("CODING_PET_DAEMON_ONESHOT", "1")

    result = runner.invoke(app, ["daemon", "run"])

    assert result.exit_code == 0
    assert "coding-pet daemon ready" in result.stdout.lower()
    assert "state_file=" in result.stdout


def test_widget_run_reports_environment_status(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))

    result = runner.invoke(app, ["widget", "run"])

    assert result.exit_code == 0
    assert "coding-pet widget" in result.stdout.lower()
    assert "live_mode=false" in result.stdout.lower()


def test_widget_run_reports_live_mode_when_socket_exists(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    runtime_dir = tmp_path / ".local/state" / "coding-pet" / "runtime"
    runtime_dir.mkdir(parents=True)
    (runtime_dir / "coding-pet.sock").write_text("placeholder", encoding="utf-8")

    result = runner.invoke(app, ["widget", "run"])

    assert result.exit_code == 0
    assert "live_mode=true" in result.stdout.lower()


def test_daemon_monitor_fails_fast_when_backend_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(
        "coding_pet.agents.registry.shutil.which",
        lambda name: None if name == "claude" else "/usr/bin/fake",
    )

    called = False

    async def fake_monitor_command(*args: object, **kwargs: object) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr("coding_pet.cli.DaemonApp.monitor_command", fake_monitor_command)

    result = runner.invoke(
        app,
        [
            "daemon",
            "monitor",
            "--agent",
            "claude_code",
            "--cmd",
            "python -c pass",
            "--workspace",
            str(tmp_path),
        ],
    )

    assert result.exit_code != 0
    assert called is False
    assert "backend claude_code is unavailable" in result.stdout.lower()


def test_admin_doctor_reports_path_and_runtime_health(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("CODING_PET_LOG_LEVEL", "debug")
    monkeypatch.setattr(
        "coding_pet.agents.registry.shutil.which",
        lambda name: None if name in {"claude", "opencode", "notify-send"} else "/usr/bin/fake",
    )
    monkeypatch.setattr("coding_pet.cli.os.access", lambda path, mode: path != tmp_path / "blocked")

    runtime_dir = tmp_path / ".local/state" / "coding-pet" / "runtime"
    runtime_dir.mkdir(parents=True)
    (runtime_dir / "coding-pet.sock").write_text("placeholder", encoding="utf-8")

    result = runner.invoke(app, ["admin", "doctor"])

    assert result.exit_code == 0
    assert "runtime_socket_exists=true" in result.stdout
    assert "notify_send=unavailable" in result.stdout
    assert "path_status_config_dir=missing,writable_parent=true" in result.stdout
    assert "path_status_runtime_dir=exists,writable_parent=true" in result.stdout
    assert "gui_runtime=unavailable" in result.stdout.lower()
    assert "assets_root=" in result.stdout
    assert "theme=company-pet" in result.stdout
    assert "theme_missing_assets=none" in result.stdout
    assert "theme_registry_count=22" in result.stdout
    assert "theme_spritecollab_count=20" in result.stdout


def test_admin_doctor_prints_live_configuration(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("CODING_PET_LOG_LEVEL", "debug")
    monkeypatch.setattr(
        "coding_pet.agents.registry.shutil.which",
        lambda name: None if name in {"claude", "opencode"} else "/usr/bin/fake",
    )

    result = runner.invoke(app, ["admin", "doctor"])

    assert result.exit_code == 0
    assert "config_dir=" in result.stdout
    assert "state_dir=" in result.stdout
    assert "runtime_dir=" in result.stdout
    assert "log_level=DEBUG" in result.stdout
    assert "backend_claude_code=unavailable:not installed (missing 'claude')" in result.stdout
    assert "backend_opencode=unavailable:not installed (missing 'opencode')" in result.stdout



def test_daemon_discover_tmux_lists_matched_and_ignored_panes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from coding_pet.tmux.models import TmuxPaneInfo

    monkeypatch.setenv("HOME", str(tmp_path))

    class FakeTmuxClient:
        def list_panes(self) -> list[TmuxPaneInfo]:
            return [
                TmuxPaneInfo("%3", "claude-auth", "0.0", "claude", "/proj/ws/auth", "claude-auth"),
                TmuxPaneInfo("%7", "shell", "0.0", "bash", "/tmp", "debug"),
            ]

    monkeypatch.setattr("coding_pet.cli.TmuxClient", lambda: FakeTmuxClient())

    result = runner.invoke(app, ["daemon", "discover-tmux"])

    assert result.exit_code == 0
    assert "%3  claude-auth" in result.stdout
    assert "claude_code" in result.stdout
    assert "matched" in result.stdout
    assert "%7  shell" in result.stdout
    assert "ignored:no matching agent rule" in result.stdout


def test_daemon_monitor_tmux_captures_and_classifies_single_pane(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from coding_pet.tmux.models import TmuxPaneInfo

    monkeypatch.setenv("HOME", str(tmp_path))

    class FakeTmuxClient:
        def list_panes(self) -> list[TmuxPaneInfo]:
            return [
                TmuxPaneInfo("%3", "manual", "0.0", "bash", "/proj/ws/auth", None),
            ]

        def capture_pane(self, pane_id: str, *, lines: int) -> str:
            assert pane_id == "%3"
            assert lines == 200
            return "Need clarification: which env?"

    monkeypatch.setattr("coding_pet.cli.TmuxClient", lambda: FakeTmuxClient())

    result = runner.invoke(
        app,
        [
            "daemon",
            "monitor-tmux",
            "--pane",
            "%3",
            "--agent",
            "claude_code",
            "--title",
            "auth-fix",
        ],
    )

    assert result.exit_code == 0
    assert "captured tmux pane %3" in result.stdout.lower()
    assert "state=needs_input" in result.stdout
    assert "session_id=tmux-%3" in result.stdout


def test_admin_doctor_reports_tmux_and_transcript_health(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("CODING_PET_TMUX_ENABLED", "1")
    monkeypatch.setattr(
        "coding_pet.agents.registry.shutil.which",
        lambda name: None if name in {"claude", "opencode"} else "/usr/bin/fake",
    )
    monkeypatch.setattr(
        "coding_pet.cli.shutil.which",
        lambda name: "/usr/bin/tmux" if name == "tmux" else None,
    )

    result = runner.invoke(app, ["admin", "doctor"])

    assert result.exit_code == 0
    assert "tmux_binary=/usr/bin/tmux" in result.stdout
    assert "tmux_enabled=true" in result.stdout
    assert "transcript_db=" in result.stdout
