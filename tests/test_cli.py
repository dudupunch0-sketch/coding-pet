from __future__ import annotations

from typer.testing import CliRunner

from coding_pet.cli import app

runner = CliRunner()


def test_daemon_run_reports_runtime_details_and_can_exit_immediately(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("CODING_PET_DAEMON_ONESHOT", "1")

    result = runner.invoke(app, ["daemon", "run"])

    assert result.exit_code == 0
    assert "coding-pet daemon ready" in result.stdout.lower()
    assert "state_file=" in result.stdout


def test_widget_run_reports_environment_status(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))

    result = runner.invoke(app, ["widget", "run"])

    assert result.exit_code == 0
    assert "coding-pet widget" in result.stdout.lower()


def test_admin_doctor_prints_live_configuration(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("CODING_PET_LOG_LEVEL", "debug")

    result = runner.invoke(app, ["admin", "doctor"])

    assert result.exit_code == 0
    assert "config_dir=" in result.stdout
    assert "state_dir=" in result.stdout
    assert "runtime_dir=" in result.stdout
    assert "log_level=DEBUG" in result.stdout
