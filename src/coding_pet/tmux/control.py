from __future__ import annotations

import shlex
import sys
import tempfile
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

from coding_pet.tmux.client import TmuxClient, TmuxCommandError

DEFAULT_TMUX_CONTROL_CHECK_TEXT = "coding-pet probe\n한글 $HOME ; \\\\ \"quote\""


@dataclass(frozen=True, slots=True)
class TmuxControlCheckResult:
    ok: bool
    session_name: str
    pane_id: str | None
    expected_text: str
    observed_text: str | None
    detail: str

    def as_report(self) -> dict[str, object]:
        return asdict(self)


def _buffer_name_for(pane_id: str) -> str:
    sanitized = "".join(char if char.isalnum() else "-" for char in pane_id).strip("-")
    return f"coding-pet-input-{sanitized}-{uuid.uuid4().hex[:8]}"


def send_raw_text_to_tmux_pane(
    pane_id: str,
    text: str,
    *,
    press_enter: bool = True,
    client: TmuxClient | None = None,
    temp_dir: Path | None = None,
) -> None:
    tmux_client = client or TmuxClient()
    buffer_name = _buffer_name_for(pane_id)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            delete=False,
            dir=temp_dir,
        ) as handle:
            handle.write(text)
            temp_path = Path(handle.name)

        tmux_client.run(["load-buffer", "-b", buffer_name, str(temp_path)])
        tmux_client.run(["paste-buffer", "-t", pane_id, "-b", buffer_name])
        if press_enter:
            tmux_client.run(["send-keys", "-t", pane_id, "Enter"])
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        try:
            tmux_client.run(["delete-buffer", "-b", buffer_name])
        except TmuxCommandError:
            pass


def run_tmux_control_check(
    *,
    text: str = DEFAULT_TMUX_CONTROL_CHECK_TEXT,
    timeout_s: float = 5.0,
    client: TmuxClient | None = None,
    temp_dir: Path | None = None,
) -> TmuxControlCheckResult:
    tmux_client = client or TmuxClient()
    session_name = f"coding-pet-probe-{uuid.uuid4().hex[:8]}"
    pane_id: str | None = None
    timeout = max(0.1, timeout_s)
    with tempfile.TemporaryDirectory(prefix="coding-pet-tmux-probe-", dir=temp_dir) as tmp:
        work_dir = Path(tmp)
        reader_script = work_dir / "read_stdin.py"
        output_file = work_dir / "input.bin"
        reader_script.write_text(
            (
                "from pathlib import Path\n"
                "import sys\n"
                "Path(sys.argv[1]).write_bytes(sys.stdin.buffer.read())\n"
            ),
            encoding="utf-8",
        )
        command = " ".join(
            shlex.quote(part)
            for part in (sys.executable, str(reader_script), str(output_file))
        )
        try:
            tmux_client.run(["new-session", "-d", "-s", session_name, command])
            pane_id = _wait_for_probe_pane(tmux_client, session_name, timeout_s=timeout)
            send_raw_text_to_tmux_pane(pane_id, text, press_enter=False, client=tmux_client)
            tmux_client.run(["send-keys", "-t", pane_id, "C-d"])
            tmux_client.run(["send-keys", "-t", pane_id, "C-d"])
            observed = _wait_for_probe_output(output_file, timeout_s=timeout)
        except Exception as exc:  # noqa: BLE001
            return TmuxControlCheckResult(
                ok=False,
                session_name=session_name,
                pane_id=pane_id,
                expected_text=text,
                observed_text=None,
                detail=str(exc),
            )
        finally:
            try:
                tmux_client.run(["kill-session", "-t", session_name])
            except Exception:  # noqa: BLE001
                pass

        ok = observed == text
        return TmuxControlCheckResult(
            ok=ok,
            session_name=session_name,
            pane_id=pane_id,
            expected_text=text,
            observed_text=observed,
            detail="raw tmux input preserved" if ok else "raw tmux input mismatch",
        )


def _wait_for_probe_pane(
    client: TmuxClient,
    session_name: str,
    *,
    timeout_s: float,
) -> str:
    deadline = time.monotonic() + timeout_s
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            output = client.run(["list-panes", "-t", session_name, "-F", "#{pane_id}"]).stdout
            pane_id = output.strip().splitlines()[0]
            if pane_id:
                return pane_id
        except Exception as exc:  # noqa: BLE001
            last_error = exc
        time.sleep(0.05)
    if last_error is not None:
        raise TimeoutError(f"tmux probe pane did not appear: {last_error}") from last_error
    raise TimeoutError("tmux probe pane did not appear")


def _wait_for_probe_output(output_file: Path, *, timeout_s: float) -> str:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if output_file.exists():
            return output_file.read_bytes().decode("utf-8")
        time.sleep(0.05)
    raise TimeoutError("tmux probe did not write captured input")
