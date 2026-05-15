from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import Protocol

from coding_pet.tmux.discovery import parse_list_panes_output
from coding_pet.tmux.models import TmuxPaneInfo

LIST_PANES_FORMAT = (
    "#{pane_id}|#{session_name}|#{window_index}.#{pane_index}|"
    "#{pane_current_command}|#{pane_current_path}|#{pane_title}"
)


@dataclass(frozen=True, slots=True)
class TmuxCommandResult:
    stdout: str = ""
    stderr: str = ""
    returncode: int = 0


class TmuxRunner(Protocol):
    def run(self, argv: list[str]) -> TmuxCommandResult: ...


class TmuxCommandError(RuntimeError):
    def __init__(self, argv: list[str], result: TmuxCommandResult) -> None:
        detail = result.stderr.strip() or result.stdout.strip() or f"exit code {result.returncode}"
        super().__init__(f"tmux command failed: {' '.join(argv)}: {detail}")
        self.argv = argv
        self.result = result


class TmuxBinaryUnavailable(RuntimeError):
    pass


class SubprocessTmuxRunner:
    def run(self, argv: list[str]) -> TmuxCommandResult:
        try:
            completed = subprocess.run(
                argv,
                check=False,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError as exc:
            raise TmuxBinaryUnavailable(str(exc)) from exc
        return TmuxCommandResult(
            stdout=completed.stdout,
            stderr=completed.stderr,
            returncode=completed.returncode,
        )


class TmuxClient:
    def __init__(self, *, binary: str = "tmux", runner: TmuxRunner | None = None) -> None:
        self.binary = binary
        self.runner = runner or SubprocessTmuxRunner()

    def run(self, args: list[str]) -> TmuxCommandResult:
        argv = [self.binary, *args]
        result = self.runner.run(argv)
        if result.returncode != 0:
            raise TmuxCommandError(argv, result)
        return result

    def list_panes_text(self) -> str:
        return self.run(["list-panes", "-a", "-F", LIST_PANES_FORMAT]).stdout

    def list_panes(self) -> list[TmuxPaneInfo]:
        return parse_list_panes_output(self.list_panes_text())

    def capture_pane(self, pane_id: str, *, lines: int = 200) -> str:
        return self.run(
            ["capture-pane", "-t", pane_id, "-p", "-J", "-S", f"-{lines}"]
        ).stdout
