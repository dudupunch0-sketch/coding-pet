from __future__ import annotations

import pytest

from coding_pet.tmux.client import TmuxClient, TmuxCommandError, TmuxCommandResult


class FakeRunner:
    def __init__(self, result: TmuxCommandResult) -> None:
        self.result = result
        self.calls: list[list[str]] = []

    def run(self, argv: list[str]) -> TmuxCommandResult:
        self.calls.append(argv)
        return self.result


def test_tmux_client_list_panes_uses_expected_format() -> None:
    runner = FakeRunner(TmuxCommandResult(stdout="%3|s|0.0|claude|/tmp|t\n"))
    client = TmuxClient(runner=runner)

    panes = client.list_panes()

    assert panes[0].pane_id == "%3"
    assert runner.calls == [[
        "tmux",
        "list-panes",
        "-a",
        "-F",
        "#{pane_id}|#{session_name}|#{window_index}.#{pane_index}|#{pane_current_command}|#{pane_current_path}|#{pane_title}",
    ]]


def test_tmux_client_capture_pane_uses_joined_recent_lines() -> None:
    runner = FakeRunner(TmuxCommandResult(stdout="screen"))
    client = TmuxClient(runner=runner)

    assert client.capture_pane("%3", lines=200) == "screen"
    assert runner.calls == [["tmux", "capture-pane", "-t", "%3", "-p", "-J", "-S", "-200"]]


def test_tmux_client_raises_command_error_with_stderr() -> None:
    runner = FakeRunner(TmuxCommandResult(stdout="", stderr="no server", returncode=1))
    client = TmuxClient(runner=runner)

    with pytest.raises(TmuxCommandError, match="no server"):
        client.list_panes()
