from __future__ import annotations

from pathlib import Path

import pytest

from coding_pet.tmux.client import TmuxClient, TmuxCommandError, TmuxCommandResult
from coding_pet.tmux.control import send_raw_text_to_tmux_pane


class CapturingRunner:
    def __init__(self, *, fail_on: str | None = None) -> None:
        self.calls: list[list[str]] = []
        self.loaded_texts: list[str] = []
        self.fail_on = fail_on

    def run(self, argv: list[str]) -> TmuxCommandResult:
        self.calls.append(argv)
        if argv[1] == "load-buffer":
            self.loaded_texts.append(Path(argv[-1]).read_text(encoding="utf-8"))
        if self.fail_on is not None and self.fail_on in argv:
            return TmuxCommandResult(stderr="boom", returncode=1)
        return TmuxCommandResult()


def test_send_raw_text_to_tmux_pane_preserves_korean_multiline_and_shell_chars() -> None:
    runner = CapturingRunner()
    client = TmuxClient(runner=runner)
    text = "  stage 환경 기준으로 계속해줘\nquote='x' $HOME ; \\ done  "

    send_raw_text_to_tmux_pane("%3", text, press_enter=True, client=client)

    assert runner.loaded_texts == [text]
    assert [call[1] for call in runner.calls[:3]] == ["load-buffer", "paste-buffer", "send-keys"]
    assert runner.calls[1][1:] == ["paste-buffer", "-t", "%3", "-b", runner.calls[0][3]]
    assert runner.calls[2] == ["tmux", "send-keys", "-t", "%3", "Enter"]


def test_send_raw_text_to_tmux_pane_can_omit_enter() -> None:
    runner = CapturingRunner()
    client = TmuxClient(runner=runner)

    send_raw_text_to_tmux_pane("%3", "hello", press_enter=False, client=client)

    assert "send-keys" not in [call[1] for call in runner.calls]


def test_send_raw_text_to_tmux_pane_cleans_temp_file_on_failure(tmp_path: Path) -> None:
    runner = CapturingRunner(fail_on="paste-buffer")
    client = TmuxClient(runner=runner)

    with pytest.raises(TmuxCommandError):
        send_raw_text_to_tmux_pane("%3", "hello", client=client, temp_dir=tmp_path)

    assert list(tmp_path.iterdir()) == []
