from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path

from coding_pet.hooks import hook_script_source


def _write_executable(path: Path, source: str) -> None:
    path.write_text(source, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _write_capture_bin(path: Path, output_path: Path) -> None:
    _write_executable(
        path,
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "import json, os, sys",
                f"path = {str(output_path)!r}",
                "open(path, 'w', encoding='utf-8').write(json.dumps(sys.argv[1:]))",
                "",
            ]
        ),
    )


def test_hook_script_extracts_common_json_payload_aliases(tmp_path: Path) -> None:
    hook_script = tmp_path / "coding-pet-hook.sh"
    capture_bin = tmp_path / "capture-coding-pet"
    captured_args = tmp_path / "captured-args.json"
    _write_executable(hook_script, hook_script_source())
    _write_capture_bin(capture_bin, captured_args)
    payload = {
        "sessionId": "sid-42",
        "workspace": {"path": "/proj/ws"},
        "title": "Claude hook title",
        "summary": "approval requested",
    }
    env = {
        **os.environ,
        "CODING_PET_BIN": str(capture_bin),
        "PYTHON": os.environ.get("PYTHON", "python3"),
    }

    result = subprocess.run(
        [str(hook_script), "claude_code", "PermissionRequest"],
        input=json.dumps(payload),
        text=True,
        env=env,
        cwd=tmp_path,
        check=False,
        capture_output=True,
    )

    assert result.returncode == 0
    args = json.loads(captured_args.read_text("utf-8"))
    assert args == [
        "daemon",
        "hook-event",
        "--agent",
        "claude_code",
        "--event",
        "PermissionRequest",
        "--session-id",
        "sid-42",
        "--workspace",
        "/proj/ws",
        "--title",
        "Claude hook title",
        "--summary",
        "approval requested",
    ]


def test_hook_script_environment_overrides_json_payload(tmp_path: Path) -> None:
    hook_script = tmp_path / "coding-pet-hook.sh"
    capture_bin = tmp_path / "capture-coding-pet"
    captured_args = tmp_path / "captured-args.json"
    _write_executable(hook_script, hook_script_source())
    _write_capture_bin(capture_bin, captured_args)
    payload = {
        "session_id": "payload-session",
        "cwd": "/payload/ws",
        "title": "payload title",
        "summary": "payload summary",
    }
    env = {
        **os.environ,
        "CODING_PET_BIN": str(capture_bin),
        "CODING_PET_HOOK_SESSION_ID": "env-session",
        "CODING_PET_HOOK_WORKSPACE": "/env/ws",
        "CODING_PET_HOOK_TITLE": "env title",
        "CODING_PET_HOOK_SUMMARY": "env summary",
        "PYTHON": os.environ.get("PYTHON", "python3"),
    }

    result = subprocess.run(
        [str(hook_script), "opencode", "tool.execute.before"],
        input=json.dumps(payload),
        text=True,
        env=env,
        cwd=tmp_path,
        check=False,
        capture_output=True,
    )

    assert result.returncode == 0
    args = json.loads(captured_args.read_text("utf-8"))
    assert args[args.index("--session-id") + 1] == "env-session"
    assert args[args.index("--workspace") + 1] == "/env/ws"
    assert args[args.index("--title") + 1] == "env title"
    assert args[args.index("--summary") + 1] == "env summary"
