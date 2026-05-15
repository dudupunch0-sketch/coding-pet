from __future__ import annotations

import tempfile
import uuid
from pathlib import Path

from coding_pet.tmux.client import TmuxClient, TmuxCommandError


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
