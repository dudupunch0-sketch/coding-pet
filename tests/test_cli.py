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
