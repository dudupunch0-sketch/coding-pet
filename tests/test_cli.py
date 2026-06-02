from __future__ import annotations

import hashlib
import json
import struct
import zipfile
import zlib
from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from coding_pet.cli import app
from coding_pet.transcripts.model import TranscriptEvent

runner = CliRunner()


def write_webp_header(path: Path, *, width: int = 1536, height: int = 1872) -> None:
    from PIL import Image, ImageDraw

    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    columns = max(1, width // 192)
    rows = max(1, height // 208)
    for row, used_columns in _atlas_test_row_counts(columns=columns, rows=rows).items():
        for column in range(used_columns):
            left = column * 192 + 72
            top = row * 208 + 80
            draw.rectangle(
                (left, top, left + 40, top + 40),
                fill=(255, 96 + column, 32 + row, 255),
            )
    image.save(path, "WEBP", lossless=True, exact=True)


def write_pet_zip(source_dir: Path, archive_path: Path, *, top_level: str | None = None) -> None:
    with zipfile.ZipFile(archive_path, "w") as archive:
        for path in sorted(source_dir.rglob("*")):
            if path.is_dir():
                continue
            relative = path.relative_to(source_dir).as_posix()
            archive_name = f"{top_level}/{relative}" if top_level is not None else relative
            archive.write(path, archive_name)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _atlas_test_row_counts(*, columns: int, rows: int) -> dict[int, int]:
    if columns == 8 and rows == 9:
        return {
            0: 6,
            1: 8,
            2: 8,
            3: 4,
            4: 5,
            5: 8,
            6: 6,
            7: 6,
            8: 6,
        }
    if columns == 9 and rows == 8:
        return {row: 6 for row in range(rows)}
    return {row: min(6, columns) for row in range(rows)}


REQUIRED_CODING_PET_WHEEL_SUFFIXES = (
    "share/coding-pet/assets/sprites/theme-manifest.json",
    "share/coding-pet/assets/sprites/theme-registry.json",
    "share/coding-pet/assets/sprites/codex-default/idle.png",
    "share/coding-pet/assets/sprites/codex-default/thinking.png",
    "share/coding-pet/docs/operations/rhel8-setup.md",
    "share/coding-pet/docs/operations/offline-rhel8-wheelhouse.md",
    "share/coding-pet/docs/operations/codex-pet-packages.md",
    "share/coding-pet/requirements.txt",
    "share/coding-pet/requirements/constraints-rhel8.txt",
    "share/coding-pet/requirements/rhel8-runtime.txt",
    "share/coding-pet/requirements/rhel8-dev.txt",
    "share/coding-pet/systemd/coding-pet-daemon.service",
    "share/coding-pet/systemd/coding-pet-widget.service",
    "share/coding-pet/systemd/coding-pet.target",
    "share/coding-pet/systemd/coding-pet.service.env.example",
)


def write_coding_pet_wheel(path: Path, *, omit: set[str] | None = None) -> None:
    omitted = omit or set()
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("coding_pet/__init__.py", "")
        archive.writestr("coding_pet-0.1.0.dist-info/METADATA", "Name: coding-pet\n")
        for suffix in REQUIRED_CODING_PET_WHEEL_SUFFIXES:
            if suffix in omitted:
                continue
            archive.writestr(f"coding_pet-0.1.0.data/data/{suffix}", "placeholder\n")


def write_placeholder_wheel(path: Path) -> None:
    if path.name.startswith("coding_pet-"):
        write_coding_pet_wheel(path)
    else:
        path.write_text("placeholder", encoding="utf-8")


def write_solid_png(path: Path, *, width: int, height: int) -> None:
    row = b"\x00" + (b"\x00\x00\x00\x00" * width)
    raw = row * height
    compressed = zlib.compress(raw)
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + png_chunk(b"IHDR", ihdr)
        + png_chunk(b"IDAT", compressed)
        + png_chunk(b"IEND", b"")
    )


def png_chunk(kind: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + kind
        + data
        + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    )


def _target_acceptance_report() -> dict[str, object]:
    required_checks = (
        "python",
        "linux",
        "glibc",
        "rhel_8_10",
        "dependency_pydantic",
        "dependency_typer",
        "dependency_pillow",
        "gui_runtime",
        "tmux",
        "theme",
        "path_config_dir",
        "path_state_dir",
        "path_runtime_dir",
        "path_log_dir",
        "path_state_file",
        "backend_claude_code",
        "backend_opencode",
    )
    return {
        "schema_version": 1,
        "ok": True,
        "profile": "target",
        "generated_at": datetime.now(UTC).isoformat(),
        "failed_required": [],
        "checks": [
            {"name": name, "ok": True, "required": True, "detail": "ok"} for name in required_checks
        ],
    }


def _target_environment_report() -> dict[str, object]:
    return {
        "schema_version": 1,
        "profile": "target",
        "generated_at": datetime.now(UTC).isoformat(),
        "python": {
            "version": "3.12.3",
            "executable": "/opt/coding-pet/.venv/bin/python",
        },
        "platform": {
            "system": "Linux",
            "platform": "Linux-4.18.0-rhel8-x86_64-with-glibc2.28",
            "machine": "x86_64",
            "release": "4.18.0-553.el8_10.x86_64",
        },
        "libc": {"name": "glibc", "version": "2.28"},
        "redhat_release": "Red Hat Enterprise Linux release 8.10 (Ootpa)",
        "gui_runtime": "available",
        "tmux_binary": "/usr/bin/tmux",
        "notify_send": "/usr/bin/notify-send",
        "paths": {
            "config_dir": "/home/user/.config/coding-pet",
            "state_dir": "/home/user/.local/state/coding-pet",
            "runtime_dir": "/run/user/1000/coding-pet",
            "state_file": "/home/user/.local/state/coding-pet/state.json",
            "log_dir": "/home/user/.local/state/coding-pet/logs",
            "transcript_db": "/home/user/.local/state/coding-pet/transcripts.sqlite",
        },
        "transcript": {
            "enabled": True,
            "backend": "sqlite",
            "db_path": "/home/user/.local/state/coding-pet/transcripts.sqlite",
            "max_events_per_session": 5000,
            "redact_secrets": True,
        },
        "theme": {"name": "codex-default", "ok": True, "detail": "codex-default:coding_pet"},
        "backends": [
            {
                "agent_kind": "claude_code",
                "available": True,
                "binary_name": "claude",
                "binary_path": "/usr/bin/claude",
                "reason": "available at /usr/bin/claude",
                "control_messages": {"approve": "approve", "reject": "reject"},
            },
            {
                "agent_kind": "opencode",
                "available": True,
                "binary_name": "opencode",
                "binary_path": "/usr/bin/opencode",
                "reason": "available at /usr/bin/opencode",
                "control_messages": {"approve": "approve", "reject": "reject"},
            },
        ],
    }


def _successful_hook_event_smoke_report(*, required: bool) -> dict[str, object]:
    return {
        "schema_version": 1,
        "ok": True,
        "required": required,
        "skipped": False,
        "generated_at": datetime.now(UTC).isoformat(),
        "socket_path": "/run/user/1000/coding-pet/coding-pet.sock",
        "event": {
            "agent": "claude_code",
            "event": "PreToolUse",
            "session_id": "coding-pet-hook-smoke",
            "workspace": "/tmp/coding-pet-target-evidence",
        },
        "hook_result": {
            "ok": True,
            "session_id": "hook-claude_code-coding-pet-hook-smoke",
            "state": "running",
        },
        "transcript": {
            "enabled": True,
            "verified": True,
            "session_id": "hook-claude_code-coding-pet-hook-smoke",
            "db_path": "/home/user/.local/state/coding-pet/transcripts.sqlite",
            "events": 1,
        },
        "cleanup_result": {
            "ok": True,
            "outcome": "local_updated",
            "action": "hide_pet",
            "session_id": "hook-claude_code-coding-pet-hook-smoke",
            "reason": "hidden",
            "detail": "session hidden",
        },
        "errors": [],
    }


def _write_complete_target_evidence_bundle(
    evidence_dir: Path,
    *,
    acceptance: dict[str, object] | None = None,
    environment: dict[str, object] | None = None,
) -> None:
    evidence_dir.mkdir()
    required_distributions = [
        "coding-pet",
        "pydantic",
        "typer",
        "pillow",
        "pyside6",
        "pyside6-addons",
        "pyside6-essentials",
        "shiboken6",
    ]
    wheel_records = [
        {
            "filename": filename,
            "distribution": distribution,
            "sha256": hex_digit * 64,
            "size_bytes": 1024 + index,
        }
        for index, (filename, distribution, hex_digit) in enumerate(
            [
                ("coding_pet-0.1.0-py3-none-any.whl", "coding-pet", "a"),
                ("pydantic-2.11.9-py3-none-any.whl", "pydantic", "b"),
                ("typer-0.16.1-py3-none-any.whl", "typer", "c"),
                (
                    "Pillow-11.3.0-cp312-cp312-manylinux_2_28_x86_64.whl",
                    "pillow",
                    "d",
                ),
                ("PySide6-6.9.3-py3-none-any.whl", "pyside6", "e"),
                (
                    "PySide6_Addons-6.9.3-cp39-abi3-manylinux_2_28_x86_64.whl",
                    "pyside6-addons",
                    "f",
                ),
                (
                    "PySide6_Essentials-6.9.3-cp39-abi3-manylinux_2_28_x86_64.whl",
                    "pyside6-essentials",
                    "1",
                ),
                (
                    "shiboken6-6.9.3-cp39-abi3-manylinux_2_28_x86_64.whl",
                    "shiboken6",
                    "2",
                ),
            ]
        )
    ]
    summary_artifacts = {
        "environment": str(evidence_dir / "environment.json"),
        "acceptance": str(evidence_dir / "acceptance-target.json"),
        "tmux_control": str(evidence_dir / "tmux-control.json"),
        "systemd_units": str(evidence_dir / "systemd-units.json"),
        "systemd_runtime": str(evidence_dir / "systemd-runtime.json"),
        "widget_smoke": str(evidence_dir / "widget-smoke.json"),
        "wheelhouse": str(evidence_dir / "wheelhouse.json"),
        "pet_packages": str(evidence_dir / "pet-packages.json"),
        "agent_hooks": str(evidence_dir / "agent-hooks.json"),
        "hook_event_smoke": str(evidence_dir / "hook-event-smoke.json"),
        "backend_summary": str(evidence_dir / "backend-summary.json"),
        "backend_claude_code_send_reply": str(evidence_dir / "backend-claude_code-send_reply.json"),
        "backend_claude_code_approve": str(evidence_dir / "backend-claude_code-approve.json"),
        "backend_claude_code_reject": str(evidence_dir / "backend-claude_code-reject.json"),
        "backend_opencode_send_reply": str(evidence_dir / "backend-opencode-send_reply.json"),
        "backend_opencode_approve": str(evidence_dir / "backend-opencode-approve.json"),
        "backend_opencode_reject": str(evidence_dir / "backend-opencode-reject.json"),
    }
    (evidence_dir / "summary.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "ok": True,
                "profile": "target",
                "output_dir": str(evidence_dir),
                "generated_at": datetime.now(UTC).isoformat(),
                "failed_required": [],
                "artifacts": summary_artifacts,
            }
        ),
        encoding="utf-8",
    )
    (evidence_dir / "acceptance-target.json").write_text(
        json.dumps(acceptance or _target_acceptance_report()),
        encoding="utf-8",
    )
    (evidence_dir / "environment.json").write_text(
        json.dumps(environment or _target_environment_report()),
        encoding="utf-8",
    )
    (evidence_dir / "tmux-control.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "ok": True,
                "profile": "target",
                "required": True,
                "skipped": False,
                "generated_at": datetime.now(UTC).isoformat(),
                "session_name": "coding-pet-probe-target",
                "pane_id": "%9",
                "expected_text": 'coding-pet probe\n한글 $HOME ; \\\\ "quote"',
                "observed_text": 'coding-pet probe\n한글 $HOME ; \\\\ "quote"',
                "detail": "raw tmux input preserved",
            }
        ),
        encoding="utf-8",
    )
    (evidence_dir / "systemd-units.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "ok": True,
                "profile": "target",
                "required": True,
                "skipped": False,
                "generated_at": datetime.now(UTC).isoformat(),
                "units": [
                    "/opt/coding-pet/share/coding-pet/systemd/coding-pet-daemon.service",
                    "/opt/coding-pet/share/coding-pet/systemd/coding-pet-widget.service",
                    "/opt/coding-pet/share/coding-pet/systemd/coding-pet.target",
                ],
                "command": [
                    "/usr/bin/systemd-analyze",
                    "--user",
                    "verify",
                    "/opt/coding-pet/share/coding-pet/systemd/coding-pet-daemon.service",
                    "/opt/coding-pet/share/coding-pet/systemd/coding-pet-widget.service",
                    "/opt/coding-pet/share/coding-pet/systemd/coding-pet.target",
                ],
                "returncode": 0,
            }
        ),
        encoding="utf-8",
    )
    (evidence_dir / "systemd-runtime.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "ok": True,
                "profile": "target",
                "required": True,
                "skipped": False,
                "generated_at": datetime.now(UTC).isoformat(),
                "systemctl": "/usr/bin/systemctl",
                "session_environment": {
                    "has_display": True,
                    "has_wayland_display": False,
                    "has_xdg_runtime_dir": True,
                    "has_dbus_session_bus": True,
                    "DISPLAY": ":1",
                    "WAYLAND_DISPLAY": None,
                    "XDG_RUNTIME_DIR": "/run/user/1000",
                    "DBUS_SESSION_BUS_ADDRESS": "unix:path=/run/user/1000/bus",
                },
                "user_manager": {
                    "ok": True,
                    "returncode": 0,
                    "command": ["/usr/bin/systemctl", "--user", "status"],
                },
                "target_enabled": {
                    "unit": "coding-pet.target",
                    "state": "enabled",
                    "ok": True,
                    "returncode": 0,
                    "command": [
                        "/usr/bin/systemctl",
                        "--user",
                        "is-enabled",
                        "coding-pet.target",
                    ],
                },
                "units": [
                    {
                        "unit": "coding-pet-daemon.service",
                        "state": "active",
                        "ok": True,
                        "returncode": 0,
                        "command": [
                            "/usr/bin/systemctl",
                            "--user",
                            "is-active",
                            "coding-pet-daemon.service",
                        ],
                    },
                    {
                        "unit": "coding-pet-widget.service",
                        "state": "active",
                        "ok": True,
                        "returncode": 0,
                        "command": [
                            "/usr/bin/systemctl",
                            "--user",
                            "is-active",
                            "coding-pet-widget.service",
                        ],
                    },
                    {
                        "unit": "coding-pet.target",
                        "state": "active",
                        "ok": True,
                        "returncode": 0,
                        "command": [
                            "/usr/bin/systemctl",
                            "--user",
                            "is-active",
                            "coding-pet.target",
                        ],
                    },
                ],
                "errors": [],
            }
        ),
        encoding="utf-8",
    )
    (evidence_dir / "wheelhouse.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "ok": True,
                "profile": "target",
                "required": True,
                "skipped": False,
                "generated_at": datetime.now(UTC).isoformat(),
                "required_distributions": [
                    *required_distributions,
                ],
                "present_distributions": [
                    *required_distributions,
                ],
                "wheels": wheel_records,
                "install_smoke": {
                    "ok": True,
                    "skipped": False,
                    "stage": "import",
                    "detail": "offline wheelhouse install smoke passed",
                },
            }
        ),
        encoding="utf-8",
    )
    (evidence_dir / "pet-packages.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "ok": True,
                "profile": "target",
                "required": True,
                "skipped": False,
                "generated_at": datetime.now(UTC).isoformat(),
                "source": "/tmp/downloaded-pets",
                "total": 1,
                "passed": 1,
                "failed": 0,
                "pets": [
                    {
                        "ok": True,
                        "theme_id": "boba",
                        "source_package": "/tmp/downloaded-pets/boba.zip",
                        "manifest": "/tmp/downloaded-pets/boba/pet.json",
                        "theme_format": "codex_pet",
                        "spritesheet": "spritesheet.webp",
                        "atlas_size": {"width": 1536, "height": 1872},
                        "atlas_grid": {"columns": 8, "rows": 9},
                        "frame_size": {"width": 192, "height": 208},
                        "frame_counts_by_row": {
                            "0": 6,
                            "1": 8,
                            "2": 8,
                            "3": 4,
                            "4": 5,
                            "5": 8,
                            "6": 6,
                            "7": 6,
                            "8": 6,
                        },
                        "mood_rows": {
                            "alert": 6,
                            "celebrate": 4,
                            "idle": 0,
                            "sad": 5,
                            "sleepy": 0,
                            "thinking": 8,
                            "typing": 7,
                        },
                        "atlas_cells": {
                            "ok": True,
                            "errors": [],
                            "warnings": [],
                            "transparent_rgb_residue_pixels": 0,
                        },
                        "transfer": {
                            "kind": "file",
                            "sha256": "3" * 64,
                            "size_bytes": 4096,
                            "file_count": 1,
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (evidence_dir / "agent-hooks.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "ok": True,
                "profile": "target",
                "required": True,
                "generated_at": datetime.now(UTC).isoformat(),
                "hooks_dir": "/home/test/.config/coding-pet/hooks",
                "claude_settings": "/home/test/.claude/settings.json",
                "opencode_plugin": "/home/test/.config/opencode/plugins/coding-pet.js",
                "checks": [
                    {
                        "name": "hook_script",
                        "ok": True,
                        "required": True,
                        "detail": ("/home/test/.config/coding-pet/hooks/coding-pet-hook.sh"),
                    },
                    {
                        "name": "hook_script_smoke",
                        "ok": True,
                        "required": True,
                        "detail": (
                            "/home/test/.config/coding-pet/hooks/coding-pet-hook.sh:returncode=0"
                        ),
                    },
                    {
                        "name": "claude_settings",
                        "ok": True,
                        "required": True,
                        "detail": "/home/test/.claude/settings.json",
                    },
                    {
                        "name": "opencode_plugin",
                        "ok": True,
                        "required": True,
                        "detail": "/home/test/.config/opencode/plugins/coding-pet.js",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    (evidence_dir / "hook-event-smoke.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "ok": True,
                "profile": "target",
                "required": True,
                "skipped": False,
                "generated_at": datetime.now(UTC).isoformat(),
                "socket_path": "/run/user/1000/coding-pet/coding-pet.sock",
                "event": {
                    "agent": "claude_code",
                    "event": "PreToolUse",
                    "session_id": "coding-pet-hook-smoke",
                    "workspace": str(evidence_dir),
                },
                "hook_result": {
                    "ok": True,
                    "session_id": "hook-claude_code-coding-pet-hook-smoke",
                    "state": "running",
                },
                "transcript": {
                    "enabled": True,
                    "verified": True,
                    "session_id": "hook-claude_code-coding-pet-hook-smoke",
                    "db_path": "/home/user/.local/state/coding-pet/transcripts.sqlite",
                    "events": 1,
                },
                "cleanup_result": {
                    "ok": True,
                    "outcome": "local_updated",
                    "action": "hide_pet",
                    "session_id": "hook-claude_code-coding-pet-hook-smoke",
                    "reason": "hidden",
                    "detail": "session hidden",
                },
                "errors": [],
            }
        ),
        encoding="utf-8",
    )
    (evidence_dir / "widget-smoke.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "ok": True,
                "profile": "target",
                "required": True,
                "skipped": False,
                "generated_at": datetime.now(UTC).isoformat(),
                "gui_runtime": "available",
                "gui_validated": True,
                "theme": "codex-default",
                "theme_ok": True,
                "shell_created": True,
                "qt_widget_created": True,
                "sprite_asset": "/tmp/codex-default/alert.png",
                "presentation": {
                    "mood": "alert",
                    "bubble_text": "Widget smoke validation",
                },
                "available_actions": ["approve", "reject"],
                "action_surfaces": {
                    "needs_permission": {
                        "presentation": {
                            "mood": "alert",
                            "bubble_text": "Widget smoke validation",
                        },
                        "available_actions": ["approve", "reject"],
                        "reply_shortcuts": [],
                        "sprite_asset": "/tmp/codex-default/alert.png",
                    },
                    "needs_input": {
                        "presentation": {
                            "mood": "alert",
                            "bubble_text": "Widget input validation",
                        },
                        "available_actions": ["send_reply"],
                        "reply_shortcuts": ["keep going", "summarize shortly"],
                        "sprite_asset": "/tmp/codex-default/alert.png",
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    (evidence_dir / "backend-summary.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "ok": True,
                "profile": "target",
                "generated_at": datetime.now(UTC).isoformat(),
                "output_dir": str(evidence_dir),
                "reports": [
                    {
                        "schema_version": 1,
                        "ok": True,
                        "profile": "target",
                        "agent": agent,
                        "action": action,
                        "pane": f"%{agent}-{action}",
                        "report": str(evidence_dir / f"backend-{agent}-{action}.json"),
                        "expected_regex": "accepted",
                        "expected_delivered_text": {
                            "send_reply": "collected target evidence",
                            "approve": "approve",
                            "reject": "reject",
                        }[action],
                        "expected_outcome": "accepted",
                        "capability": {
                            "action": action,
                            "transport": "tmux_buffer",
                            "requires_text": action == "send_reply",
                            "press_enter_default": True,
                            "semantics": (
                                "agent_reply" if action == "send_reply" else "agent_control"
                            ),
                        },
                    }
                    for agent in ("claude_code", "opencode")
                    for action in ("send_reply", "approve", "reject")
                ],
            }
        ),
        encoding="utf-8",
    )
    for agent in ("claude_code", "opencode"):
        for action in ("send_reply", "approve", "reject"):
            delivered_text = {
                "send_reply": "collected target evidence",
                "approve": "approve",
                "reject": "reject",
            }[action]
            before_hash = hashlib.sha256(f"{agent}:{action}:before".encode()).hexdigest()
            after_hash = hashlib.sha256(f"{agent}:{action}:after".encode()).hexdigest()
            (evidence_dir / f"backend-{agent}-{action}.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "ok": True,
                        "profile": "target",
                        "agent": agent,
                        "action": action,
                        "pane": f"%{agent}-{action}",
                        "expected_regex": "accepted",
                        "matched_expected": True,
                        "output_changed": True,
                        "capability": {
                            "action": action,
                            "transport": "tmux_buffer",
                            "requires_text": action == "send_reply",
                            "press_enter_default": True,
                            "semantics": (
                                "agent_reply" if action == "send_reply" else "agent_control"
                            ),
                        },
                        "before_hash": before_hash,
                        "after_hash": after_hash,
                        "before_tail": f"waiting for {agent} {action}",
                        "after_tail": f"{agent} {action} accepted",
                        "action_result": {
                            "ok": True,
                            "outcome": "accepted",
                            "session_id": f"tmux-%{agent}-{action}",
                            "action": action,
                            "delivered_text": delivered_text,
                        },
                    }
                ),
                encoding="utf-8",
            )


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
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)

    result = runner.invoke(app, ["widget", "run"])

    assert result.exit_code == 0
    assert "coding-pet widget" in result.stdout.lower()
    assert "live_mode=false" in result.stdout.lower()


def test_widget_run_reports_live_mode_when_socket_exists(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from coding_pet.daemon.runtime import default_socket_path

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    monkeypatch.setattr("coding_pet.config._default_runtime_root", lambda: None)
    runtime_dir = tmp_path / ".local/state" / "coding-pet" / "runtime"
    runtime_dir.mkdir(parents=True)
    socket_path = default_socket_path(runtime_dir)
    socket_path.parent.mkdir(parents=True, exist_ok=True)
    socket_path.write_text("placeholder", encoding="utf-8")

    result = runner.invoke(app, ["widget", "run"])

    assert result.exit_code == 0
    assert "live_mode=true" in result.stdout.lower()


def test_admin_widget_smoke_check_writes_headless_shell_report(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setattr("coding_pet.cli._gui_runtime_status", lambda: "unavailable:no_display")
    report_path = tmp_path / "widget-smoke.json"

    result = runner.invoke(
        app,
        ["admin", "widget-smoke-check", "--json-out", str(report_path)],
    )
    report = json.loads(report_path.read_text("utf-8"))

    assert result.exit_code == 0
    assert "widget_smoke=ok" in result.stdout
    assert report["required"] is False
    assert report["gui_runtime"] == "unavailable:no_display"
    assert report["gui_validated"] is False
    assert report["shell_created"] is True
    assert report["sprite_asset"]
    assert report["available_actions"] == ["approve", "reject"]
    assert report["presentation"]["mood"] == "alert"
    assert report["presentation"]["bubble_text"]
    assert report["action_surfaces"]["needs_permission"]["available_actions"] == [
        "approve",
        "reject",
    ]
    assert report["action_surfaces"]["needs_input"]["available_actions"] == ["send_reply"]
    assert report["action_surfaces"]["needs_input"]["reply_shortcuts"]


def test_admin_widget_smoke_check_required_fails_without_gui(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setattr("coding_pet.cli._gui_runtime_status", lambda: "unavailable:no_display")
    report_path = tmp_path / "widget-smoke.json"

    result = runner.invoke(
        app,
        ["admin", "widget-smoke-check", "--required", "--json-out", str(report_path)],
    )
    report = json.loads(report_path.read_text("utf-8"))

    assert result.exit_code != 0
    assert "widget_smoke=failed" in result.stdout
    assert report["required"] is True
    assert report["ok"] is False
    assert "GUI validation required" in report["errors"]


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
    from coding_pet.daemon.runtime import default_socket_path

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    monkeypatch.setattr("coding_pet.config._default_runtime_root", lambda: None)
    monkeypatch.setenv("CODING_PET_LOG_LEVEL", "debug")
    monkeypatch.setattr(
        "coding_pet.agents.registry.shutil.which",
        lambda name: (
            None if name in {"claude", "opencode", "codex", "notify-send"} else "/usr/bin/fake"
        ),
    )
    monkeypatch.setattr("coding_pet.cli.os.access", lambda path, mode: path != tmp_path / "blocked")

    runtime_dir = tmp_path / ".local/state" / "coding-pet" / "runtime"
    runtime_dir.mkdir(parents=True)
    socket_path = default_socket_path(runtime_dir)
    socket_path.parent.mkdir(parents=True, exist_ok=True)
    socket_path.write_text("placeholder", encoding="utf-8")

    result = runner.invoke(app, ["admin", "doctor"])

    assert result.exit_code == 0
    assert f"runtime_socket={socket_path}" in result.stdout
    assert "runtime_socket_exists=true" in result.stdout
    assert "notify_send=unavailable" in result.stdout
    assert "path_status_config_dir=missing,writable_parent=true" in result.stdout
    assert "path_status_runtime_dir=exists,writable_parent=true" in result.stdout
    assert "gui_runtime=unavailable" in result.stdout.lower()
    assert "assets_root=" in result.stdout
    assert "theme=codex-default" in result.stdout
    assert "theme_missing_assets=none" in result.stdout
    assert "theme_registry_count=22" in result.stdout
    assert "theme_spritecollab_count=20" in result.stdout


def test_admin_doctor_prints_live_configuration(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("CODING_PET_LOG_LEVEL", "debug")
    monkeypatch.setenv("CODING_PET_SHOW_COMPLETED_FOR_SEC", "7")
    monkeypatch.setenv("CODING_PET_PROCESS_STOP_TIMEOUT_SEC", "5")
    monkeypatch.setattr(
        "coding_pet.agents.registry.shutil.which",
        lambda name: None if name in {"claude", "opencode", "codex"} else "/usr/bin/fake",
    )

    result = runner.invoke(app, ["admin", "doctor"])

    assert result.exit_code == 0
    assert "config_dir=" in result.stdout
    assert "state_dir=" in result.stdout
    assert "runtime_dir=" in result.stdout
    assert "log_level=DEBUG" in result.stdout
    assert "show_completed_for_sec=7" in result.stdout
    assert "process_stop_timeout_sec=5" in result.stdout
    assert "backend_claude_code=unavailable:not installed (missing 'claude')" in result.stdout
    assert "backend_opencode=unavailable:not installed (missing 'opencode')" in result.stdout
    assert "backend_codex=unavailable:not installed (missing 'codex')" in result.stdout


def test_admin_acceptance_check_current_profile_allows_optional_degraded_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setattr("coding_pet.cli._gui_runtime_status", lambda: "unavailable:no_display")
    monkeypatch.setattr("coding_pet.cli.shutil.which", lambda name: None)
    monkeypatch.setattr("coding_pet.agents.registry.shutil.which", lambda name: None)

    result = runner.invoke(app, ["admin", "acceptance-check", "--profile", "current"])

    assert result.exit_code == 0
    assert "profile=current" in result.stdout
    assert "check=python ok=true required=true" in result.stdout
    assert (
        "check=gui_runtime ok=false required=false detail=unavailable:no_display" in result.stdout
    )
    assert "check=backend_claude_code ok=false required=false" in result.stdout
    assert "overall=ok" in result.stdout


def test_admin_acceptance_check_writes_json_report_for_current_profile(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    monkeypatch.setattr("coding_pet.cli._gui_runtime_status", lambda: "unavailable:no_display")
    monkeypatch.setattr("coding_pet.cli.shutil.which", lambda name: None)
    monkeypatch.setattr("coding_pet.agents.registry.shutil.which", lambda name: None)
    report_path = tmp_path / "qa" / "acceptance-current.json"

    result = runner.invoke(
        app,
        [
            "admin",
            "acceptance-check",
            "--profile",
            "current",
            "--json-out",
            str(report_path),
        ],
    )

    report = json.loads(report_path.read_text("utf-8"))
    gui_check = next(check for check in report["checks"] if check["name"] == "gui_runtime")

    assert result.exit_code == 0
    assert report["ok"] is True
    assert report["profile"] == "current"
    assert report["failed_required"] == []
    assert gui_check == {
        "name": "gui_runtime",
        "ok": False,
        "required": False,
        "detail": "unavailable:no_display",
    }


def test_admin_acceptance_check_target_profile_fails_required_missing_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    missing_release = tmp_path / "missing-redhat-release"
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    monkeypatch.setattr("coding_pet.cli.REDHAT_RELEASE_PATH", missing_release)
    monkeypatch.setattr("coding_pet.cli._gui_runtime_status", lambda: "unavailable:no_display")
    monkeypatch.setattr("coding_pet.cli.shutil.which", lambda name: None)
    monkeypatch.setattr("coding_pet.agents.registry.shutil.which", lambda name: None)

    result = runner.invoke(app, ["admin", "acceptance-check", "--profile", "target"])

    assert result.exit_code == 1
    assert "profile=target" in result.stdout
    assert "check=rhel_8_10 ok=false required=true" in result.stdout
    assert "check=gui_runtime ok=false required=true detail=unavailable:no_display" in result.stdout
    assert "check=tmux ok=false required=true detail=unavailable" in result.stdout
    assert "check=backend_claude_code ok=false required=true" in result.stdout
    assert "check=backend_opencode ok=false required=true" in result.stdout
    assert "overall=failed" in result.stdout


def test_admin_acceptance_check_target_profile_requires_linux(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    release_path = tmp_path / "redhat-release"
    release_path.write_text(
        "Red Hat Enterprise Linux release 8.10 (Ootpa)\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    monkeypatch.setattr("coding_pet.cli.REDHAT_RELEASE_PATH", release_path)
    monkeypatch.setattr("coding_pet.cli.platform.system", lambda: "Windows")
    monkeypatch.setattr("coding_pet.cli.platform.platform", lambda: "Windows-11")
    monkeypatch.setattr("coding_pet.cli.platform.libc_ver", lambda: ("glibc", "2.28"))
    monkeypatch.setattr("coding_pet.cli._gui_runtime_status", lambda: "available")
    monkeypatch.setattr("coding_pet.cli.shutil.which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(
        "coding_pet.agents.registry.shutil.which",
        lambda name: f"/usr/bin/{name}",
    )

    result = runner.invoke(app, ["admin", "acceptance-check", "--profile", "target"])

    assert result.exit_code == 1
    assert "check=linux ok=false required=true detail=Windows-11" in result.stdout
    assert "overall=failed" in result.stdout


def test_admin_acceptance_check_writes_json_report_for_failed_target_profile(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    missing_release = tmp_path / "missing-redhat-release"
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    monkeypatch.setattr("coding_pet.cli.REDHAT_RELEASE_PATH", missing_release)
    monkeypatch.setattr("coding_pet.cli._gui_runtime_status", lambda: "unavailable:no_display")
    monkeypatch.setattr("coding_pet.cli.shutil.which", lambda name: None)
    monkeypatch.setattr("coding_pet.agents.registry.shutil.which", lambda name: None)
    report_path = tmp_path / "qa" / "acceptance-target.json"

    result = runner.invoke(
        app,
        [
            "admin",
            "acceptance-check",
            "--profile",
            "target",
            "--json-out",
            str(report_path),
        ],
    )

    report = json.loads(report_path.read_text("utf-8"))

    assert result.exit_code == 1
    assert report["ok"] is False
    assert report["profile"] == "target"
    assert "rhel_8_10" in report["failed_required"]
    assert "gui_runtime" in report["failed_required"]
    assert "backend_claude_code" in report["failed_required"]


def test_admin_acceptance_check_target_profile_passes_with_required_runtime(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    release_path = tmp_path / "redhat-release"
    release_path.write_text(
        "Red Hat Enterprise Linux release 8.10 (Ootpa)\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    monkeypatch.setattr("coding_pet.cli.REDHAT_RELEASE_PATH", release_path)
    monkeypatch.setattr("coding_pet.cli.platform.system", lambda: "Linux")
    monkeypatch.setattr("coding_pet.cli.platform.platform", lambda: "Linux-test")
    monkeypatch.setattr("coding_pet.cli.platform.libc_ver", lambda: ("glibc", "2.28"))
    monkeypatch.setattr("coding_pet.cli._gui_runtime_status", lambda: "available")
    monkeypatch.setattr("coding_pet.cli.shutil.which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(
        "coding_pet.agents.registry.shutil.which",
        lambda name: f"/usr/bin/{name}",
    )

    result = runner.invoke(app, ["admin", "acceptance-check", "--profile", "target"])

    assert result.exit_code == 0
    assert "profile=target" in result.stdout
    assert "check=linux ok=true required=true detail=Linux-test" in result.stdout
    assert "check=glibc ok=true required=true detail=glibc 2.28; need glibc>=2.28" in result.stdout
    assert "check=rhel_8_10 ok=true required=true" in result.stdout
    assert "check=gui_runtime ok=true required=true detail=available" in result.stdout
    assert "check=tmux ok=true required=true detail=/usr/bin/tmux" in result.stdout
    assert "check=backend_claude_code ok=true required=true" in result.stdout
    assert "check=backend_opencode ok=true required=true" in result.stdout
    assert "check=theme ok=true required=true detail=codex-default:coding_pet" in result.stdout
    assert "overall=ok" in result.stdout


def test_admin_acceptance_check_rejects_unknown_profile() -> None:
    result = runner.invoke(app, ["admin", "acceptance-check", "--profile", "later"])

    assert result.exit_code == 2
    assert "profile must be current or target" in result.stdout


def test_admin_tmux_control_check_writes_json_report(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from coding_pet.tmux.control import TmuxControlCheckResult

    def fake_check(*, text: str, timeout_s: float) -> TmuxControlCheckResult:
        assert text == "hello\n한글"
        assert timeout_s == 0.25
        return TmuxControlCheckResult(
            ok=True,
            session_name="coding-pet-probe-test",
            pane_id="%9",
            expected_text=text,
            observed_text=text,
            detail="raw tmux input preserved",
        )

    monkeypatch.setattr("coding_pet.cli.run_tmux_control_check", fake_check)
    report_path = tmp_path / "tmux-control.json"

    result = runner.invoke(
        app,
        [
            "admin",
            "tmux-control-check",
            "--text",
            "hello\n한글",
            "--timeout-s",
            "0.25",
            "--json-out",
            str(report_path),
        ],
    )
    report = json.loads(report_path.read_text("utf-8"))

    assert result.exit_code == 0
    assert "tmux_control_check=ok" in result.stdout
    assert "pane=%9" in result.stdout
    assert report["schema_version"] == 1
    datetime.fromisoformat(report["generated_at"])
    assert report["ok"] is True
    assert report["observed_text"] == "hello\n한글"


def test_admin_tmux_control_check_exits_nonzero_on_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from coding_pet.tmux.control import TmuxControlCheckResult

    monkeypatch.setattr(
        "coding_pet.cli.run_tmux_control_check",
        lambda **_: TmuxControlCheckResult(
            ok=False,
            session_name="coding-pet-probe-test",
            pane_id="%9",
            expected_text="expected",
            observed_text="actual",
            detail="raw tmux input mismatch",
        ),
    )

    result = runner.invoke(app, ["admin", "tmux-control-check"])

    assert result.exit_code != 0
    assert "tmux_control_check=failed" in result.stdout
    assert "detail=raw tmux input mismatch" in result.stdout


def test_admin_evidence_bundle_writes_current_profile_reports(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from coding_pet.tmux.control import TmuxControlCheckResult

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    monkeypatch.setattr("coding_pet.cli._gui_runtime_status", lambda: "unavailable:no_display")
    monkeypatch.setattr(
        "coding_pet.cli.shutil.which",
        lambda name: "/usr/bin/tmux" if name == "tmux" else None,
    )
    monkeypatch.setattr(
        "coding_pet.cli.run_tmux_control_check",
        lambda **_: TmuxControlCheckResult(
            ok=True,
            session_name="coding-pet-probe-test",
            pane_id="%9",
            expected_text="expected",
            observed_text="expected",
            detail="raw tmux input preserved",
        ),
    )
    output_dir = tmp_path / "evidence"

    result = runner.invoke(
        app,
        [
            "admin",
            "evidence-bundle",
            "--profile",
            "current",
            "--output-dir",
            str(output_dir),
        ],
    )
    summary = json.loads((output_dir / "summary.json").read_text("utf-8"))
    acceptance = json.loads((output_dir / "acceptance-current.json").read_text("utf-8"))
    environment = json.loads((output_dir / "environment.json").read_text("utf-8"))
    tmux_control = json.loads((output_dir / "tmux-control.json").read_text("utf-8"))
    systemd_units = json.loads((output_dir / "systemd-units.json").read_text("utf-8"))
    systemd_runtime = json.loads((output_dir / "systemd-runtime.json").read_text("utf-8"))
    wheelhouse = json.loads((output_dir / "wheelhouse.json").read_text("utf-8"))
    pet_packages = json.loads((output_dir / "pet-packages.json").read_text("utf-8"))
    agent_hooks = json.loads((output_dir / "agent-hooks.json").read_text("utf-8"))
    hook_event_smoke = json.loads((output_dir / "hook-event-smoke.json").read_text("utf-8"))
    widget_smoke = json.loads((output_dir / "widget-smoke.json").read_text("utf-8"))

    assert result.exit_code == 0
    assert "evidence_bundle=" in result.stdout
    assert "overall=ok" in result.stdout
    assert summary["ok"] is True
    assert summary["schema_version"] == 1
    datetime.fromisoformat(summary["generated_at"])
    assert acceptance["schema_version"] == 1
    datetime.fromisoformat(acceptance["generated_at"])
    assert environment["schema_version"] == 1
    datetime.fromisoformat(environment["generated_at"])
    assert tmux_control["schema_version"] == 1
    datetime.fromisoformat(tmux_control["generated_at"])
    assert systemd_units["schema_version"] == 1
    datetime.fromisoformat(systemd_units["generated_at"])
    assert systemd_runtime["schema_version"] == 1
    datetime.fromisoformat(systemd_runtime["generated_at"])
    assert widget_smoke["schema_version"] == 1
    datetime.fromisoformat(widget_smoke["generated_at"])
    assert hook_event_smoke["schema_version"] == 1
    datetime.fromisoformat(hook_event_smoke["generated_at"])
    assert wheelhouse["schema_version"] == 1
    datetime.fromisoformat(wheelhouse["generated_at"])
    assert pet_packages["schema_version"] == 1
    datetime.fromisoformat(pet_packages["generated_at"])
    assert agent_hooks["schema_version"] == 1
    datetime.fromisoformat(agent_hooks["generated_at"])
    assert summary["artifacts"]["acceptance"] == str(output_dir / "acceptance-current.json")
    assert summary["artifacts"]["systemd_units"] == str(output_dir / "systemd-units.json")
    assert summary["artifacts"]["systemd_runtime"] == str(output_dir / "systemd-runtime.json")
    assert summary["artifacts"]["wheelhouse"] == str(output_dir / "wheelhouse.json")
    assert summary["artifacts"]["pet_packages"] == str(output_dir / "pet-packages.json")
    assert summary["artifacts"]["agent_hooks"] == str(output_dir / "agent-hooks.json")
    assert summary["artifacts"]["hook_event_smoke"] == str(output_dir / "hook-event-smoke.json")
    assert summary["artifacts"]["widget_smoke"] == str(output_dir / "widget-smoke.json")
    assert environment["transcript"]["enabled"] is True
    assert environment["transcript"]["redact_secrets"] is True
    assert environment["transcript"]["custom_redaction_pattern_count"] == 0
    assert acceptance["profile"] == "current"
    assert environment["profile"] == "current"
    assert tmux_control["profile"] == "current"
    assert systemd_units["profile"] == "current"
    assert systemd_runtime["profile"] == "current"
    assert widget_smoke["profile"] == "current"
    assert wheelhouse["profile"] == "current"
    assert pet_packages["profile"] == "current"
    assert agent_hooks["profile"] == "current"
    assert hook_event_smoke["profile"] == "current"
    assert environment["platform"]["system"]
    assert environment["platform"]["platform"]
    claude_backend = next(
        backend for backend in environment["backends"] if backend["agent_kind"] == "claude_code"
    )
    assert claude_backend["binary_name"] == "claude"
    assert "binary_path" in claude_backend
    assert claude_backend["control_messages"] == {
        "approve": "approve",
        "reject": "reject",
    }
    assert tmux_control["ok"] is True
    assert tmux_control["required"] is False
    assert systemd_units["ok"] is False
    assert systemd_units["required"] is False
    assert systemd_units["detail"] == "systemd-analyze unavailable"
    assert systemd_runtime["ok"] is False
    assert systemd_runtime["required"] is False
    assert systemd_runtime["detail"] == "systemctl unavailable"
    assert wheelhouse["ok"] is False
    assert wheelhouse["required"] is False
    assert wheelhouse["skipped"] is True
    assert wheelhouse["detail"] == "wheelhouse not provided"
    assert pet_packages["ok"] is False
    assert pet_packages["required"] is False
    assert pet_packages["skipped"] is True
    assert pet_packages["detail"] == "pet source not provided"
    assert agent_hooks["ok"] is False
    assert agent_hooks["required"] is False
    assert hook_event_smoke["ok"] is False
    assert hook_event_smoke["required"] is False
    assert "daemon socket unavailable" in hook_event_smoke["errors"]
    assert widget_smoke["ok"] is True
    assert widget_smoke["required"] is False
    assert widget_smoke["gui_validated"] is False


def test_admin_evidence_bundle_can_require_agent_hooks(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from coding_pet.tmux.control import TmuxControlCheckResult

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    monkeypatch.setattr("coding_pet.cli._gui_runtime_status", lambda: "unavailable:no_display")
    monkeypatch.setattr(
        "coding_pet.cli.shutil.which",
        lambda name: "/usr/bin/tmux" if name == "tmux" else None,
    )
    monkeypatch.setattr(
        "coding_pet.cli.run_tmux_control_check",
        lambda **_: TmuxControlCheckResult(
            ok=True,
            session_name="coding-pet-probe-test",
            pane_id="%9",
            expected_text="expected",
            observed_text="expected",
            detail="raw tmux input preserved",
        ),
    )
    hooks_dir = tmp_path / "hooks"
    claude_settings = tmp_path / "claude" / "settings.json"
    opencode_plugin = tmp_path / "opencode" / "plugins" / "coding-pet.js"
    missing_output_dir = tmp_path / "missing-evidence"

    missing_result = runner.invoke(
        app,
        [
            "admin",
            "evidence-bundle",
            "--profile",
            "current",
            "--output-dir",
            str(missing_output_dir),
            "--hooks-dir",
            str(hooks_dir),
            "--claude-settings",
            str(claude_settings),
            "--opencode-plugin",
            str(opencode_plugin),
            "--require-agent-hooks",
        ],
    )
    missing_summary = json.loads((missing_output_dir / "summary.json").read_text("utf-8"))
    missing_agent_hooks = json.loads((missing_output_dir / "agent-hooks.json").read_text("utf-8"))

    install_result = runner.invoke(
        app,
        [
            "admin",
            "install-agent-hooks",
            "--hooks-dir",
            str(hooks_dir),
            "--claude-settings",
            str(claude_settings),
            "--opencode-plugin",
            str(opencode_plugin),
        ],
    )
    installed_output_dir = tmp_path / "installed-evidence"
    installed_result = runner.invoke(
        app,
        [
            "admin",
            "evidence-bundle",
            "--profile",
            "current",
            "--output-dir",
            str(installed_output_dir),
            "--hooks-dir",
            str(hooks_dir),
            "--claude-settings",
            str(claude_settings),
            "--opencode-plugin",
            str(opencode_plugin),
            "--require-agent-hooks",
        ],
    )
    installed_summary = json.loads((installed_output_dir / "summary.json").read_text("utf-8"))
    installed_agent_hooks = json.loads(
        (installed_output_dir / "agent-hooks.json").read_text("utf-8")
    )

    assert missing_result.exit_code != 0
    assert "overall=failed" in missing_result.stdout
    assert missing_summary["failed_required"] == ["agent_hooks"]
    assert missing_agent_hooks["required"] is True
    assert missing_agent_hooks["ok"] is False
    assert install_result.exit_code == 0, install_result.stdout
    assert installed_result.exit_code == 0, installed_result.stdout
    assert installed_summary["ok"] is True
    assert installed_agent_hooks["required"] is True
    assert installed_agent_hooks["ok"] is True


def test_admin_evidence_bundle_can_require_wheelhouse(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from coding_pet.tmux.control import TmuxControlCheckResult

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    monkeypatch.setattr("coding_pet.cli._gui_runtime_status", lambda: "unavailable:no_display")
    monkeypatch.setattr(
        "coding_pet.cli.shutil.which",
        lambda name: "/usr/bin/tmux" if name == "tmux" else None,
    )
    monkeypatch.setattr(
        "coding_pet.cli.run_tmux_control_check",
        lambda **_: TmuxControlCheckResult(
            ok=True,
            session_name="coding-pet-probe-test",
            pane_id="%9",
            expected_text="expected",
            observed_text="expected",
            detail="raw tmux input preserved",
        ),
    )
    missing_output_dir = tmp_path / "missing-wheelhouse-evidence"

    missing_result = runner.invoke(
        app,
        [
            "admin",
            "evidence-bundle",
            "--profile",
            "current",
            "--output-dir",
            str(missing_output_dir),
            "--require-wheelhouse",
        ],
    )
    missing_summary = json.loads((missing_output_dir / "summary.json").read_text("utf-8"))
    missing_wheelhouse = json.loads((missing_output_dir / "wheelhouse.json").read_text("utf-8"))

    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()
    for filename in [
        "coding_pet-0.1.0-py3-none-any.whl",
        "pydantic-2.11.9-py3-none-any.whl",
        "typer-0.16.1-py3-none-any.whl",
        "Pillow-11.3.0-cp312-cp312-manylinux_2_28_x86_64.whl",
        "PySide6-6.9.3-py3-none-any.whl",
        "PySide6_Addons-6.9.3-cp39-abi3-manylinux_2_28_x86_64.whl",
        "PySide6_Essentials-6.9.3-cp39-abi3-manylinux_2_28_x86_64.whl",
        "shiboken6-6.9.3-cp39-abi3-manylinux_2_28_x86_64.whl",
    ]:
        write_placeholder_wheel(wheelhouse / filename)
    installed_output_dir = tmp_path / "wheelhouse-evidence"
    installed_result = runner.invoke(
        app,
        [
            "admin",
            "evidence-bundle",
            "--profile",
            "current",
            "--output-dir",
            str(installed_output_dir),
            "--wheelhouse",
            str(wheelhouse),
            "--require-wheelhouse",
            "--skip-install-smoke",
        ],
    )
    installed_summary = json.loads((installed_output_dir / "summary.json").read_text("utf-8"))
    installed_wheelhouse = json.loads((installed_output_dir / "wheelhouse.json").read_text("utf-8"))

    assert missing_result.exit_code != 0
    assert "overall=failed" in missing_result.stdout
    assert missing_summary["failed_required"] == ["wheelhouse"]
    assert missing_wheelhouse["required"] is True
    assert missing_wheelhouse["skipped"] is True
    assert installed_result.exit_code == 0, installed_result.stdout
    assert installed_summary["ok"] is True
    assert installed_summary["artifacts"]["wheelhouse"] == str(
        installed_output_dir / "wheelhouse.json"
    )
    assert installed_wheelhouse["required"] is True
    assert installed_wheelhouse["ok"] is True
    assert installed_wheelhouse["install_smoke"]["skipped"] is True


def test_admin_evidence_bundle_can_require_pet_packages(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from coding_pet.tmux.control import TmuxControlCheckResult

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    monkeypatch.setattr("coding_pet.cli._gui_runtime_status", lambda: "unavailable:no_display")
    monkeypatch.setattr(
        "coding_pet.cli.shutil.which",
        lambda name: "/usr/bin/tmux" if name == "tmux" else None,
    )
    monkeypatch.setattr(
        "coding_pet.cli.run_tmux_control_check",
        lambda **_: TmuxControlCheckResult(
            ok=True,
            session_name="coding-pet-probe-test",
            pane_id="%9",
            expected_text="expected",
            observed_text="expected",
            detail="raw tmux input preserved",
        ),
    )
    missing_output_dir = tmp_path / "missing-pets-evidence"

    missing_result = runner.invoke(
        app,
        [
            "admin",
            "evidence-bundle",
            "--profile",
            "current",
            "--output-dir",
            str(missing_output_dir),
            "--require-pet-packages",
        ],
    )
    missing_summary = json.loads((missing_output_dir / "summary.json").read_text("utf-8"))
    missing_pet_packages = json.loads((missing_output_dir / "pet-packages.json").read_text("utf-8"))

    pet_source = tmp_path / "pets"
    pet_dir = pet_source / "boba"
    pet_dir.mkdir(parents=True)
    write_webp_header(pet_dir / "spritesheet.webp")
    (pet_dir / "pet.json").write_text(
        '{"id":"boba","displayName":"Boba","spritesheetPath":"spritesheet.webp"}',
        encoding="utf-8",
    )
    installed_output_dir = tmp_path / "pets-evidence"
    installed_result = runner.invoke(
        app,
        [
            "admin",
            "evidence-bundle",
            "--profile",
            "current",
            "--output-dir",
            str(installed_output_dir),
            "--pet-source",
            str(pet_source),
            "--require-pet-packages",
        ],
    )
    installed_summary = json.loads((installed_output_dir / "summary.json").read_text("utf-8"))
    installed_pet_packages = json.loads(
        (installed_output_dir / "pet-packages.json").read_text("utf-8")
    )

    assert missing_result.exit_code != 0
    assert "overall=failed" in missing_result.stdout
    assert missing_summary["failed_required"] == ["pet_packages"]
    assert missing_pet_packages["required"] is True
    assert missing_pet_packages["skipped"] is True
    assert installed_result.exit_code == 0, installed_result.stdout
    assert installed_summary["ok"] is True
    assert installed_summary["artifacts"]["pet_packages"] == str(
        installed_output_dir / "pet-packages.json"
    )
    assert installed_pet_packages["required"] is True
    assert installed_pet_packages["ok"] is True
    assert installed_pet_packages["total"] == 1
    pet_entry = installed_pet_packages["pets"][0]
    assert pet_entry["theme_id"] == "boba"
    assert pet_entry["transfer"]["kind"] == "directory"
    assert len(pet_entry["transfer"]["sha256"]) == 64
    assert pet_entry["transfer"]["file_count"] == 2
    assert pet_entry["transfer"]["size_bytes"] > 0


def test_admin_evidence_bundle_target_requires_tmux_control_when_skipped(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    release_path = tmp_path / "redhat-release"
    release_path.write_text(
        "Red Hat Enterprise Linux release 8.10 (Ootpa)\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    monkeypatch.setattr("coding_pet.cli.REDHAT_RELEASE_PATH", release_path)
    monkeypatch.setattr("coding_pet.cli.platform.libc_ver", lambda: ("glibc", "2.28"))
    monkeypatch.setattr("coding_pet.cli._gui_runtime_status", lambda: "available")
    monkeypatch.setattr("coding_pet.cli.shutil.which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(
        "coding_pet.agents.registry.shutil.which",
        lambda name: f"/usr/bin/{name}",
    )
    monkeypatch.setattr(
        "coding_pet.cli._systemd_unit_evidence_report",
        lambda **kwargs: {
            "ok": True,
            "required": kwargs["required"],
            "skipped": False,
            "units": ["coding-pet-daemon.service"],
            "detail": "systemd user units verified",
        },
    )
    monkeypatch.setattr(
        "coding_pet.cli._widget_smoke_evidence_report",
        lambda **kwargs: {
            "ok": True,
            "required": kwargs["required"],
            "skipped": False,
            "gui_runtime": "available",
            "gui_validated": True,
            "theme": "codex-default",
            "theme_ok": True,
            "shell_created": True,
            "qt_widget_created": True,
            "sprite_asset": "/tmp/codex-default/alert.png",
            "errors": [],
        },
    )
    monkeypatch.setattr(
        "coding_pet.cli._systemd_runtime_evidence_report",
        lambda **kwargs: {
            "ok": True,
            "required": kwargs["required"],
            "skipped": False,
            "systemctl": "/usr/bin/systemctl",
            "user_manager": {"ok": True},
            "target_enabled": {"unit": "coding-pet.target", "state": "enabled", "ok": True},
            "units": [
                {"unit": "coding-pet-daemon.service", "state": "active", "ok": True},
                {"unit": "coding-pet-widget.service", "state": "active", "ok": True},
                {"unit": "coding-pet.target", "state": "active", "ok": True},
            ],
            "errors": [],
        },
    )
    monkeypatch.setattr(
        "coding_pet.cli._hook_event_smoke_evidence_report",
        lambda **kwargs: _successful_hook_event_smoke_report(required=kwargs["required"]),
    )
    output_dir = tmp_path / "target-evidence"

    result = runner.invoke(
        app,
        [
            "admin",
            "evidence-bundle",
            "--profile",
            "target",
            "--output-dir",
            str(output_dir),
            "--skip-tmux-control",
        ],
    )
    summary = json.loads((output_dir / "summary.json").read_text("utf-8"))
    tmux_control = json.loads((output_dir / "tmux-control.json").read_text("utf-8"))

    assert result.exit_code == 1
    assert "overall=failed" in result.stdout
    assert summary["ok"] is False
    assert summary["failed_required"] == ["tmux_control"]
    assert tmux_control["required"] is True
    assert tmux_control["skipped"] is True


def test_admin_evidence_bundle_target_requires_systemd_unit_verification(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from coding_pet.tmux.control import TmuxControlCheckResult

    release_path = tmp_path / "redhat-release"
    release_path.write_text(
        "Red Hat Enterprise Linux release 8.10 (Ootpa)\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    monkeypatch.setattr("coding_pet.cli.REDHAT_RELEASE_PATH", release_path)
    monkeypatch.setattr("coding_pet.cli.platform.libc_ver", lambda: ("glibc", "2.28"))
    monkeypatch.setattr("coding_pet.cli._gui_runtime_status", lambda: "available")
    monkeypatch.setattr("coding_pet.cli.shutil.which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(
        "coding_pet.agents.registry.shutil.which",
        lambda name: f"/usr/bin/{name}",
    )
    monkeypatch.setattr(
        "coding_pet.cli.run_tmux_control_check",
        lambda **_: TmuxControlCheckResult(
            ok=True,
            session_name="coding-pet-probe-test",
            pane_id="%9",
            expected_text="expected",
            observed_text="expected",
            detail="raw tmux input preserved",
        ),
    )
    monkeypatch.setattr(
        "coding_pet.cli._systemd_unit_evidence_report",
        lambda **kwargs: {
            "ok": False,
            "required": kwargs["required"],
            "skipped": False,
            "units": ["coding-pet-daemon.service"],
            "detail": "systemd-analyze unavailable",
        },
    )
    monkeypatch.setattr(
        "coding_pet.cli._widget_smoke_evidence_report",
        lambda **kwargs: {
            "ok": True,
            "required": kwargs["required"],
            "skipped": False,
            "gui_runtime": "available",
            "gui_validated": True,
            "theme": "codex-default",
            "theme_ok": True,
            "shell_created": True,
            "qt_widget_created": True,
            "sprite_asset": "/tmp/codex-default/alert.png",
            "errors": [],
        },
    )
    monkeypatch.setattr(
        "coding_pet.cli._systemd_runtime_evidence_report",
        lambda **kwargs: {
            "ok": True,
            "required": kwargs["required"],
            "skipped": False,
            "systemctl": "/usr/bin/systemctl",
            "user_manager": {"ok": True},
            "target_enabled": {"unit": "coding-pet.target", "state": "enabled", "ok": True},
            "units": [
                {"unit": "coding-pet-daemon.service", "state": "active", "ok": True},
                {"unit": "coding-pet-widget.service", "state": "active", "ok": True},
                {"unit": "coding-pet.target", "state": "active", "ok": True},
            ],
            "errors": [],
        },
    )
    monkeypatch.setattr(
        "coding_pet.cli._hook_event_smoke_evidence_report",
        lambda **kwargs: _successful_hook_event_smoke_report(required=kwargs["required"]),
    )
    output_dir = tmp_path / "target-evidence"

    result = runner.invoke(
        app,
        [
            "admin",
            "evidence-bundle",
            "--profile",
            "target",
            "--output-dir",
            str(output_dir),
        ],
    )
    summary = json.loads((output_dir / "summary.json").read_text("utf-8"))
    systemd_units = json.loads((output_dir / "systemd-units.json").read_text("utf-8"))

    assert result.exit_code == 1
    assert "overall=failed" in result.stdout
    assert summary["failed_required"] == ["systemd_units"]
    assert systemd_units["required"] is True
    assert systemd_units["ok"] is False


def test_admin_systemd_unit_check_writes_json_report(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class FakeCompletedProcess:
        returncode = 0
        stdout = ""
        stderr = "warnings are captured"

    commands: list[list[str]] = []

    def fake_run(command: list[str], **_: object) -> FakeCompletedProcess:
        commands.append(command)
        return FakeCompletedProcess()

    monkeypatch.setattr(
        "coding_pet.cli.shutil.which",
        lambda name: "/usr/bin/systemd-analyze" if name == "systemd-analyze" else None,
    )
    monkeypatch.setattr("coding_pet.cli.subprocess.run", fake_run)
    report_path = tmp_path / "systemd-units.json"

    result = runner.invoke(
        app,
        [
            "admin",
            "systemd-unit-check",
            "--json-out",
            str(report_path),
        ],
    )
    report = json.loads(report_path.read_text("utf-8"))

    assert result.exit_code == 0
    assert "systemd_units=ok" in result.stdout
    assert report["schema_version"] == 1
    datetime.fromisoformat(report["generated_at"])
    assert report["ok"] is True
    assert report["required"] is True
    assert report["stderr"] == "warnings are captured"
    assert commands[0][0:3] == ["/usr/bin/systemd-analyze", "--user", "verify"]
    assert commands[0][-3:] == [
        str(Path(__file__).resolve().parents[1] / "packaging/systemd/coding-pet-daemon.service"),
        str(Path(__file__).resolve().parents[1] / "packaging/systemd/coding-pet-widget.service"),
        str(Path(__file__).resolve().parents[1] / "packaging/systemd/coding-pet.target"),
    ]


def test_admin_systemd_runtime_check_writes_active_json_report(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class FakeCompletedProcess:
        def __init__(self, stdout: str, returncode: int = 0) -> None:
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = ""

    commands: list[list[str]] = []

    def fake_run(command: list[str], **_: object) -> FakeCompletedProcess:
        commands.append(command)
        if command[-2:] == ["is-enabled", "coding-pet.target"]:
            return FakeCompletedProcess("enabled\n")
        if command[2] == "status":
            return FakeCompletedProcess("user manager ready\n")
        return FakeCompletedProcess("active\n")

    monkeypatch.setenv("DISPLAY", ":1")
    monkeypatch.setenv("XDG_RUNTIME_DIR", "/run/user/1000")
    monkeypatch.setenv("DBUS_SESSION_BUS_ADDRESS", "unix:path=/run/user/1000/bus")
    monkeypatch.setattr(
        "coding_pet.cli.shutil.which",
        lambda name: "/usr/bin/systemctl" if name == "systemctl" else None,
    )
    monkeypatch.setattr("coding_pet.cli.subprocess.run", fake_run)
    report_path = tmp_path / "systemd-runtime.json"

    result = runner.invoke(
        app,
        ["admin", "systemd-runtime-check", "--json-out", str(report_path)],
    )
    report = json.loads(report_path.read_text("utf-8"))

    assert result.exit_code == 0
    assert "systemd_runtime=ok" in result.stdout
    assert report["schema_version"] == 1
    datetime.fromisoformat(report["generated_at"])
    assert report["ok"] is True
    assert report["required"] is True
    assert report["target_enabled"]["state"] == "enabled"
    assert report["user_manager"]["command"] == [
        "/usr/bin/systemctl",
        "--user",
        "status",
    ]
    assert report["target_enabled"]["command"] == [
        "/usr/bin/systemctl",
        "--user",
        "is-enabled",
        "coding-pet.target",
    ]
    assert [unit["unit"] for unit in report["units"]] == [
        "coding-pet-daemon.service",
        "coding-pet-widget.service",
        "coding-pet.target",
    ]
    assert all(unit["state"] == "active" for unit in report["units"])
    assert report["units"][0]["command"] == [
        "/usr/bin/systemctl",
        "--user",
        "is-active",
        "coding-pet-daemon.service",
    ]
    assert commands[0] == ["/usr/bin/systemctl", "--user", "status"]


def test_admin_systemd_runtime_check_fails_when_widget_service_inactive(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class FakeCompletedProcess:
        def __init__(self, stdout: str, returncode: int = 0) -> None:
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = ""

    def fake_run(command: list[str], **_: object) -> FakeCompletedProcess:
        unit = command[-1]
        if command[-2:] == ["is-enabled", "coding-pet.target"]:
            return FakeCompletedProcess("enabled\n")
        if command[2] == "status":
            return FakeCompletedProcess("user manager ready\n")
        if unit == "coding-pet-widget.service":
            return FakeCompletedProcess("failed\n", returncode=3)
        return FakeCompletedProcess("active\n")

    monkeypatch.setenv("DISPLAY", ":1")
    monkeypatch.setenv("XDG_RUNTIME_DIR", "/run/user/1000")
    monkeypatch.setattr(
        "coding_pet.cli.shutil.which",
        lambda name: "/usr/bin/systemctl" if name == "systemctl" else None,
    )
    monkeypatch.setattr("coding_pet.cli.subprocess.run", fake_run)
    report_path = tmp_path / "systemd-runtime.json"

    result = runner.invoke(
        app,
        ["admin", "systemd-runtime-check", "--json-out", str(report_path)],
    )
    report = json.loads(report_path.read_text("utf-8"))

    assert result.exit_code != 0
    assert "systemd_runtime=failed" in result.stdout
    assert report["ok"] is False
    assert "unit coding-pet-widget.service is not active" in report["errors"]


def test_admin_wheelhouse_check_accepts_complete_static_rhel8_wheelhouse(
    tmp_path: Path,
) -> None:
    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()
    for filename in [
        "coding_pet-0.1.0-py3-none-any.whl",
        "pydantic-2.11.9-py3-none-any.whl",
        "typer-0.16.1-py3-none-any.whl",
        "Pillow-11.3.0-cp312-cp312-manylinux_2_28_x86_64.whl",
        "PySide6-6.9.3-py3-none-any.whl",
        "PySide6_Addons-6.9.3-cp39-abi3-manylinux_2_28_x86_64.whl",
        "PySide6_Essentials-6.9.3-cp39-abi3-manylinux_2_28_x86_64.whl",
        "shiboken6-6.9.3-cp39-abi3-manylinux_2_28_x86_64.whl",
    ]:
        write_placeholder_wheel(wheelhouse / filename)
    report_path = tmp_path / "wheelhouse.json"

    result = runner.invoke(
        app,
        [
            "admin",
            "wheelhouse-check",
            str(wheelhouse),
            "--skip-install-smoke",
            "--json-out",
            str(report_path),
        ],
    )
    report = json.loads(report_path.read_text("utf-8"))

    assert result.exit_code == 0
    assert "wheelhouse_check=ok" in result.stdout
    assert "missing_distributions=none" in result.stdout
    assert report["schema_version"] == 1
    datetime.fromisoformat(report["generated_at"])
    assert report["ok"] is True
    assert report["install_smoke"]["skipped"] is True
    assert report["missing_distributions"] == []
    assert report["incompatible_platform_wheels"] == []
    assert report["coding_pet_wheel"]["ok"] is True
    assert report["coding_pet_wheel"]["missing_shared_data"] == []
    wheel_records = report["wheels"]
    assert len(wheel_records) == 8
    assert all(isinstance(wheel["size_bytes"], int) for wheel in wheel_records)
    assert all(wheel["size_bytes"] > 0 for wheel in wheel_records)
    assert all(isinstance(wheel["sha256"], str) for wheel in wheel_records)
    assert all(len(wheel["sha256"]) == 64 for wheel in wheel_records)
    assert all(set(wheel["sha256"]) <= set("0123456789abcdef") for wheel in wheel_records)
    assert "coding-pet" in report["present_distributions"]
    assert "pyside6" in report["present_distributions"]
    assert "pyside6-addons" in report["present_distributions"]
    assert "pyside6-essentials" in report["present_distributions"]
    assert "shiboken6" in report["present_distributions"]


def test_admin_wheelhouse_check_rejects_coding_pet_wheel_missing_shared_data(
    tmp_path: Path,
) -> None:
    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()
    for filename in [
        "pydantic-2.11.9-py3-none-any.whl",
        "typer-0.16.1-py3-none-any.whl",
        "Pillow-11.3.0-cp312-cp312-manylinux_2_28_x86_64.whl",
        "PySide6-6.9.3-py3-none-any.whl",
        "PySide6_Addons-6.9.3-cp39-abi3-manylinux_2_28_x86_64.whl",
        "PySide6_Essentials-6.9.3-cp39-abi3-manylinux_2_28_x86_64.whl",
        "shiboken6-6.9.3-cp39-abi3-manylinux_2_28_x86_64.whl",
    ]:
        write_placeholder_wheel(wheelhouse / filename)
    missing_suffix = "share/coding-pet/docs/operations/offline-rhel8-wheelhouse.md"
    write_coding_pet_wheel(
        wheelhouse / "coding_pet-0.1.0-py3-none-any.whl",
        omit={missing_suffix},
    )
    report_path = tmp_path / "wheelhouse.json"

    result = runner.invoke(
        app,
        [
            "admin",
            "wheelhouse-check",
            str(wheelhouse),
            "--skip-install-smoke",
            "--json-out",
            str(report_path),
        ],
    )
    report = json.loads(report_path.read_text("utf-8"))

    assert result.exit_code == 1
    assert "wheelhouse_check=failed" in result.stdout
    assert report["ok"] is False
    assert report["coding_pet_wheel"]["ok"] is False
    assert missing_suffix in report["coding_pet_wheel"]["missing_shared_data"]
    assert "coding-pet wheel missing required shared data" in report["errors"]


def test_admin_wheelhouse_check_rejects_missing_required_wheel(
    tmp_path: Path,
) -> None:
    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()
    for filename in [
        "coding_pet-0.1.0-py3-none-any.whl",
        "pydantic-2.11.9-py3-none-any.whl",
        "typer-0.16.1-py3-none-any.whl",
        "Pillow-11.3.0-cp312-cp312-manylinux_2_28_x86_64.whl",
    ]:
        write_placeholder_wheel(wheelhouse / filename)
    report_path = tmp_path / "wheelhouse.json"

    result = runner.invoke(
        app,
        [
            "admin",
            "wheelhouse-check",
            str(wheelhouse),
            "--skip-install-smoke",
            "--json-out",
            str(report_path),
        ],
    )
    report = json.loads(report_path.read_text("utf-8"))

    assert result.exit_code == 1
    assert "wheelhouse_check=failed" in result.stdout
    assert "missing_distributions=pyside6,pyside6-addons,pyside6-essentials,shiboken6" in (
        result.stdout
    )
    assert report["ok"] is False
    assert report["missing_distributions"] == [
        "pyside6",
        "pyside6-addons",
        "pyside6-essentials",
        "shiboken6",
    ]


def test_admin_wheelhouse_check_rejects_missing_pyside6_runtime_wheels(
    tmp_path: Path,
) -> None:
    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()
    for filename in [
        "coding_pet-0.1.0-py3-none-any.whl",
        "pydantic-2.11.9-py3-none-any.whl",
        "typer-0.16.1-py3-none-any.whl",
        "Pillow-11.3.0-cp312-cp312-manylinux_2_28_x86_64.whl",
        "PySide6-6.9.3-py3-none-any.whl",
    ]:
        write_placeholder_wheel(wheelhouse / filename)
    report_path = tmp_path / "wheelhouse.json"

    result = runner.invoke(
        app,
        [
            "admin",
            "wheelhouse-check",
            str(wheelhouse),
            "--skip-install-smoke",
            "--json-out",
            str(report_path),
        ],
    )
    report = json.loads(report_path.read_text("utf-8"))

    assert result.exit_code == 1
    assert "wheelhouse_check=failed" in result.stdout
    assert report["missing_distributions"] == [
        "pyside6-addons",
        "pyside6-essentials",
        "shiboken6",
    ]


def test_admin_wheelhouse_check_rejects_newer_manylinux_wheel(
    tmp_path: Path,
) -> None:
    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()
    for filename in [
        "coding_pet-0.1.0-py3-none-any.whl",
        "pydantic-2.11.9-py3-none-any.whl",
        "typer-0.16.1-py3-none-any.whl",
        "Pillow-11.3.0-cp312-cp312-manylinux_2_28_x86_64.whl",
        "PySide6-6.10.0-py3-none-any.whl",
        "PySide6_Addons-6.10.0-cp39-abi3-manylinux_2_34_x86_64.whl",
        "PySide6_Essentials-6.10.0-cp39-abi3-manylinux_2_28_x86_64.whl",
        "shiboken6-6.10.0-cp39-abi3-manylinux_2_28_x86_64.whl",
    ]:
        write_placeholder_wheel(wheelhouse / filename)
    report_path = tmp_path / "wheelhouse.json"

    result = runner.invoke(
        app,
        [
            "admin",
            "wheelhouse-check",
            str(wheelhouse),
            "--skip-install-smoke",
            "--json-out",
            str(report_path),
        ],
    )
    report = json.loads(report_path.read_text("utf-8"))

    assert result.exit_code == 1
    assert "wheelhouse_check=failed" in result.stdout
    assert "PySide6_Addons-6.10.0-cp39-abi3-manylinux_2_34_x86_64.whl" in result.stdout
    assert report["incompatible_platform_wheels"] == [
        "PySide6_Addons-6.10.0-cp39-abi3-manylinux_2_34_x86_64.whl"
    ]


def test_admin_wheelhouse_check_rejects_python_tag_incompatible_wheel(
    tmp_path: Path,
) -> None:
    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()
    for filename in [
        "coding_pet-0.1.0-py3-none-any.whl",
        "pydantic-2.11.9-py3-none-any.whl",
        "typer-0.16.1-py3-none-any.whl",
        "Pillow-11.3.0-cp313-cp313-manylinux_2_28_x86_64.whl",
        "PySide6-6.9.3-py3-none-any.whl",
        "PySide6_Addons-6.9.3-cp39-abi3-manylinux_2_28_x86_64.whl",
        "PySide6_Essentials-6.9.3-cp39-abi3-manylinux_2_28_x86_64.whl",
        "shiboken6-6.9.3-cp39-abi3-manylinux_2_28_x86_64.whl",
    ]:
        write_placeholder_wheel(wheelhouse / filename)
    report_path = tmp_path / "wheelhouse.json"

    result = runner.invoke(
        app,
        [
            "admin",
            "wheelhouse-check",
            str(wheelhouse),
            "--skip-install-smoke",
            "--json-out",
            str(report_path),
        ],
    )
    report = json.loads(report_path.read_text("utf-8"))

    assert result.exit_code == 1
    assert "wheelhouse_check=failed" in result.stdout
    assert "Pillow-11.3.0-cp313-cp313-manylinux_2_28_x86_64.whl" in result.stdout
    assert report["incompatible_python_wheels"] == [
        "Pillow-11.3.0-cp313-cp313-manylinux_2_28_x86_64.whl"
    ]
    assert "wheel python tag is incompatible with Python 3.12 target" in report["errors"]


def test_admin_wheelhouse_check_rejects_non_x86_64_platform_wheel(
    tmp_path: Path,
) -> None:
    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()
    for filename in [
        "coding_pet-0.1.0-py3-none-any.whl",
        "pydantic-2.11.9-py3-none-any.whl",
        "typer-0.16.1-py3-none-any.whl",
        "Pillow-11.3.0-cp312-cp312-manylinux_2_28_aarch64.whl",
        "PySide6-6.9.3-py3-none-any.whl",
        "PySide6_Addons-6.9.3-cp39-abi3-manylinux_2_28_x86_64.whl",
        "PySide6_Essentials-6.9.3-cp39-abi3-manylinux_2_28_x86_64.whl",
        "shiboken6-6.9.3-cp39-abi3-manylinux_2_28_x86_64.whl",
    ]:
        write_placeholder_wheel(wheelhouse / filename)
    report_path = tmp_path / "wheelhouse.json"

    result = runner.invoke(
        app,
        [
            "admin",
            "wheelhouse-check",
            str(wheelhouse),
            "--skip-install-smoke",
            "--json-out",
            str(report_path),
        ],
    )
    report = json.loads(report_path.read_text("utf-8"))

    assert result.exit_code == 1
    assert "wheelhouse_check=failed" in result.stdout
    assert "Pillow-11.3.0-cp312-cp312-manylinux_2_28_aarch64.whl" in result.stdout
    assert report["incompatible_platform_wheels"] == [
        "Pillow-11.3.0-cp312-cp312-manylinux_2_28_aarch64.whl"
    ]
    assert "wheel platform tag is incompatible with RHEL 8.10 x86_64 target" in report["errors"]


def test_admin_wheelhouse_check_runs_offline_install_smoke(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class FakeCompletedProcess:
        returncode = 0
        stdout = ""
        stderr = ""

    commands: list[list[str]] = []

    def fake_run(command: list[str], **_: object) -> FakeCompletedProcess:
        commands.append(command)
        return FakeCompletedProcess()

    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()
    for filename in [
        "coding_pet-0.1.0-py3-none-any.whl",
        "pydantic-2.11.9-py3-none-any.whl",
        "typer-0.16.1-py3-none-any.whl",
        "Pillow-11.3.0-cp312-cp312-manylinux_2_28_x86_64.whl",
        "PySide6-6.9.3-py3-none-any.whl",
        "PySide6_Addons-6.9.3-cp39-abi3-manylinux_2_28_x86_64.whl",
        "PySide6_Essentials-6.9.3-cp39-abi3-manylinux_2_28_x86_64.whl",
        "shiboken6-6.9.3-cp39-abi3-manylinux_2_28_x86_64.whl",
    ]:
        write_placeholder_wheel(wheelhouse / filename)
    monkeypatch.setattr("coding_pet.cli.subprocess.run", fake_run)

    result = runner.invoke(app, ["admin", "wheelhouse-check", str(wheelhouse)])

    assert result.exit_code == 0
    assert "install_smoke=ok" in result.stdout
    assert commands[0][1:3] == ["-m", "venv"]
    assert commands[1][1:6] == [
        "-m",
        "pip",
        "install",
        "--no-index",
        "--find-links",
    ]
    assert commands[1][-1] == "coding-pet[gui]"
    assert "from PySide6 import QtCore" in commands[2][-1]
    assert "load_manifest_for_theme(WidgetTheme.CODEX_DEFAULT)" in commands[2][-1]
    assert "all(path.exists() for path in _systemd_unit_paths())" in commands[2][-1]


def test_admin_wheelhouse_check_fails_when_gui_import_smoke_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class FakeCompletedProcess:
        def __init__(
            self,
            *,
            returncode: int = 0,
            stdout: str = "",
            stderr: str = "",
        ) -> None:
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    commands: list[list[str]] = []

    def fake_run(command: list[str], **_: object) -> FakeCompletedProcess:
        commands.append(command)
        if "from PySide6 import QtCore" in command[-1]:
            return FakeCompletedProcess(returncode=1, stderr="missing QtCore")
        return FakeCompletedProcess()

    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()
    for filename in [
        "coding_pet-0.1.0-py3-none-any.whl",
        "pydantic-2.11.9-py3-none-any.whl",
        "typer-0.16.1-py3-none-any.whl",
        "Pillow-11.3.0-cp312-cp312-manylinux_2_28_x86_64.whl",
        "PySide6-6.9.3-py3-none-any.whl",
        "PySide6_Addons-6.9.3-cp39-abi3-manylinux_2_28_x86_64.whl",
        "PySide6_Essentials-6.9.3-cp39-abi3-manylinux_2_28_x86_64.whl",
        "shiboken6-6.9.3-cp39-abi3-manylinux_2_28_x86_64.whl",
    ]:
        write_placeholder_wheel(wheelhouse / filename)
    monkeypatch.setattr("coding_pet.cli.subprocess.run", fake_run)
    report_path = tmp_path / "wheelhouse.json"

    result = runner.invoke(
        app,
        [
            "admin",
            "wheelhouse-check",
            str(wheelhouse),
            "--json-out",
            str(report_path),
        ],
    )
    report = json.loads(report_path.read_text("utf-8"))

    assert result.exit_code == 1
    assert "install_smoke=failed" in result.stdout
    assert report["ok"] is False
    assert report["install_smoke"]["stage"] == "import"
    assert report["install_smoke"]["stderr"] == "missing QtCore"
    assert report["errors"] == ["offline install smoke failed"]
    assert "from PySide6 import QtCore" in commands[2][-1]
    assert "load_manifest_for_theme(WidgetTheme.CODEX_DEFAULT)" in commands[2][-1]
    assert "all(path.exists() for path in _systemd_unit_paths())" in commands[2][-1]


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


@pytest.mark.asyncio
async def test_daemon_send_action_helper_sends_widget_style_request_over_ipc(
    tmp_path: Path,
) -> None:
    from coding_pet.cli import _send_daemon_action_once
    from coding_pet.daemon.session_registry import SessionRegistry
    from coding_pet.ipc.server import IpcServer

    registry = SessionRegistry()
    received: list[dict[str, object]] = []

    async def handle_action(message: dict[str, object]) -> dict[str, object]:
        received.append(message)
        return {
            "type": "action_result",
            "session_id": str(message["session_id"]),
            "action": str(message["action"]),
            "ok": True,
            "reason": "delivered",
            "detail": "sent",
        }

    server = IpcServer(
        socket_path=tmp_path / "coding-pet.sock",
        registry=registry,
        action_handler=handle_action,
    )
    await server.start()

    try:
        result = await _send_daemon_action_once(
            socket_path=server.socket_path,
            session_id="tmux-%3",
            action="send_reply",
            reply_text="  keep going\n$HOME  ",
            press_enter=False,
        )
    finally:
        await server.stop()

    assert result["ok"] is True
    assert result["reason"] == "delivered"
    assert received == [
        {
            "type": "action_request",
            "session_id": "tmux-%3",
            "action": "send_without_enter",
            "reply_text": "  keep going\n$HOME  ",
            "press_enter": False,
        }
    ]


def test_daemon_send_action_cli_uses_default_socket_path_and_prints_result(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from coding_pet.daemon.runtime import default_socket_path

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    monkeypatch.setattr("coding_pet.config._default_runtime_root", lambda: None)
    config_runtime = tmp_path / ".local/state" / "coding-pet" / "runtime"
    captured: dict[str, object] = {}

    async def fake_send_daemon_action_once(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {
            "type": "action_result",
            "session_id": "tmux-%3",
            "action": "approve",
            "ok": True,
            "reason": "delivered",
            "detail": "approve delivered",
        }

    monkeypatch.setattr("coding_pet.cli._send_daemon_action_once", fake_send_daemon_action_once)

    result = runner.invoke(
        app,
        [
            "daemon",
            "send-action",
            "--session-id",
            "tmux-%3",
            "--action",
            "approve",
        ],
    )

    assert result.exit_code == 0
    assert captured == {
        "socket_path": default_socket_path(config_runtime),
        "session_id": "tmux-%3",
        "action": "approve",
        "reply_text": None,
        "press_enter": True,
    }
    assert "session_id=tmux-%3" in result.stdout
    assert "sent_action=approve" in result.stdout
    assert "ok=true" in result.stdout
    assert "reason=delivered" in result.stdout


def test_daemon_hook_event_cli_uses_default_socket_path_and_prints_result(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from coding_pet.daemon.runtime import default_socket_path

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    monkeypatch.setattr("coding_pet.config._default_runtime_root", lambda: None)
    config_runtime = tmp_path / ".local/state" / "coding-pet" / "runtime"
    captured: dict[str, object] = {}

    async def fake_send_hook_event_once(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {
            "type": "hook_event_result",
            "session_id": "hook-claude_code-abc",
            "ok": True,
            "state": "running",
        }

    monkeypatch.setattr("coding_pet.cli._send_hook_event_once", fake_send_hook_event_once)

    result = runner.invoke(
        app,
        [
            "daemon",
            "hook-event",
            "--agent",
            "claude_code",
            "--event",
            "PreToolUse",
            "--session-id",
            "abc",
            "--workspace",
            "/proj/ws",
            "--title",
            "Hooked",
            "--summary",
            "tool started",
        ],
    )

    assert result.exit_code == 0
    assert captured["socket_path"] == default_socket_path(config_runtime)
    assert str(captured["agent"]) == "claude_code"
    assert captured["event"] == "PreToolUse"
    assert captured["session_id"] == "abc"
    assert captured["workspace"] == "/proj/ws"
    assert captured["title"] == "Hooked"
    assert captured["summary"] == "tool started"
    assert "hook_event=ok" in result.stdout
    assert "session_id=hook-claude_code-abc" in result.stdout
    assert "state=running" in result.stdout


def test_admin_hook_event_smoke_check_writes_verified_report(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from coding_pet.daemon.runtime import default_socket_path
    from coding_pet.transcripts.model import TranscriptEvent

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    monkeypatch.setattr("coding_pet.config._default_runtime_root", lambda: None)
    socket_path = default_socket_path(tmp_path / ".local/state" / "coding-pet" / "runtime")
    socket_path.parent.mkdir(parents=True, exist_ok=True)
    socket_path.write_text("socket placeholder", encoding="utf-8")
    captured_hook: dict[str, object] = {}
    captured_cleanup: dict[str, object] = {}

    async def fake_send_hook_event_once(**kwargs: object) -> dict[str, object]:
        captured_hook.update(kwargs)
        return {
            "type": "hook_event_result",
            "ok": True,
            "session_id": "hook-claude_code-smoke",
            "state": "running",
        }

    async def fake_send_daemon_action_once(**kwargs: object) -> dict[str, object]:
        captured_cleanup.update(kwargs)
        return {
            "type": "action_result",
            "ok": True,
            "outcome": "local_updated",
            "session_id": "hook-claude_code-smoke",
            "action": "hide_pet",
            "reason": "hidden",
            "detail": "session hidden",
        }

    class FakeTranscriptStore:
        path = tmp_path / "transcripts.sqlite"

        async def list_recent_events(
            self,
            session_id: str,
            limit: int = 100,
        ) -> list[TranscriptEvent]:
            assert session_id == "hook-claude_code-smoke"
            assert limit == 10
            return [
                TranscriptEvent(
                    event_id="event-1",
                    session_id=session_id,
                    ts=datetime.now(UTC),
                    direction="system",
                    source="hook_event",
                    text="PreToolUse: coding-pet hook event smoke",
                )
            ]

    monkeypatch.setattr("coding_pet.cli._send_hook_event_once", fake_send_hook_event_once)
    monkeypatch.setattr("coding_pet.cli._send_daemon_action_once", fake_send_daemon_action_once)
    monkeypatch.setattr(
        "coding_pet.cli._configured_transcript_store",
        lambda config: FakeTranscriptStore(),
    )
    report_path = tmp_path / "hook-event-smoke.json"

    result = runner.invoke(
        app,
        ["admin", "hook-event-smoke-check", "--json-out", str(report_path)],
    )
    report = json.loads(report_path.read_text("utf-8"))

    assert result.exit_code == 0
    assert "hook_event_smoke=ok" in result.stdout
    assert report["ok"] is True
    assert report["required"] is True
    assert report["transcript"]["verified"] is True
    assert report["transcript"]["session_id"] == "hook-claude_code-smoke"
    assert report["cleanup_result"]["ok"] is True
    assert report["cleanup_result"]["session_id"] == "hook-claude_code-smoke"
    assert report["cleanup_result"]["reason"] == "hidden"
    assert report["cleanup_result"]["detail"] == "session hidden"
    assert captured_hook["socket_path"] == socket_path
    assert captured_hook["event"] == "PreToolUse"
    assert captured_cleanup["action"] == "hide_pet"


def test_admin_hook_event_smoke_check_fails_when_transcript_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from coding_pet.daemon.runtime import default_socket_path

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    monkeypatch.setattr("coding_pet.config._default_runtime_root", lambda: None)
    socket_path = default_socket_path(tmp_path / ".local/state" / "coding-pet" / "runtime")
    socket_path.parent.mkdir(parents=True, exist_ok=True)
    socket_path.write_text("socket placeholder", encoding="utf-8")

    async def fake_send_hook_event_once(**_: object) -> dict[str, object]:
        return {
            "type": "hook_event_result",
            "ok": True,
            "session_id": "hook-claude_code-smoke",
            "state": "running",
        }

    async def fake_send_daemon_action_once(**_: object) -> dict[str, object]:
        return {"type": "action_result", "ok": True, "action": "hide_pet"}

    class FakeTranscriptStore:
        path = tmp_path / "transcripts.sqlite"

        async def list_recent_events(
            self,
            session_id: str,
            limit: int = 100,
        ) -> list[TranscriptEvent]:
            return []

    monkeypatch.setattr("coding_pet.cli._send_hook_event_once", fake_send_hook_event_once)
    monkeypatch.setattr("coding_pet.cli._send_daemon_action_once", fake_send_daemon_action_once)
    monkeypatch.setattr(
        "coding_pet.cli._configured_transcript_store",
        lambda config: FakeTranscriptStore(),
    )
    report_path = tmp_path / "hook-event-smoke.json"

    result = runner.invoke(
        app,
        ["admin", "hook-event-smoke-check", "--json-out", str(report_path)],
    )
    report = json.loads(report_path.read_text("utf-8"))

    assert result.exit_code != 0
    assert "hook_event_smoke=failed" in result.stdout
    assert report["ok"] is False
    assert "hook transcript event was not found" in report["errors"]


def test_widget_run_uses_default_socket_path_for_long_runtime_dirs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from coding_pet.daemon.runtime import default_socket_path

    runtime_dir = tmp_path / ("deep-segment-" * 12)
    socket_path = default_socket_path(runtime_dir)
    socket_path.parent.mkdir(parents=True, exist_ok=True)
    socket_path.write_text("placeholder", encoding="utf-8")
    monkeypatch.setenv("CODING_PET_RUNTIME_DIR", str(runtime_dir))
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)

    result = runner.invoke(app, ["widget", "run"])

    assert result.exit_code == 0
    assert "live_mode=true" in result.stdout.lower()


def test_daemon_send_tmux_action_routes_reply_without_enter(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from coding_pet.tmux.client import TmuxCommandResult
    from coding_pet.tmux.models import TmuxPaneInfo

    monkeypatch.setenv("HOME", str(tmp_path))

    class FakeTmuxClient:
        def __init__(self) -> None:
            self.loaded_texts: list[str] = []
            self.calls: list[list[str]] = []

        def list_panes(self) -> list[TmuxPaneInfo]:
            return [
                TmuxPaneInfo("%3", "claude-auth", "0.0", "claude", "/proj/ws/auth", None),
            ]

        def capture_pane(self, pane_id: str, *, lines: int) -> str:
            assert pane_id == "%3"
            assert lines == 200
            return "Need clarification: which env?"

        def run(self, argv: list[str]) -> TmuxCommandResult:
            self.calls.append(argv)
            if argv[0] == "load-buffer":
                self.loaded_texts.append(Path(argv[-1]).read_text(encoding="utf-8"))
            return TmuxCommandResult()

    fake_client = FakeTmuxClient()
    monkeypatch.setattr("coding_pet.cli.TmuxClient", lambda: fake_client)

    result = runner.invoke(
        app,
        [
            "daemon",
            "send-tmux-action",
            "--pane",
            "%3",
            "--agent",
            "claude_code",
            "--action",
            "send_reply",
            "--reply-text",
            "  keep going\n$HOME ; \\ done  ",
            "--no-enter",
        ],
    )

    assert result.exit_code == 0
    assert "sent_action=send_reply" in result.stdout
    assert "ok=true" in result.stdout
    assert "reason=delivered" in result.stdout
    assert fake_client.loaded_texts == ["  keep going\n$HOME ; \\ done  "]
    assert "send-keys" not in [call[0] for call in fake_client.calls]


def test_daemon_send_tmux_action_routes_opencode_reject_control_text(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from coding_pet.tmux.client import TmuxCommandResult
    from coding_pet.tmux.models import TmuxPaneInfo

    monkeypatch.setenv("HOME", str(tmp_path))

    class FakeTmuxClient:
        def __init__(self) -> None:
            self.loaded_texts: list[str] = []

        def list_panes(self) -> list[TmuxPaneInfo]:
            return [
                TmuxPaneInfo("%4", "opencode-build", "0.0", "opencode", "/proj/ws/build", None),
            ]

        def capture_pane(self, pane_id: str, *, lines: int) -> str:
            assert pane_id == "%4"
            assert lines == 200
            return "Approval required before editing files."

        def run(self, argv: list[str]) -> TmuxCommandResult:
            if argv[0] == "load-buffer":
                self.loaded_texts.append(Path(argv[-1]).read_text(encoding="utf-8"))
            return TmuxCommandResult()

    fake_client = FakeTmuxClient()
    monkeypatch.setattr("coding_pet.cli.TmuxClient", lambda: fake_client)

    result = runner.invoke(
        app,
        [
            "daemon",
            "send-tmux-action",
            "--pane",
            "%4",
            "--agent",
            "opencode",
            "--action",
            "reject",
        ],
    )

    assert result.exit_code == 0
    assert "agent=opencode" in result.stdout
    assert "sent_action=reject" in result.stdout
    assert "ok=true" in result.stdout
    assert fake_client.loaded_texts == ["reject"]


def test_daemon_verify_tmux_action_writes_before_after_evidence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from coding_pet.tmux.client import TmuxCommandResult
    from coding_pet.tmux.models import TmuxPaneInfo

    monkeypatch.setenv("HOME", str(tmp_path))

    class FakeTmuxClient:
        def __init__(self) -> None:
            self.loaded_texts: list[str] = []
            self.delivered = False

        def list_panes(self) -> list[TmuxPaneInfo]:
            return [
                TmuxPaneInfo("%4", "opencode-build", "0.0", "opencode", "/proj/ws/build", None),
            ]

        def capture_pane(self, pane_id: str, *, lines: int) -> str:
            assert pane_id == "%4"
            assert lines == 200
            if self.delivered:
                return "Accepted patch and continuing."
            return "Approval required before editing files."

        def run(self, argv: list[str]) -> TmuxCommandResult:
            if argv[0] == "load-buffer":
                self.loaded_texts.append(Path(argv[-1]).read_text(encoding="utf-8"))
            if argv[0] == "send-keys" and argv[-1] == "Enter":
                self.delivered = True
            return TmuxCommandResult()

    fake_client = FakeTmuxClient()
    monkeypatch.setattr("coding_pet.cli.TmuxClient", lambda: fake_client)
    report_path = tmp_path / "verify-action.json"

    result = runner.invoke(
        app,
        [
            "daemon",
            "verify-tmux-action",
            "--pane",
            "%4",
            "--agent",
            "opencode",
            "--action",
            "approve",
            "--expect-regex",
            "Accepted patch",
            "--json-out",
            str(report_path),
        ],
    )
    report = json.loads(report_path.read_text("utf-8"))

    assert result.exit_code == 0
    assert "matched_expected=true" in result.stdout
    assert report["schema_version"] == 1
    assert report["profile"] == "target"
    assert report["ok"] is True
    assert report["output_changed"] is True
    assert report["matched_expected"] is True
    assert report["action_result"]["ok"] is True
    assert report["action_result"]["delivered_text"] == "approve"
    assert report["capability"] == {
        "action": "approve",
        "transport": "tmux_buffer",
        "requires_text": False,
        "press_enter_default": True,
        "semantics": "agent_control",
    }
    assert fake_client.loaded_texts == ["approve"]


def test_daemon_verify_tmux_action_redacts_evidence_tails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from coding_pet.tmux.client import TmuxCommandResult
    from coding_pet.tmux.models import TmuxPaneInfo

    monkeypatch.setenv("HOME", str(tmp_path))

    class FakeTmuxClient:
        def __init__(self) -> None:
            self.delivered = False

        def list_panes(self) -> list[TmuxPaneInfo]:
            return [
                TmuxPaneInfo("%4", "opencode-build", "0.0", "opencode", "/proj/ws/build", None),
            ]

        def capture_pane(self, pane_id: str, *, lines: int) -> str:
            assert pane_id == "%4"
            assert lines == 200
            if self.delivered:
                return "Accepted patch OPENAI_API_KEY=sk-live_abcdefghijklmnopqrstuvwxyz"
            return "Approval required Authorization: Bearer sk-test_abcdefghijklmnopqrstuvwxyz"

        def run(self, argv: list[str]) -> TmuxCommandResult:
            if argv[0] == "send-keys" and argv[-1] == "Enter":
                self.delivered = True
            return TmuxCommandResult()

    monkeypatch.setattr("coding_pet.cli.TmuxClient", FakeTmuxClient)
    report_path = tmp_path / "verify-action.json"

    result = runner.invoke(
        app,
        [
            "daemon",
            "verify-tmux-action",
            "--pane",
            "%4",
            "--agent",
            "opencode",
            "--action",
            "approve",
            "--expect-regex",
            "Accepted patch",
            "--json-out",
            str(report_path),
        ],
    )
    report = json.loads(report_path.read_text("utf-8"))

    assert result.exit_code == 0
    assert "sk-test_" not in report["before_tail"]
    assert "sk-live_" not in report["after_tail"]
    assert "Authorization: Bearer [REDACTED]" in report["before_tail"]
    assert "OPENAI_API_KEY=[REDACTED]" in report["after_tail"]


def test_daemon_verify_tmux_action_fails_when_expected_output_is_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from coding_pet.tmux.client import TmuxCommandResult
    from coding_pet.tmux.models import TmuxPaneInfo

    monkeypatch.setenv("HOME", str(tmp_path))

    class FakeTmuxClient:
        def list_panes(self) -> list[TmuxPaneInfo]:
            return [
                TmuxPaneInfo("%3", "claude-auth", "0.0", "claude", "/proj/ws/auth", None),
            ]

        def capture_pane(self, pane_id: str, *, lines: int) -> str:
            return "Still waiting for approval."

        def run(self, argv: list[str]) -> TmuxCommandResult:
            return TmuxCommandResult()

    monkeypatch.setattr("coding_pet.cli.TmuxClient", lambda: FakeTmuxClient())
    report_path = tmp_path / "verify-action.json"

    result = runner.invoke(
        app,
        [
            "daemon",
            "verify-tmux-action",
            "--pane",
            "%3",
            "--agent",
            "claude_code",
            "--action",
            "approve",
            "--expect-regex",
            "Accepted",
            "--timeout-s",
            "0.1",
            "--json-out",
            str(report_path),
        ],
    )
    report = json.loads(report_path.read_text("utf-8"))

    assert result.exit_code != 0
    assert "matched_expected=false" in result.stdout
    assert report["ok"] is False
    assert report["matched_expected"] is False
    assert report["action_result"]["ok"] is True
    assert report["action_result"]["delivered_text"] == "approve"


def test_daemon_verify_tmux_action_writes_report_identity_on_exception(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))

    class FakeTmuxClient:
        def capture_pane(self, pane_id: str, *, lines: int) -> str:
            raise RuntimeError(f"tmux unavailable for {pane_id}")

    monkeypatch.setattr("coding_pet.cli.TmuxClient", FakeTmuxClient)
    report_path = tmp_path / "verify-action.json"

    result = runner.invoke(
        app,
        [
            "daemon",
            "verify-tmux-action",
            "--pane",
            "%dead",
            "--agent",
            "opencode",
            "--action",
            "approve",
            "--expect-regex",
            "Accepted",
            "--json-out",
            str(report_path),
        ],
    )
    report = json.loads(report_path.read_text("utf-8"))

    assert result.exit_code != 0
    assert report["schema_version"] == 1
    assert report["profile"] == "target"
    assert report["ok"] is False
    assert report["pane"] == "%dead"
    assert report["agent"] == "opencode"
    assert report["action"] == "approve"
    assert report["capability"]["action"] == "approve"
    assert report["expected_regex"] == "Accepted"
    assert report["action_result"]["outcome"] == "backend_failed"
    assert "tmux unavailable" in report["error"]


def test_admin_backend_evidence_check_accepts_verified_report(tmp_path: Path) -> None:
    report_path = tmp_path / "verify-action.json"
    report_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "ok": True,
                "profile": "target",
                "agent": "claude_code",
                "action": "approve",
                "pane": "%claude-approve",
                "expected_regex": "approved",
                "matched_expected": True,
                "output_changed": True,
                "capability": {
                    "action": "approve",
                    "transport": "tmux_buffer",
                    "requires_text": False,
                    "press_enter_default": True,
                    "semantics": "agent_control",
                },
                "before_hash": "1" * 64,
                "after_hash": "2" * 64,
                "before_tail": "waiting",
                "after_tail": "approved",
                "action_result": {
                    "ok": True,
                    "outcome": "accepted",
                    "session_id": "target-claude-approve",
                    "action": "approve",
                    "delivered_text": "approve",
                },
            }
        ),
        encoding="utf-8",
    )
    check_path = tmp_path / "backend-evidence.json"

    result = runner.invoke(
        app,
        [
            "admin",
            "backend-evidence-check",
            str(report_path),
            "--agent",
            "claude_code",
            "--action",
            "approve",
            "--json-out",
            str(check_path),
        ],
    )
    check = json.loads(check_path.read_text("utf-8"))

    assert result.exit_code == 0
    assert "backend_evidence=ok" in result.stdout
    assert "pane=%claude-approve" in result.stdout
    assert "matched_expected=true" in result.stdout
    assert check["ok"] is True
    assert check["errors"] == []
    assert check["capability"] == {
        "action": "approve",
        "transport": "tmux_buffer",
        "requires_text": False,
        "press_enter_default": True,
        "semantics": "agent_control",
    }


def test_admin_backend_evidence_check_rejects_missing_action_outcome(
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "verify-action.json"
    report_path.write_text(
        json.dumps(
            {
                "ok": True,
                "agent": "claude_code",
                "action": "approve",
                "pane": "%claude-approve",
                "expected_regex": "approved",
                "matched_expected": True,
                "output_changed": True,
                "capability": {
                    "action": "approve",
                    "transport": "tmux_buffer",
                    "requires_text": False,
                    "press_enter_default": True,
                    "semantics": "agent_control",
                },
                "before_hash": "1" * 64,
                "after_hash": "2" * 64,
                "before_tail": "waiting",
                "after_tail": "approved",
                "action_result": {
                    "ok": True,
                    "delivered_text": "approve",
                },
            }
        ),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "admin",
            "backend-evidence-check",
            str(report_path),
            "--agent",
            "claude_code",
            "--action",
            "approve",
        ],
    )

    assert result.exit_code != 0
    assert "backend_evidence=failed" in result.stdout
    assert "error=action_result.outcome must be accepted" in result.stdout


def test_admin_backend_evidence_check_rejects_missing_report_identity(
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "verify-action.json"
    report_path.write_text(
        json.dumps(
            {
                "ok": True,
                "agent": "claude_code",
                "action": "approve",
                "pane": "%claude-approve",
                "expected_regex": "approved",
                "matched_expected": True,
                "output_changed": True,
                "capability": {
                    "action": "approve",
                    "transport": "tmux_buffer",
                    "requires_text": False,
                    "press_enter_default": True,
                    "semantics": "agent_control",
                },
                "before_hash": "1" * 64,
                "after_hash": "2" * 64,
                "before_tail": "waiting",
                "after_tail": "approved",
                "action_result": {
                    "ok": True,
                    "outcome": "accepted",
                    "delivered_text": "approve",
                },
            }
        ),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "admin",
            "backend-evidence-check",
            str(report_path),
            "--agent",
            "claude_code",
            "--action",
            "approve",
        ],
    )

    assert result.exit_code != 0
    assert "backend_evidence=failed" in result.stdout
    assert "error=report schema_version must be 1" in result.stdout
    assert "error=report profile must be target, got None" in result.stdout


def test_admin_backend_evidence_check_rejects_missing_action_result_metadata(
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "verify-action.json"
    report_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "ok": True,
                "profile": "target",
                "agent": "claude_code",
                "action": "approve",
                "pane": "%claude-approve",
                "expected_regex": "approved",
                "matched_expected": True,
                "output_changed": True,
                "capability": {
                    "action": "approve",
                    "transport": "tmux_buffer",
                    "requires_text": False,
                    "press_enter_default": True,
                    "semantics": "agent_control",
                },
                "before_hash": "1" * 64,
                "after_hash": "2" * 64,
                "before_tail": "waiting",
                "after_tail": "approved",
                "action_result": {
                    "ok": True,
                    "outcome": "accepted",
                    "delivered_text": "approve",
                },
            }
        ),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "admin",
            "backend-evidence-check",
            str(report_path),
            "--agent",
            "claude_code",
            "--action",
            "approve",
        ],
    )

    assert result.exit_code != 0
    assert "backend_evidence=failed" in result.stdout
    assert "error=action_result.action must be approve" in result.stdout
    assert "error=action_result.session_id is required" in result.stdout


def test_admin_backend_evidence_check_rejects_action_result_action_mismatch(
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "verify-action.json"
    report_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "ok": True,
                "profile": "target",
                "agent": "opencode",
                "action": "approve",
                "pane": "%opencode-approve",
                "expected_regex": "approved",
                "matched_expected": True,
                "output_changed": True,
                "capability": {
                    "action": "approve",
                    "transport": "tmux_buffer",
                    "requires_text": False,
                    "press_enter_default": True,
                    "semantics": "agent_control",
                },
                "before_hash": "1" * 64,
                "after_hash": "2" * 64,
                "before_tail": "waiting",
                "after_tail": "approved",
                "action_result": {
                    "ok": True,
                    "outcome": "accepted",
                    "session_id": "target-opencode-approve",
                    "action": "reject",
                    "delivered_text": "approve",
                },
            }
        ),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "admin",
            "backend-evidence-check",
            str(report_path),
            "--agent",
            "opencode",
            "--action",
            "approve",
        ],
    )

    assert result.exit_code != 0
    assert "backend_evidence=failed" in result.stdout
    assert "error=action_result.action must be approve" in result.stdout


def test_admin_backend_evidence_check_rejects_failed_action_outcome(
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "verify-action.json"
    report_path.write_text(
        json.dumps(
            {
                "ok": True,
                "agent": "claude_code",
                "action": "approve",
                "pane": "%claude-approve",
                "expected_regex": "approved",
                "matched_expected": True,
                "output_changed": True,
                "capability": {
                    "action": "approve",
                    "transport": "tmux_buffer",
                    "requires_text": False,
                    "press_enter_default": True,
                    "semantics": "agent_control",
                },
                "before_hash": "1" * 64,
                "after_hash": "2" * 64,
                "before_tail": "waiting",
                "after_tail": "approved",
                "action_result": {
                    "ok": False,
                    "outcome": "backend_failed",
                    "delivered_text": "approve",
                },
            }
        ),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "admin",
            "backend-evidence-check",
            str(report_path),
            "--agent",
            "claude_code",
            "--action",
            "approve",
        ],
    )

    assert result.exit_code != 0
    assert "backend_evidence=failed" in result.stdout
    assert "error=action_result.ok must be true" in result.stdout
    assert "error=action_result.outcome must be accepted" in result.stdout


def test_admin_backend_evidence_check_rejects_capability_mismatch(
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "verify-action.json"
    report_path.write_text(
        json.dumps(
            {
                "ok": True,
                "agent": "claude_code",
                "action": "send_reply",
                "pane": "%claude-reply",
                "expected_regex": "accepted",
                "matched_expected": True,
                "output_changed": True,
                "capability": {
                    "action": "send_reply",
                    "transport": "process_stdin",
                    "requires_text": False,
                    "press_enter_default": True,
                    "semantics": "agent_control",
                },
                "before_hash": "1" * 64,
                "after_hash": "2" * 64,
                "before_tail": "waiting",
                "after_tail": "accepted",
                "action_result": {"ok": True, "delivered_text": "keep going"},
            }
        ),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "admin",
            "backend-evidence-check",
            str(report_path),
            "--agent",
            "claude_code",
            "--action",
            "send_reply",
        ],
    )

    assert result.exit_code != 0
    assert "backend_evidence=failed" in result.stdout
    assert "error=capability transport must be tmux_buffer" in result.stdout
    assert "error=capability requires_text must be true" in result.stdout
    assert "error=capability semantics must be agent_reply" in result.stdout


def test_admin_backend_evidence_check_rejects_non_sha_hashes(
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "verify-action.json"
    report_path.write_text(
        json.dumps(
            {
                "ok": True,
                "agent": "claude_code",
                "action": "approve",
                "pane": "%claude-approve",
                "expected_regex": "approved",
                "matched_expected": True,
                "output_changed": True,
                "before_hash": "before",
                "after_hash": "after",
                "before_tail": "waiting",
                "after_tail": "approved",
                "action_result": {"ok": True, "delivered_text": "approve"},
            }
        ),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "admin",
            "backend-evidence-check",
            str(report_path),
            "--agent",
            "claude_code",
            "--action",
            "approve",
        ],
    )

    assert result.exit_code != 0
    assert "backend_evidence=failed" in result.stdout
    assert "error=before_hash must be SHA-256 hex" in result.stdout
    assert "error=after_hash must be SHA-256 hex" in result.stdout


def test_admin_backend_evidence_check_rejects_missing_pane(
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "verify-action.json"
    report_path.write_text(
        json.dumps(
            {
                "ok": True,
                "agent": "claude_code",
                "action": "approve",
                "expected_regex": "approved",
                "matched_expected": True,
                "output_changed": True,
                "before_hash": "before",
                "after_hash": "after",
                "before_tail": "waiting",
                "after_tail": "approved",
                "action_result": {"ok": True, "delivered_text": "approve"},
            }
        ),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "admin",
            "backend-evidence-check",
            str(report_path),
            "--agent",
            "claude_code",
            "--action",
            "approve",
        ],
    )

    assert result.exit_code != 0
    assert "backend_evidence=failed" in result.stdout
    assert "error=pane is required" in result.stdout


def test_admin_backend_evidence_check_rejects_missing_delivered_text(
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "verify-action.json"
    report_path.write_text(
        json.dumps(
            {
                "ok": True,
                "agent": "claude_code",
                "action": "approve",
                "expected_regex": "approved",
                "matched_expected": True,
                "output_changed": True,
                "before_hash": "before",
                "after_hash": "after",
                "before_tail": "waiting",
                "after_tail": "approved",
                "action_result": {"ok": True},
            }
        ),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "admin",
            "backend-evidence-check",
            str(report_path),
            "--agent",
            "claude_code",
            "--action",
            "approve",
        ],
    )

    assert result.exit_code != 0
    assert "backend_evidence=failed" in result.stdout
    assert "error=action_result.delivered_text is required" in result.stdout


def test_admin_backend_evidence_check_rejects_unredacted_delivered_text(
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "verify-action.json"
    report_path.write_text(
        json.dumps(
            {
                "ok": True,
                "agent": "claude_code",
                "action": "approve",
                "expected_regex": "approved",
                "matched_expected": True,
                "output_changed": True,
                "before_hash": "before",
                "after_hash": "after",
                "before_tail": "waiting",
                "after_tail": "approved",
                "action_result": {
                    "ok": True,
                    "delivered_text": "password=super-secret",
                },
            }
        ),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "admin",
            "backend-evidence-check",
            str(report_path),
            "--agent",
            "claude_code",
            "--action",
            "approve",
        ],
    )

    assert result.exit_code != 0
    assert "backend_evidence=failed" in result.stdout
    assert (
        "error=action_result.delivered_text contains unredacted secret-like text" in result.stdout
    )


def test_admin_backend_evidence_check_rejects_weak_report(tmp_path: Path) -> None:
    report_path = tmp_path / "verify-action.json"
    report_path.write_text(
        json.dumps(
            {
                "ok": True,
                "agent": "opencode",
                "action": "reject",
                "matched_expected": None,
                "output_changed": False,
                "before_hash": "same",
                "after_hash": "same",
                "action_result": {"ok": True},
            }
        ),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "admin",
            "backend-evidence-check",
            str(report_path),
            "--agent",
            "claude_code",
            "--action",
            "approve",
        ],
    )

    assert result.exit_code != 0
    assert "backend_evidence=failed" in result.stdout
    assert "error=agent must be claude_code" in result.stdout
    assert "error=expected_regex is required" in result.stdout
    assert "error=matched_expected must be true" in result.stdout


def test_admin_backend_evidence_check_rejects_unredacted_evidence_tail(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("CODING_PET_TRANSCRIPT_REDACTION_PATTERNS", r"PROJECT-[0-9]{4}")
    report_path = tmp_path / "verify-action.json"
    report_path.write_text(
        json.dumps(
            {
                "ok": True,
                "agent": "claude_code",
                "action": "approve",
                "expected_regex": "approved",
                "matched_expected": True,
                "output_changed": True,
                "before_hash": "before",
                "after_hash": "after",
                "before_tail": "PROJECT-1234",
                "after_tail": "approved",
                "action_result": {"ok": True},
            }
        ),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "admin",
            "backend-evidence-check",
            str(report_path),
            "--agent",
            "claude_code",
            "--action",
            "approve",
        ],
    )

    assert result.exit_code != 0
    assert "backend_evidence=failed" in result.stdout
    assert "error=before_tail contains unredacted secret-like text" in result.stdout


def test_admin_backend_evidence_check_rejects_missing_evidence_tails(
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "verify-action.json"
    report_path.write_text(
        json.dumps(
            {
                "ok": True,
                "agent": "claude_code",
                "action": "approve",
                "expected_regex": "approved",
                "matched_expected": True,
                "output_changed": True,
                "before_hash": "before",
                "after_hash": "after",
                "action_result": {"ok": True},
            }
        ),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "admin",
            "backend-evidence-check",
            str(report_path),
            "--agent",
            "claude_code",
            "--action",
            "approve",
        ],
    )

    assert result.exit_code != 0
    assert "backend_evidence=failed" in result.stdout
    assert "error=before_tail is required" in result.stdout
    assert "error=after_tail is required" in result.stdout


def test_admin_backend_evidence_check_rejects_regex_tail_mismatch(
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "verify-action.json"
    report_path.write_text(
        json.dumps(
            {
                "ok": True,
                "agent": "opencode",
                "action": "reject",
                "expected_regex": "rejected",
                "matched_expected": True,
                "output_changed": True,
                "before_hash": "before",
                "after_hash": "after",
                "before_tail": "waiting",
                "after_tail": "still pending",
                "action_result": {"ok": True},
            }
        ),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "admin",
            "backend-evidence-check",
            str(report_path),
            "--agent",
            "opencode",
            "--action",
            "reject",
        ],
    )

    assert result.exit_code != 0
    assert "backend_evidence=failed" in result.stdout
    assert "error=after_tail must match expected_regex" in result.stdout


def test_admin_backend_evidence_check_rejects_expected_regex_already_in_before_tail(
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "verify-action.json"
    report_path.write_text(
        json.dumps(
            {
                "ok": True,
                "agent": "claude_code",
                "action": "approve",
                "expected_regex": "approved",
                "matched_expected": True,
                "output_changed": True,
                "before_hash": "before",
                "after_hash": "after",
                "before_tail": "already approved before action",
                "after_tail": "approved again after action",
                "action_result": {"ok": True},
            }
        ),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "admin",
            "backend-evidence-check",
            str(report_path),
            "--agent",
            "claude_code",
            "--action",
            "approve",
        ],
    )

    assert result.exit_code != 0
    assert "backend_evidence=failed" in result.stdout
    assert "error=before_tail must not match expected_regex" in result.stdout


def test_admin_target_evidence_check_accepts_complete_target_bundle(tmp_path: Path) -> None:
    evidence_dir = tmp_path / "target-evidence"
    _write_complete_target_evidence_bundle(evidence_dir)
    check_path = tmp_path / "target-check.json"

    result = runner.invoke(
        app,
        [
            "admin",
            "target-evidence-check",
            str(evidence_dir),
            "--json-out",
            str(check_path),
        ],
    )
    check = json.loads(check_path.read_text("utf-8"))

    assert result.exit_code == 0
    assert "target_evidence=ok" in result.stdout
    assert "backend_report_count=6" in result.stdout
    assert check["ok"] is True
    assert check["errors"] == []
    assert check["artifacts"]["systemd_units"] == str(evidence_dir / "systemd-units.json")
    assert check["artifacts"]["systemd_runtime"] == str(evidence_dir / "systemd-runtime.json")
    assert check["artifacts"]["wheelhouse"] == str(evidence_dir / "wheelhouse.json")
    assert check["artifacts"]["pet_packages"] == str(evidence_dir / "pet-packages.json")
    assert check["artifacts"]["backend_summary"] == str(evidence_dir / "backend-summary.json")
    assert check["artifacts"]["backend_claude_code_send_reply"] == str(
        evidence_dir / "backend-claude_code-send_reply.json"
    )
    summary = json.loads((evidence_dir / "summary.json").read_text("utf-8"))
    assert summary["artifacts"]["backend_summary"] == str(evidence_dir / "backend-summary.json")
    assert summary["artifacts"]["backend_opencode_reject"] == str(
        evidence_dir / "backend-opencode-reject.json"
    )
    assert check["artifacts"]["hook_event_smoke"] == str(evidence_dir / "hook-event-smoke.json")
    assert check["artifacts"]["widget_smoke"] == str(evidence_dir / "widget-smoke.json")
    assert check["wheelhouse"]["ok"] is True
    assert check["pet_packages"]["ok"] is True
    assert check["agent_hooks"]["ok"] is True
    assert check["hook_event_smoke"]["transcript"]["verified"] is True
    assert check["systemd_runtime"]["ok"] is True
    assert check["widget_smoke"]["gui_validated"] is True
    assert check["backend_summary"]["ok"] is True
    assert check["backend_summary"]["schema_version"] == 1
    assert check["backend_summary"]["profile"] == "target"
    assert len(check["backend_reports"]) == 6


def test_admin_target_evidence_check_rejects_weak_summary_manifest(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    _write_complete_target_evidence_bundle(evidence_dir)
    summary_path = evidence_dir / "summary.json"
    summary = json.loads(summary_path.read_text("utf-8"))
    summary.pop("schema_version")
    summary["generated_at"] = "not-a-timestamp"
    summary["artifacts"].pop("hook_event_smoke")
    summary["artifacts"].pop("backend_summary")
    summary["artifacts"].pop("backend_claude_code_send_reply")
    summary["artifacts"]["widget_smoke"] = str(evidence_dir / "wrong-widget.json")
    summary_path.write_text(json.dumps(summary), encoding="utf-8")

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert "error=summary schema_version must be 1" in result.stdout
    assert "error=summary generated_at must be ISO 8601" in result.stdout
    assert "error=summary artifacts missing hook_event_smoke" in result.stdout
    assert "error=summary artifacts missing backend_summary" in result.stdout
    assert "error=summary artifacts missing backend_claude_code_send_reply" in result.stdout
    assert ("error=summary artifact widget_smoke must point to widget-smoke.json") in result.stdout


def test_admin_target_evidence_check_rejects_external_summary_artifact_paths(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    _write_complete_target_evidence_bundle(evidence_dir)
    summary_path = evidence_dir / "summary.json"
    summary = json.loads(summary_path.read_text("utf-8"))
    summary["output_dir"] = str(tmp_path / "other-evidence")
    summary["artifacts"]["environment"] = str(tmp_path / "other" / "environment.json")
    summary_path.write_text(json.dumps(summary), encoding="utf-8")

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert "error=summary output_dir must match evidence directory" in result.stdout
    assert "error=summary artifact environment must stay inside evidence directory" in result.stdout


def test_admin_target_evidence_check_rejects_shifted_summary_artifact_paths(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    _write_complete_target_evidence_bundle(evidence_dir)
    summary_path = evidence_dir / "summary.json"
    summary = json.loads(summary_path.read_text("utf-8"))
    summary["artifacts"]["environment"] = str(evidence_dir / "nested" / "environment.json")
    summary_path.write_text(json.dumps(summary), encoding="utf-8")

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert (
        "error=summary artifact environment must match evidence file environment.json"
        in result.stdout
    )


def test_admin_target_evidence_check_rejects_weak_environment_report(tmp_path: Path) -> None:
    evidence_dir = tmp_path / "target-evidence"
    _write_complete_target_evidence_bundle(
        evidence_dir,
        environment={
            "profile": "target",
            "platform": {"system": "Windows", "platform": "Windows-11"},
            "python": {"version": "3.11.9"},
            "libc": {"name": "msvcrt", "version": ""},
            "redhat_release": None,
            "gui_runtime": "available",
            "tmux_binary": "/usr/bin/tmux",
            "theme": {"ok": True},
            "backends": [],
        },
    )

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert "error=environment platform.system must be Linux, got 'Windows'" in result.stdout
    assert "error=environment python.version must be 3.12.x" in result.stdout
    assert "error=environment libc.name must be glibc" in result.stdout
    assert "error=environment redhat_release must describe RHEL 8.10" in result.stdout
    assert "error=environment missing backend claude_code" in result.stdout


def test_admin_target_evidence_check_rejects_unversioned_acceptance_and_environment_reports(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    _write_complete_target_evidence_bundle(evidence_dir)
    acceptance_path = evidence_dir / "acceptance-target.json"
    acceptance = json.loads(acceptance_path.read_text("utf-8"))
    acceptance.pop("schema_version")
    acceptance["generated_at"] = "not-a-timestamp"
    acceptance_path.write_text(json.dumps(acceptance), encoding="utf-8")
    environment_path = evidence_dir / "environment.json"
    environment = json.loads(environment_path.read_text("utf-8"))
    environment.pop("schema_version")
    environment["generated_at"] = "not-a-timestamp"
    environment_path.write_text(json.dumps(environment), encoding="utf-8")

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert "error=acceptance schema_version must be 1" in result.stdout
    assert "error=acceptance generated_at must be ISO 8601" in result.stdout
    assert "error=environment schema_version must be 1" in result.stdout
    assert "error=environment generated_at must be ISO 8601" in result.stdout


def test_admin_target_evidence_check_rejects_non_rhel_8_10_linux_environment(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    environment = _target_environment_report()
    environment["platform"] = {
        "system": "Linux",
        "platform": "Linux-5.14.0-rhel9-x86_64-with-glibc2.34",
        "machine": "x86_64",
        "release": "5.14.0-427.el9.x86_64",
    }
    environment["libc"] = {"name": "glibc", "version": "2.34"}
    _write_complete_target_evidence_bundle(evidence_dir, environment=environment)

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert "error=environment platform.release must describe RHEL 8.10" in result.stdout
    assert "error=environment libc.version must be exactly 2.28" in result.stdout


def test_admin_target_evidence_check_rejects_non_x86_64_linux_environment(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    environment = _target_environment_report()
    environment["platform"] = {
        "system": "Linux",
        "platform": "Linux-4.18.0-rhel8-aarch64-with-glibc2.28",
        "machine": "aarch64",
        "release": "4.18.0-553.el8_10.aarch64",
    }
    _write_complete_target_evidence_bundle(evidence_dir, environment=environment)

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert "error=environment platform.machine must be x86_64" in result.stdout


def test_admin_target_evidence_check_rejects_weak_python_executable_environment(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    environment = _target_environment_report()
    python_report = environment["python"]
    assert isinstance(python_report, dict)
    python_report.pop("executable")
    _write_complete_target_evidence_bundle(evidence_dir, environment=environment)

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert "error=environment python.executable is required" in result.stdout

    python_report["executable"] = "python3.12"
    (evidence_dir / "environment.json").write_text(
        json.dumps(environment),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert "error=environment python.executable must be an absolute path" in result.stdout

    python_report["executable"] = "/usr/bin/bash"
    (evidence_dir / "environment.json").write_text(
        json.dumps(environment),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert "error=environment python.executable must point to python" in result.stdout


def test_admin_target_evidence_check_rejects_weak_tmux_binary_environment(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    environment = _target_environment_report()
    environment["tmux_binary"] = "tmux"
    _write_complete_target_evidence_bundle(evidence_dir, environment=environment)

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert "error=environment tmux_binary must be an absolute path" in result.stdout

    environment["tmux_binary"] = "/usr/bin/screen"
    (evidence_dir / "environment.json").write_text(
        json.dumps(environment),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert "error=environment tmux_binary must point to tmux" in result.stdout


def test_admin_target_evidence_check_rejects_weak_notify_send_environment(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    environment = _target_environment_report()
    environment.pop("notify_send")
    _write_complete_target_evidence_bundle(evidence_dir, environment=environment)

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert "error=environment notify_send is required" in result.stdout

    environment["notify_send"] = "notify-send"
    (evidence_dir / "environment.json").write_text(
        json.dumps(environment),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert "error=environment notify_send must be an absolute path" in result.stdout

    environment["notify_send"] = "/usr/bin/notify"
    (evidence_dir / "environment.json").write_text(
        json.dumps(environment),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert "error=environment notify_send must point to notify-send" in result.stdout


def test_admin_target_evidence_check_rejects_weak_environment_paths(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    environment = _target_environment_report()
    environment["paths"] = {
        "config_dir": "relative-config",
        "state_dir": "/home/user/.local/state/coding-pet",
        "runtime_dir": "/tmp/coding-pet",
        "state_file": "/home/user/.local/state/coding-pet/state.json",
        "transcript_db": "/tmp/other-transcripts.sqlite",
    }
    _write_complete_target_evidence_bundle(evidence_dir, environment=environment)

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert "error=environment paths.log_dir is required" in result.stdout
    assert "error=environment paths.config_dir must be an absolute path" in result.stdout
    assert "error=environment paths.runtime_dir must be under /run/user" in result.stdout
    assert "error=environment transcript.db_path must match paths.transcript_db" in result.stdout


def test_admin_target_evidence_check_rejects_incomplete_acceptance_checks(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    _write_complete_target_evidence_bundle(
        evidence_dir,
        acceptance={"ok": True, "profile": "target", "failed_required": [], "checks": []},
    )

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert "error=acceptance missing required check linux" in result.stdout
    assert "error=acceptance missing required check backend_claude_code" in result.stdout


def test_admin_target_evidence_check_rejects_missing_dependency_and_path_acceptance_checks(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    _write_complete_target_evidence_bundle(evidence_dir)
    acceptance_path = evidence_dir / "acceptance-target.json"
    acceptance = json.loads(acceptance_path.read_text("utf-8"))
    checks = acceptance["checks"]
    assert isinstance(checks, list)
    acceptance["checks"] = [
        check
        for check in checks
        if not (
            isinstance(check, dict)
            and check.get("name") in {"dependency_pillow", "path_runtime_dir"}
        )
    ]
    acceptance_path.write_text(json.dumps(acceptance), encoding="utf-8")

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert "error=acceptance missing required check dependency_pillow" in result.stdout
    assert "error=acceptance missing required check path_runtime_dir" in result.stdout


def test_admin_target_evidence_check_rejects_weak_backend_binary_paths(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    environment = _target_environment_report()
    backends = environment["backends"]
    assert isinstance(backends, list)
    claude_backend = next(
        backend
        for backend in backends
        if isinstance(backend, dict) and backend.get("agent_kind") == "claude_code"
    )
    opencode_backend = next(
        backend
        for backend in backends
        if isinstance(backend, dict) and backend.get("agent_kind") == "opencode"
    )
    claude_backend.pop("binary_path")
    opencode_backend["binary_path"] = "opencode"
    _write_complete_target_evidence_bundle(evidence_dir, environment=environment)

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert "error=environment backend claude_code binary_path is required" in result.stdout
    assert (
        "error=environment backend opencode binary_path must be an absolute path" in result.stdout
    )

    claude_backend["binary_path"] = "/usr/bin/claude-code"
    opencode_backend["binary_path"] = "/usr/local/bin/opencode"
    (evidence_dir / "environment.json").write_text(
        json.dumps(environment),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert "error=environment backend claude_code binary_path must point to claude" in result.stdout
    assert (
        "error=environment backend opencode binary_path must match available reason"
        in result.stdout
    )


def test_admin_target_evidence_check_rejects_failing_required_acceptance_check(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    _write_complete_target_evidence_bundle(evidence_dir)
    acceptance_path = evidence_dir / "acceptance-target.json"
    acceptance = json.loads(acceptance_path.read_text("utf-8"))
    checks = acceptance["checks"]
    assert isinstance(checks, list)
    checks.append(
        {
            "name": "company_certificate_store",
            "ok": False,
            "required": True,
            "detail": "missing",
        }
    )
    acceptance_path.write_text(json.dumps(acceptance), encoding="utf-8")

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert "error=acceptance check company_certificate_store ok must be true" in result.stdout


def test_admin_target_evidence_check_rejects_duplicate_acceptance_check_names(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    _write_complete_target_evidence_bundle(evidence_dir)
    acceptance_path = evidence_dir / "acceptance-target.json"
    acceptance = json.loads(acceptance_path.read_text("utf-8"))
    checks = acceptance["checks"]
    assert isinstance(checks, list)
    checks.insert(
        0,
        {
            "name": "python",
            "ok": False,
            "required": True,
            "detail": "shadowed duplicate",
        },
    )
    acceptance_path.write_text(json.dumps(acceptance), encoding="utf-8")

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert "error=acceptance duplicate check python" in result.stdout


def test_admin_target_evidence_check_rejects_transcript_redaction_disabled(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    environment = _target_environment_report()
    raw_transcript = environment["transcript"]
    assert isinstance(raw_transcript, dict)
    transcript = dict(raw_transcript)
    transcript["redact_secrets"] = False
    environment["transcript"] = transcript
    _write_complete_target_evidence_bundle(evidence_dir, environment=environment)

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert "error=environment transcript.redact_secrets must be true" in result.stdout


def test_admin_target_evidence_check_rejects_unbounded_transcript_retention(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    environment = _target_environment_report()
    raw_transcript = environment["transcript"]
    assert isinstance(raw_transcript, dict)
    transcript = dict(raw_transcript)
    transcript["max_events_per_session"] = 0
    environment["transcript"] = transcript
    _write_complete_target_evidence_bundle(evidence_dir, environment=environment)

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert "error=environment transcript.max_events_per_session must be positive" in result.stdout


def test_admin_target_evidence_check_rejects_weak_environment_theme(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    environment = _target_environment_report()
    environment["theme"] = {"ok": True, "detail": ""}
    _write_complete_target_evidence_bundle(evidence_dir, environment=environment)

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert "error=environment theme.name is required" in result.stdout
    assert "error=environment theme.detail is required" in result.stdout


def test_admin_target_evidence_check_rejects_backend_control_text_mismatch(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    _write_complete_target_evidence_bundle(evidence_dir)
    report_path = evidence_dir / "backend-opencode-reject.json"
    report = json.loads(report_path.read_text("utf-8"))
    report["action_result"]["delivered_text"] = "no"
    report_path.write_text(json.dumps(report), encoding="utf-8")

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert (
        "error=backend-opencode-reject.json: delivered_text must match "
        "environment opencode reject control message"
    ) in result.stdout


def test_admin_target_evidence_check_rejects_missing_widget_smoke(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    _write_complete_target_evidence_bundle(evidence_dir)
    (evidence_dir / "widget-smoke.json").unlink()

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert "error=widget-smoke.json could not be read" in result.stdout


def test_admin_target_evidence_check_rejects_missing_systemd_runtime(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    _write_complete_target_evidence_bundle(evidence_dir)
    (evidence_dir / "systemd-runtime.json").unlink()

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert "error=systemd-runtime.json could not be read" in result.stdout


def test_admin_target_evidence_check_rejects_unversioned_systemd_and_tmux_reports(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    _write_complete_target_evidence_bundle(evidence_dir)
    for filename in ("tmux-control.json", "systemd-units.json", "systemd-runtime.json"):
        report_path = evidence_dir / filename
        report = json.loads(report_path.read_text("utf-8"))
        report.pop("schema_version")
        report["generated_at"] = "not-a-timestamp"
        report_path.write_text(json.dumps(report), encoding="utf-8")

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert "error=tmux_control schema_version must be 1" in result.stdout
    assert "error=tmux_control generated_at must be ISO 8601" in result.stdout
    assert "error=systemd_units schema_version must be 1" in result.stdout
    assert "error=systemd_units generated_at must be ISO 8601" in result.stdout
    assert "error=systemd_runtime schema_version must be 1" in result.stdout
    assert "error=systemd_runtime generated_at must be ISO 8601" in result.stdout


def test_admin_target_evidence_check_rejects_weak_tmux_control_probe(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    _write_complete_target_evidence_bundle(evidence_dir)
    control_path = evidence_dir / "tmux-control.json"
    control = json.loads(control_path.read_text("utf-8"))
    control["session_name"] = ""
    control["pane_id"] = None
    control["expected_text"] = "hello"
    control["observed_text"] = "hello?"
    control["detail"] = "raw tmux input mismatch"
    control_path.write_text(json.dumps(control), encoding="utf-8")

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert "error=tmux_control session_name is required" in result.stdout
    assert "error=tmux_control pane_id is required" in result.stdout
    assert "error=tmux_control expected_text must match default probe text" in result.stdout
    assert "error=tmux_control observed_text must match expected_text" in result.stdout
    assert "error=tmux_control detail must be raw tmux input preserved" in result.stdout


def test_admin_target_evidence_check_rejects_weak_systemd_unit_verification(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    _write_complete_target_evidence_bundle(evidence_dir)
    units_path = evidence_dir / "systemd-units.json"
    units = json.loads(units_path.read_text("utf-8"))
    units["units"] = [
        "/opt/coding-pet/share/coding-pet/systemd/coding-pet-daemon.service",
        "/opt/coding-pet/share/coding-pet/systemd/coding-pet.target",
    ]
    units["command"] = [
        "systemd-analyze",
        "verify",
        "/opt/coding-pet/share/coding-pet/systemd/coding-pet-daemon.service",
    ]
    units["returncode"] = 1
    units_path.write_text(json.dumps(units), encoding="utf-8")

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert "error=systemd_units missing unit coding-pet-widget.service" in result.stdout
    assert (
        "error=systemd_units command must start with absolute systemd-analyze path" in result.stdout
    )
    assert "error=systemd_units command must include --user verify" in result.stdout
    assert "error=systemd_units returncode must be 0" in result.stdout


def test_admin_target_evidence_check_rejects_non_exact_systemd_unit_verification(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    _write_complete_target_evidence_bundle(evidence_dir)
    units_path = evidence_dir / "systemd-units.json"
    units = json.loads(units_path.read_text("utf-8"))
    duplicate_unit = units["units"][0]
    extra_unit = "/opt/coding-pet/share/coding-pet/systemd/coding-pet-extra.service"
    units["units"].extend([duplicate_unit, extra_unit])
    units["command"].extend([duplicate_unit, extra_unit])
    units_path.write_text(json.dumps(units), encoding="utf-8")

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert (
        "error=systemd_units units must contain exactly "
        "coding-pet-daemon.service, coding-pet-widget.service, coding-pet.target"
    ) in result.stdout
    assert "error=systemd_units duplicate unit coding-pet-daemon.service" in result.stdout
    assert "error=systemd_units unexpected unit coding-pet-extra.service" in result.stdout
    assert "error=systemd_units command must match verified units" in result.stdout


def test_admin_target_evidence_check_rejects_missing_hook_event_smoke(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    _write_complete_target_evidence_bundle(evidence_dir)
    (evidence_dir / "hook-event-smoke.json").unlink()

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert "error=hook-event-smoke.json could not be read" in result.stdout


def test_admin_target_evidence_check_rejects_unversioned_widget_and_hook_smoke_reports(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    _write_complete_target_evidence_bundle(evidence_dir)
    widget_smoke_path = evidence_dir / "widget-smoke.json"
    widget_smoke = json.loads(widget_smoke_path.read_text("utf-8"))
    widget_smoke.pop("schema_version")
    widget_smoke["generated_at"] = "not-a-timestamp"
    widget_smoke_path.write_text(json.dumps(widget_smoke), encoding="utf-8")
    hook_smoke_path = evidence_dir / "hook-event-smoke.json"
    hook_smoke = json.loads(hook_smoke_path.read_text("utf-8"))
    hook_smoke.pop("schema_version")
    hook_smoke["generated_at"] = "not-a-timestamp"
    hook_smoke_path.write_text(json.dumps(hook_smoke), encoding="utf-8")

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert "error=widget_smoke schema_version must be 1" in result.stdout
    assert "error=widget_smoke generated_at must be ISO 8601" in result.stdout
    assert "error=hook_event_smoke schema_version must be 1" in result.stdout
    assert "error=hook_event_smoke generated_at must be ISO 8601" in result.stdout


def test_admin_target_evidence_check_rejects_missing_optional_bundle_artifacts(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    _write_complete_target_evidence_bundle(evidence_dir)
    (evidence_dir / "wheelhouse.json").unlink()
    (evidence_dir / "pet-packages.json").unlink()
    (evidence_dir / "agent-hooks.json").unlink()

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert "error=wheelhouse.json could not be read" in result.stdout
    assert "error=pet-packages.json could not be read" in result.stdout
    assert "error=agent-hooks.json could not be read" in result.stdout


def test_admin_target_evidence_check_rejects_unversioned_optional_bundle_reports(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    _write_complete_target_evidence_bundle(evidence_dir)
    for filename in ("wheelhouse.json", "pet-packages.json", "agent-hooks.json"):
        report_path = evidence_dir / filename
        report = json.loads(report_path.read_text("utf-8"))
        report.pop("schema_version")
        report["generated_at"] = "not-a-timestamp"
        report_path.write_text(json.dumps(report), encoding="utf-8")

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert "error=wheelhouse schema_version must be 1" in result.stdout
    assert "error=wheelhouse generated_at must be ISO 8601" in result.stdout
    assert "error=pet_packages schema_version must be 1" in result.stdout
    assert "error=pet_packages generated_at must be ISO 8601" in result.stdout
    assert "error=agent_hooks schema_version must be 1" in result.stdout
    assert "error=agent_hooks generated_at must be ISO 8601" in result.stdout


def test_admin_target_evidence_check_rejects_non_target_profile_reports(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    _write_complete_target_evidence_bundle(evidence_dir)
    profile_files = {
        "tmux-control.json": "tmux_control",
        "systemd-units.json": "systemd_units",
        "systemd-runtime.json": "systemd_runtime",
        "widget-smoke.json": "widget_smoke",
        "hook-event-smoke.json": "hook_event_smoke",
        "wheelhouse.json": "wheelhouse",
        "pet-packages.json": "pet_packages",
        "agent-hooks.json": "agent_hooks",
    }
    for filename in profile_files:
        report_path = evidence_dir / filename
        report = json.loads(report_path.read_text("utf-8"))
        report["profile"] = "current"
        report_path.write_text(json.dumps(report), encoding="utf-8")

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    for label in profile_files.values():
        assert f"error={label} profile must be target, got 'current'" in result.stdout


def test_admin_target_evidence_check_rejects_weak_optional_evidence_status(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    _write_complete_target_evidence_bundle(evidence_dir)
    (evidence_dir / "wheelhouse.json").write_text(
        json.dumps({"ok": "yes", "required": "no", "skipped": "no"}),
        encoding="utf-8",
    )
    (evidence_dir / "pet-packages.json").write_text(
        json.dumps({"ok": False, "required": False}),
        encoding="utf-8",
    )
    (evidence_dir / "agent-hooks.json").write_text(
        json.dumps({"ok": "no", "required": "no", "checks": "bad"}),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert "error=wheelhouse ok must be boolean" in result.stdout
    assert "error=wheelhouse required must be boolean" in result.stdout
    assert "error=wheelhouse skipped must be boolean" in result.stdout
    assert "error=pet_packages skipped must be boolean" in result.stdout
    assert "error=agent_hooks ok must be boolean" in result.stdout
    assert "error=agent_hooks required must be boolean" in result.stdout
    assert "error=agent_hooks checks must be a list" in result.stdout


def test_admin_target_evidence_check_rejects_unverified_hook_event_smoke(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    _write_complete_target_evidence_bundle(evidence_dir)
    smoke_path = evidence_dir / "hook-event-smoke.json"
    smoke = json.loads(smoke_path.read_text("utf-8"))
    smoke["ok"] = False
    smoke["transcript"]["verified"] = False
    smoke_path.write_text(json.dumps(smoke), encoding="utf-8")

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert "error=hook_event_smoke ok must be true" in result.stdout
    assert "error=hook_event_smoke transcript.verified must be true" in result.stdout


def test_admin_target_evidence_check_rejects_inconsistent_hook_event_smoke_status(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    _write_complete_target_evidence_bundle(evidence_dir)
    smoke_path = evidence_dir / "hook-event-smoke.json"
    smoke = json.loads(smoke_path.read_text("utf-8"))
    smoke["hook_result"]["state"] = "failed"
    smoke["errors"] = ["hook event failed but ok stayed true"]
    smoke_path.write_text(json.dumps(smoke), encoding="utf-8")

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert "error=hook_event_smoke errors must be empty" in result.stdout
    assert "error=hook_event_smoke hook_result.state must be running" in result.stdout


def test_admin_target_evidence_check_rejects_weak_hook_event_smoke_manifest(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    _write_complete_target_evidence_bundle(evidence_dir)
    smoke_path = evidence_dir / "hook-event-smoke.json"
    smoke = json.loads(smoke_path.read_text("utf-8"))
    smoke["event"] = {
        "agent": "codex",
        "event": "PostToolUse",
        "session_id": "",
        "workspace": "",
    }
    smoke["transcript"]["events"] = 0
    smoke["cleanup_result"]["action"] = "noop"
    smoke_path.write_text(json.dumps(smoke), encoding="utf-8")

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert "error=hook_event_smoke event.agent must be claude_code or opencode" in result.stdout
    assert "error=hook_event_smoke event.event must be PreToolUse" in result.stdout
    assert "error=hook_event_smoke event.session_id is required" in result.stdout
    assert "error=hook_event_smoke event.workspace is required" in result.stdout
    assert "error=hook_event_smoke transcript.events must be positive" in result.stdout
    assert "error=hook_event_smoke cleanup_result.action must be hide_pet" in result.stdout


def test_admin_target_evidence_check_rejects_hook_event_workspace_session_mismatch(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    _write_complete_target_evidence_bundle(evidence_dir)
    smoke_path = evidence_dir / "hook-event-smoke.json"
    smoke = json.loads(smoke_path.read_text("utf-8"))
    smoke["event"]["session_id"] = "unexpected-session"
    smoke["event"]["workspace"] = "relative-workspace"
    smoke_path.write_text(json.dumps(smoke), encoding="utf-8")

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert "error=hook_event_smoke event.session_id must be coding-pet-hook-smoke" in result.stdout
    assert "error=hook_event_smoke event.workspace must be an absolute path" in result.stdout


def test_admin_target_evidence_check_rejects_hook_result_session_identity_mismatch(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    _write_complete_target_evidence_bundle(evidence_dir)
    smoke_path = evidence_dir / "hook-event-smoke.json"
    smoke = json.loads(smoke_path.read_text("utf-8"))
    smoke["hook_result"]["session_id"] = "hook-claude_code-other-session"
    smoke["transcript"]["session_id"] = "hook-claude_code-other-session"
    smoke["cleanup_result"]["session_id"] = "hook-claude_code-other-session"
    smoke_path.write_text(json.dumps(smoke), encoding="utf-8")

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert (
        "error=hook_event_smoke hook_result.session_id must match "
        "hook-claude_code-coding-pet-hook-smoke"
    ) in result.stdout


def test_admin_target_evidence_check_rejects_weak_hook_event_socket_path(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    _write_complete_target_evidence_bundle(evidence_dir)
    smoke_path = evidence_dir / "hook-event-smoke.json"
    smoke = json.loads(smoke_path.read_text("utf-8"))
    smoke["socket_path"] = "coding-pet.sock"
    smoke_path.write_text(json.dumps(smoke), encoding="utf-8")

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert "error=hook_event_smoke socket_path must be an absolute path" in result.stdout

    smoke["socket_path"] = "/tmp/coding-pet.sock"
    smoke_path.write_text(json.dumps(smoke), encoding="utf-8")

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert (
        "error=hook_event_smoke socket_path must be under environment runtime_dir" in result.stdout
    )

    smoke["socket_path"] = "/run/user/1000/coding-pet/not-coding-pet.sock"
    smoke_path.write_text(json.dumps(smoke), encoding="utf-8")

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert "error=hook_event_smoke socket_path must point to coding-pet.sock" in result.stdout


def test_admin_target_evidence_check_rejects_hook_event_transcript_db_mismatch(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    _write_complete_target_evidence_bundle(evidence_dir)
    smoke_path = evidence_dir / "hook-event-smoke.json"
    smoke = json.loads(smoke_path.read_text("utf-8"))
    smoke["transcript"]["db_path"] = "relative/transcripts.sqlite"
    smoke_path.write_text(json.dumps(smoke), encoding="utf-8")

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert "error=hook_event_smoke transcript.db_path must be an absolute path" in result.stdout

    smoke["transcript"]["db_path"] = "/tmp/other-transcripts.sqlite"
    smoke_path.write_text(json.dumps(smoke), encoding="utf-8")

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert (
        "error=hook_event_smoke transcript.db_path must match environment transcript.db_path"
        in result.stdout
    )


def test_admin_target_evidence_check_rejects_hook_event_session_mismatch(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    _write_complete_target_evidence_bundle(evidence_dir)
    smoke_path = evidence_dir / "hook-event-smoke.json"
    smoke = json.loads(smoke_path.read_text("utf-8"))
    smoke["transcript"]["session_id"] = "different-transcript-session"
    smoke["cleanup_result"]["session_id"] = "different-cleanup-session"
    smoke_path.write_text(json.dumps(smoke), encoding="utf-8")

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert (
        "error=hook_event_smoke transcript.session_id must match hook_result.session_id"
        in result.stdout
    )
    assert (
        "error=hook_event_smoke cleanup_result.session_id must match hook_result.session_id"
        in result.stdout
    )


def test_admin_target_evidence_check_rejects_weak_hook_event_cleanup_outcome(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    _write_complete_target_evidence_bundle(evidence_dir)
    smoke_path = evidence_dir / "hook-event-smoke.json"
    smoke = json.loads(smoke_path.read_text("utf-8"))
    smoke["cleanup_result"].pop("outcome")
    smoke_path.write_text(json.dumps(smoke), encoding="utf-8")

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert "error=hook_event_smoke cleanup_result.outcome must be local_updated" in result.stdout

    smoke["cleanup_result"]["outcome"] = "accepted"
    smoke_path.write_text(json.dumps(smoke), encoding="utf-8")

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert "error=hook_event_smoke cleanup_result.outcome must be local_updated" in result.stdout


def test_admin_target_evidence_check_rejects_weak_hook_event_cleanup_detail(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    _write_complete_target_evidence_bundle(evidence_dir)
    smoke_path = evidence_dir / "hook-event-smoke.json"
    smoke = json.loads(smoke_path.read_text("utf-8"))
    smoke["cleanup_result"]["reason"] = "delivered"
    smoke["cleanup_result"]["detail"] = ""
    smoke_path.write_text(json.dumps(smoke), encoding="utf-8")

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert "error=hook_event_smoke cleanup_result.reason must be hidden" in result.stdout
    assert "error=hook_event_smoke cleanup_result.detail is required" in result.stdout


def test_admin_target_evidence_check_rejects_inactive_systemd_runtime(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    _write_complete_target_evidence_bundle(evidence_dir)
    runtime_path = evidence_dir / "systemd-runtime.json"
    runtime = json.loads(runtime_path.read_text("utf-8"))
    runtime["ok"] = False
    runtime["units"][1]["state"] = "failed"
    runtime["units"][1]["ok"] = False
    runtime_path.write_text(json.dumps(runtime), encoding="utf-8")

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert "error=systemd_runtime ok must be true" in result.stdout
    assert "error=systemd_runtime unit coding-pet-widget.service must be active" in result.stdout


def test_admin_target_evidence_check_rejects_non_exact_systemd_runtime_units(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    _write_complete_target_evidence_bundle(evidence_dir)
    runtime_path = evidence_dir / "systemd-runtime.json"
    runtime = json.loads(runtime_path.read_text("utf-8"))
    duplicate_unit = dict(runtime["units"][0])
    extra_unit = {
        "unit": "coding-pet-extra.service",
        "state": "active",
        "ok": True,
        "returncode": 0,
        "command": [
            "/usr/bin/systemctl",
            "--user",
            "is-active",
            "coding-pet-extra.service",
        ],
    }
    runtime["units"].extend([duplicate_unit, extra_unit])
    runtime_path.write_text(json.dumps(runtime), encoding="utf-8")

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert (
        "error=systemd_runtime units must contain exactly "
        "coding-pet-daemon.service, coding-pet-widget.service, coding-pet.target"
    ) in result.stdout
    assert "error=systemd_runtime duplicate unit coding-pet-daemon.service" in result.stdout
    assert "error=systemd_runtime unexpected unit coding-pet-extra.service" in result.stdout


def test_admin_target_evidence_check_rejects_weak_systemd_runtime_command_evidence(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    _write_complete_target_evidence_bundle(evidence_dir)
    runtime_path = evidence_dir / "systemd-runtime.json"
    runtime = json.loads(runtime_path.read_text("utf-8"))
    runtime["systemctl"] = "systemctl"
    runtime["user_manager"]["returncode"] = 1
    runtime["target_enabled"]["returncode"] = 1
    runtime["units"][0].pop("returncode")
    runtime["units"][1]["returncode"] = 3
    runtime_path.write_text(json.dumps(runtime), encoding="utf-8")

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert "error=systemd_runtime systemctl must be an absolute systemctl path" in result.stdout
    assert "error=systemd_runtime user manager returncode must be 0" in result.stdout
    assert "error=systemd_runtime target_enabled.returncode must be 0" in result.stdout
    assert (
        "error=systemd_runtime unit coding-pet-daemon.service returncode must be 0" in result.stdout
    )
    assert (
        "error=systemd_runtime unit coding-pet-widget.service returncode must be 0" in result.stdout
    )


def test_admin_target_evidence_check_rejects_systemd_runtime_command_mismatch(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    _write_complete_target_evidence_bundle(evidence_dir)
    runtime_path = evidence_dir / "systemd-runtime.json"
    runtime = json.loads(runtime_path.read_text("utf-8"))
    runtime["user_manager"]["command"] = ["systemctl", "--user", "status"]
    runtime["target_enabled"]["command"] = [
        "/usr/bin/systemctl",
        "--user",
        "is-active",
        "coding-pet.target",
    ]
    runtime["units"][0].pop("command")
    runtime["units"][1]["command"] = [
        "/usr/bin/systemctl",
        "--user",
        "is-enabled",
        "coding-pet-widget.service",
    ]
    runtime_path.write_text(json.dumps(runtime), encoding="utf-8")

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert (
        "error=systemd_runtime user_manager.command must be systemctl --user status"
    ) in result.stdout
    assert (
        "error=systemd_runtime target_enabled.command must be "
        "systemctl --user is-enabled coding-pet.target"
    ) in result.stdout
    assert (
        "error=systemd_runtime unit coding-pet-daemon.service command must be "
        "systemctl --user is-active coding-pet-daemon.service"
    ) in result.stdout
    assert (
        "error=systemd_runtime unit coding-pet-widget.service command must be "
        "systemctl --user is-active coding-pet-widget.service"
    ) in result.stdout


def test_admin_target_evidence_check_rejects_unenabled_systemd_target(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    _write_complete_target_evidence_bundle(evidence_dir)
    runtime_path = evidence_dir / "systemd-runtime.json"
    runtime = json.loads(runtime_path.read_text("utf-8"))
    runtime["target_enabled"] = {
        "unit": "coding-pet-widget.service",
        "state": "disabled",
        "ok": True,
    }
    runtime_path.write_text(json.dumps(runtime), encoding="utf-8")

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert "error=systemd_runtime target_enabled.unit must be coding-pet.target" in result.stdout
    assert "error=systemd_runtime target coding-pet.target state must be enabled" in result.stdout


def test_admin_target_evidence_check_rejects_non_desktop_systemd_runtime(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    _write_complete_target_evidence_bundle(evidence_dir)
    runtime_path = evidence_dir / "systemd-runtime.json"
    runtime = json.loads(runtime_path.read_text("utf-8"))
    runtime["session_environment"] = {
        "has_display": False,
        "has_wayland_display": False,
        "has_xdg_runtime_dir": False,
        "has_dbus_session_bus": False,
    }
    runtime["user_manager"] = {"ok": False, "returncode": 1}
    runtime_path.write_text(json.dumps(runtime), encoding="utf-8")

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert "error=systemd_runtime user manager must be reachable" in result.stdout
    assert (
        "error=systemd_runtime session_environment.XDG_RUNTIME_DIR must be present" in result.stdout
    )
    assert (
        "error=systemd_runtime session_environment DISPLAY or WAYLAND_DISPLAY must be present"
    ) in result.stdout
    assert (
        "error=systemd_runtime session_environment DBUS_SESSION_BUS_ADDRESS must be present"
    ) in result.stdout


def test_admin_target_evidence_check_rejects_weak_systemd_runtime_session_values(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    _write_complete_target_evidence_bundle(evidence_dir)
    runtime_path = evidence_dir / "systemd-runtime.json"
    runtime = json.loads(runtime_path.read_text("utf-8"))
    runtime["session_environment"] = {
        "has_display": True,
        "has_wayland_display": False,
        "has_xdg_runtime_dir": True,
        "has_dbus_session_bus": True,
        "DISPLAY": "",
        "XDG_RUNTIME_DIR": "relative-runtime",
        "DBUS_SESSION_BUS_ADDRESS": "unix:path=/tmp/bus",
    }
    runtime_path.write_text(json.dumps(runtime), encoding="utf-8")

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert (
        "error=systemd_runtime session_environment.XDG_RUNTIME_DIR value must "
        "be an absolute /run/user path"
    ) in result.stdout
    assert (
        "error=systemd_runtime session_environment DISPLAY or WAYLAND_DISPLAY "
        "value must be recorded"
    ) in result.stdout
    assert (
        "error=systemd_runtime session_environment.DBUS_SESSION_BUS_ADDRESS "
        "value must use /run/user bus"
    ) in result.stdout


def test_admin_systemd_runtime_check_requires_dbus_session_bus(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class FakeCompletedProcess:
        def __init__(self, stdout: str, returncode: int = 0) -> None:
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = ""

    def fake_run(command: list[str], **_: object) -> FakeCompletedProcess:
        if command[-2:] == ["is-enabled", "coding-pet.target"]:
            return FakeCompletedProcess("enabled\n")
        if command[2] == "status":
            return FakeCompletedProcess("user manager ready\n")
        return FakeCompletedProcess("active\n")

    monkeypatch.setenv("DISPLAY", ":1")
    monkeypatch.setenv("XDG_RUNTIME_DIR", "/run/user/1000")
    monkeypatch.delenv("DBUS_SESSION_BUS_ADDRESS", raising=False)
    monkeypatch.setattr(
        "coding_pet.cli.shutil.which",
        lambda name: "/usr/bin/systemctl" if name == "systemctl" else None,
    )
    monkeypatch.setattr("coding_pet.cli.subprocess.run", fake_run)
    report_path = tmp_path / "systemd-runtime.json"

    result = runner.invoke(
        app,
        ["admin", "systemd-runtime-check", "--json-out", str(report_path)],
    )
    report = json.loads(report_path.read_text("utf-8"))

    assert result.exit_code != 0
    assert "systemd_runtime=failed" in result.stdout
    assert report["ok"] is False
    assert "DBUS_SESSION_BUS_ADDRESS is required for desktop user services" in report["errors"]


def test_admin_target_evidence_check_rejects_unvalidated_widget_smoke(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    _write_complete_target_evidence_bundle(evidence_dir)
    widget_smoke_path = evidence_dir / "widget-smoke.json"
    widget_smoke = json.loads(widget_smoke_path.read_text("utf-8"))
    widget_smoke["ok"] = False
    widget_smoke["gui_validated"] = False
    widget_smoke_path.write_text(json.dumps(widget_smoke), encoding="utf-8")

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert "error=widget_smoke ok must be true" in result.stdout
    assert "error=widget_smoke gui_validated must be true" in result.stdout


def test_admin_target_evidence_check_rejects_invalid_widget_theme_smoke(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    _write_complete_target_evidence_bundle(evidence_dir)
    widget_smoke_path = evidence_dir / "widget-smoke.json"
    widget_smoke = json.loads(widget_smoke_path.read_text("utf-8"))
    widget_smoke["theme"] = ""
    widget_smoke["theme_ok"] = False
    widget_smoke_path.write_text(json.dumps(widget_smoke), encoding="utf-8")

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert "error=widget_smoke theme is required" in result.stdout
    assert "error=widget_smoke theme_ok must be true" in result.stdout


def test_admin_target_evidence_check_rejects_removed_legacy_theme_name(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    _write_complete_target_evidence_bundle(evidence_dir)
    environment_path = evidence_dir / "environment.json"
    environment = json.loads(environment_path.read_text("utf-8"))
    environment["theme"] = {
        "name": "company-pet",
        "ok": True,
        "detail": "company-pet:coding_pet",
    }
    environment_path.write_text(json.dumps(environment), encoding="utf-8")
    widget_smoke_path = evidence_dir / "widget-smoke.json"
    widget_smoke = json.loads(widget_smoke_path.read_text("utf-8"))
    widget_smoke["theme"] = "company-pet"
    widget_smoke_path.write_text(json.dumps(widget_smoke), encoding="utf-8")

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert (
        "error=environment theme.name must not use removed legacy theme company-pet"
        in result.stdout
    )
    assert "error=widget_smoke theme must not use removed legacy theme company-pet" in result.stdout


def test_admin_target_evidence_check_rejects_unresolved_widget_sprite_asset(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    _write_complete_target_evidence_bundle(evidence_dir)
    widget_smoke_path = evidence_dir / "widget-smoke.json"
    widget_smoke = json.loads(widget_smoke_path.read_text("utf-8"))
    widget_smoke["sprite_asset"] = "codex-default/alert.png"
    widget_smoke_path.write_text(json.dumps(widget_smoke), encoding="utf-8")

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert "error=widget_smoke sprite_asset must be an absolute path" in result.stdout


def test_admin_target_evidence_check_rejects_unresolved_widget_surface_sprites(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    _write_complete_target_evidence_bundle(evidence_dir)
    widget_smoke_path = evidence_dir / "widget-smoke.json"
    widget_smoke = json.loads(widget_smoke_path.read_text("utf-8"))
    action_surfaces = widget_smoke["action_surfaces"]
    assert isinstance(action_surfaces, dict)
    needs_permission = action_surfaces["needs_permission"]
    needs_input = action_surfaces["needs_input"]
    assert isinstance(needs_permission, dict)
    assert isinstance(needs_input, dict)
    needs_permission["sprite_asset"] = ""
    needs_input["sprite_asset"] = "codex-default/alert.png"
    widget_smoke_path.write_text(json.dumps(widget_smoke), encoding="utf-8")

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert (
        "error=widget_smoke action_surfaces.needs_permission sprite_asset is required"
        in result.stdout
    )
    assert (
        "error=widget_smoke action_surfaces.needs_input sprite_asset must be an absolute path"
    ) in result.stdout


def test_admin_target_evidence_check_rejects_removed_legacy_widget_sprite_assets(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    _write_complete_target_evidence_bundle(evidence_dir)
    widget_smoke_path = evidence_dir / "widget-smoke.json"
    widget_smoke = json.loads(widget_smoke_path.read_text("utf-8"))
    widget_smoke["sprite_asset"] = "/tmp/company-pet/alert.png"
    action_surfaces = widget_smoke["action_surfaces"]
    assert isinstance(action_surfaces, dict)
    needs_permission = action_surfaces["needs_permission"]
    needs_input = action_surfaces["needs_input"]
    assert isinstance(needs_permission, dict)
    assert isinstance(needs_input, dict)
    needs_permission["sprite_asset"] = "/tmp/company-pet/alert.png"
    needs_input["sprite_asset"] = "/tmp/company-pet/alert.png"
    widget_smoke_path.write_text(json.dumps(widget_smoke), encoding="utf-8")

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert (
        "error=widget_smoke sprite_asset must not point at a removed legacy theme asset"
        in result.stdout
    )
    assert (
        "error=widget_smoke action_surfaces.needs_permission sprite_asset must not "
        "point at a removed legacy theme asset"
    ) in result.stdout
    assert (
        "error=widget_smoke action_surfaces.needs_input sprite_asset must not "
        "point at a removed legacy theme asset"
    ) in result.stdout


def test_admin_target_evidence_check_rejects_weak_permission_surface_presentation(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    _write_complete_target_evidence_bundle(evidence_dir)
    widget_smoke_path = evidence_dir / "widget-smoke.json"
    widget_smoke = json.loads(widget_smoke_path.read_text("utf-8"))
    action_surfaces = widget_smoke["action_surfaces"]
    assert isinstance(action_surfaces, dict)
    needs_permission = action_surfaces["needs_permission"]
    assert isinstance(needs_permission, dict)
    needs_permission["presentation"] = {"mood": "idle", "bubble_text": ""}
    widget_smoke_path.write_text(json.dumps(widget_smoke), encoding="utf-8")

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert (
        "error=widget_smoke action_surfaces.needs_permission presentation.mood must be alert"
    ) in result.stdout
    assert (
        "error=widget_smoke action_surfaces.needs_permission presentation.bubble_text is required"
    ) in result.stdout


def test_admin_target_evidence_check_rejects_widget_theme_environment_mismatch(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    _write_complete_target_evidence_bundle(evidence_dir)
    widget_smoke_path = evidence_dir / "widget-smoke.json"
    widget_smoke = json.loads(widget_smoke_path.read_text("utf-8"))
    widget_smoke["theme"] = "different-pet"
    widget_smoke_path.write_text(json.dumps(widget_smoke), encoding="utf-8")

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert "error=widget_smoke theme must match environment theme" in result.stdout


def test_admin_target_evidence_check_rejects_widget_smoke_missing_action_surface(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    _write_complete_target_evidence_bundle(evidence_dir)
    widget_smoke_path = evidence_dir / "widget-smoke.json"
    widget_smoke = json.loads(widget_smoke_path.read_text("utf-8"))
    widget_smoke["available_actions"] = ["open_workspace"]
    widget_smoke["presentation"] = {"mood": "idle", "bubble_text": ""}
    widget_smoke["action_surfaces"]["needs_input"]["available_actions"] = ["open_workspace"]
    widget_smoke["action_surfaces"]["needs_input"]["reply_shortcuts"] = []
    widget_smoke_path.write_text(json.dumps(widget_smoke), encoding="utf-8")

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert "error=widget_smoke available_actions must include approve and reject" in result.stdout
    assert "error=widget_smoke presentation.mood must be alert" in result.stdout
    assert "error=widget_smoke presentation.bubble_text is required" in result.stdout
    assert (
        "error=widget_smoke action_surfaces.needs_input available_actions must include send_reply"
    ) in result.stdout
    assert (
        "error=widget_smoke action_surfaces.needs_input reply_shortcuts is required"
        in result.stdout
    )


def test_admin_target_evidence_check_rejects_backend_summary_delivered_text_mismatch(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    _write_complete_target_evidence_bundle(evidence_dir)
    report_path = evidence_dir / "backend-opencode-send_reply.json"
    report = json.loads(report_path.read_text("utf-8"))
    report["action_result"]["delivered_text"] = "wrong reply"
    report_path.write_text(json.dumps(report), encoding="utf-8")

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert (
        "error=backend-opencode-send_reply.json: delivered_text must match "
        "backend_summary expected_delivered_text"
    ) in result.stdout


def test_admin_target_evidence_check_rejects_missing_backend_summary_delivered_text(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    _write_complete_target_evidence_bundle(evidence_dir)
    summary_path = evidence_dir / "backend-summary.json"
    summary = json.loads(summary_path.read_text("utf-8"))
    summary["reports"][0].pop("expected_delivered_text")
    summary_path.write_text(json.dumps(summary), encoding="utf-8")

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert (
        "error=backend_summary missing expected_delivered_text for claude_code:send_reply"
    ) in result.stdout


def test_admin_target_evidence_check_rejects_backend_summary_capability_mismatch(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    _write_complete_target_evidence_bundle(evidence_dir)
    summary_path = evidence_dir / "backend-summary.json"
    summary = json.loads(summary_path.read_text("utf-8"))
    summary["reports"][0].pop("capability")
    summary["reports"][1]["capability"]["action"] = "reject"
    summary["reports"][2]["capability"]["transport"] = "process_stdin"
    summary["reports"][3]["capability"]["requires_text"] = False
    summary["reports"][4]["capability"]["semantics"] = "agent_reply"
    summary_path.write_text(json.dumps(summary), encoding="utf-8")

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert "error=backend_summary missing capability for claude_code:send_reply" in result.stdout
    assert (
        "error=backend_summary capability action for claude_code:approve must be approve"
        in result.stdout
    )
    assert (
        "error=backend_summary capability transport for claude_code:reject must be tmux_buffer"
    ) in result.stdout
    assert (
        "error=backend_summary capability requires_text for opencode:send_reply must be true"
    ) in result.stdout
    assert (
        "error=backend_summary capability semantics for opencode:approve must be agent_control"
    ) in result.stdout


def test_admin_target_evidence_check_rejects_backend_report_capability_mismatch(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    _write_complete_target_evidence_bundle(evidence_dir)
    report_path = evidence_dir / "backend-opencode-send_reply.json"
    report = json.loads(report_path.read_text("utf-8"))
    report["capability"]["transport"] = "process_stdin"
    report_path.write_text(json.dumps(report), encoding="utf-8")

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert (
        "error=backend-opencode-send_reply.json: capability transport must be tmux_buffer"
        in result.stdout
    )


def test_admin_target_evidence_check_rejects_backend_summary_regex_mismatch(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    _write_complete_target_evidence_bundle(evidence_dir)
    report_path = evidence_dir / "backend-opencode-send_reply.json"
    report = json.loads(report_path.read_text("utf-8"))
    report["expected_regex"] = "opencode send_reply accepted"
    report_path.write_text(json.dumps(report), encoding="utf-8")

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert (
        "error=backend-opencode-send_reply.json: expected_regex must match "
        "backend_summary expected_regex"
    ) in result.stdout


def test_admin_target_evidence_check_rejects_backend_summary_outcome_mismatch(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    _write_complete_target_evidence_bundle(evidence_dir)
    summary_path = evidence_dir / "backend-summary.json"
    summary = json.loads(summary_path.read_text("utf-8"))
    summary["reports"][0]["expected_outcome"] = "timed_out"
    summary_path.write_text(json.dumps(summary), encoding="utf-8")

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert (
        "error=backend_summary expected_outcome for claude_code:send_reply must be accepted"
    ) in result.stdout
    assert (
        "error=backend-claude_code-send_reply.json: action_result.outcome must match "
        "backend_summary expected_outcome"
    ) in result.stdout


def test_admin_target_evidence_check_rejects_backend_action_result_metadata_mismatch(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    _write_complete_target_evidence_bundle(evidence_dir)
    report_path = evidence_dir / "backend-claude_code-approve.json"
    report = json.loads(report_path.read_text("utf-8"))
    report["action_result"]["action"] = "reject"
    report["action_result"].pop("session_id")
    report_path.write_text(json.dumps(report), encoding="utf-8")

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert (
        "error=backend-claude_code-approve.json: action_result.action must be approve"
        in result.stdout
    )
    assert (
        "error=backend-claude_code-approve.json: action_result.session_id is required"
        in result.stdout
    )


def test_admin_target_evidence_check_rejects_backend_action_session_pane_mismatch(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    _write_complete_target_evidence_bundle(evidence_dir)
    report_path = evidence_dir / "backend-opencode-approve.json"
    report = json.loads(report_path.read_text("utf-8"))
    report["action_result"]["session_id"] = "tmux-%different-pane"
    report_path.write_text(json.dumps(report), encoding="utf-8")

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert (
        "error=backend-opencode-approve.json: action_result.session_id "
        "must match tmux pane session id"
    ) in result.stdout


def test_admin_target_evidence_check_rejects_duplicate_backend_evidence_hash_pair(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    _write_complete_target_evidence_bundle(evidence_dir)
    source_report = json.loads(
        (evidence_dir / "backend-claude_code-approve.json").read_text("utf-8")
    )
    target_path = evidence_dir / "backend-opencode-approve.json"
    target_report = json.loads(target_path.read_text("utf-8"))
    target_report["before_hash"] = source_report["before_hash"]
    target_report["after_hash"] = source_report["after_hash"]
    target_path.write_text(json.dumps(target_report), encoding="utf-8")

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert (
        "error=backend-opencode-approve.json: backend evidence hash pair must be "
        "unique across target bundle"
    ) in result.stdout


def test_admin_target_evidence_check_rejects_backend_action_result_outcome_mismatch(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    _write_complete_target_evidence_bundle(evidence_dir)
    report_path = evidence_dir / "backend-claude_code-approve.json"
    report = json.loads(report_path.read_text("utf-8"))
    report["action_result"]["outcome"] = "timed_out"
    report_path.write_text(json.dumps(report), encoding="utf-8")

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert (
        "error=backend-claude_code-approve.json: action_result.outcome must be accepted"
        in result.stdout
    )


def test_admin_target_evidence_check_rejects_backend_report_pane_mismatch(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    _write_complete_target_evidence_bundle(evidence_dir)
    report_path = evidence_dir / "backend-claude_code-approve.json"
    report = json.loads(report_path.read_text("utf-8"))
    report["pane"] = "%different-pane"
    report_path.write_text(json.dumps(report), encoding="utf-8")

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert (
        "error=backend-claude_code-approve.json: pane must match backend_summary pane"
    ) in result.stdout


def test_admin_target_evidence_check_rejects_weak_backend_summary_manifest(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    _write_complete_target_evidence_bundle(evidence_dir)
    summary_path = evidence_dir / "backend-summary.json"
    summary = json.loads(summary_path.read_text("utf-8"))
    summary.pop("schema_version")
    summary["profile"] = "current"
    summary["reports"][0]["report"] = str(evidence_dir / "wrong-report.json")
    summary["reports"][1].pop("pane")
    summary["reports"][2].pop("expected_regex")
    summary["reports"][3].pop("expected_outcome")
    summary["reports"].append(
        {
            "ok": True,
            "agent": "codex",
            "action": "approve",
            "pane": "%codex",
            "report": str(evidence_dir / "backend-codex-approve.json"),
            "expected_regex": "accepted",
            "expected_delivered_text": "y",
        }
    )
    summary_path.write_text(json.dumps(summary), encoding="utf-8")

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert "error=backend_summary schema_version must be 1" in result.stdout
    assert "error=backend_summary profile must be target, got 'current'" in result.stdout
    assert "error=backend_summary reports must contain exactly 6 entries" in result.stdout
    assert "error=backend_summary unexpected report for codex:approve" in result.stdout
    assert (
        "error=backend_summary report claude_code:send_reply must point to "
        "backend-claude_code-send_reply.json"
    ) in result.stdout
    assert "error=backend_summary report claude_code:approve pane is required" in result.stdout
    assert "error=backend_summary missing expected_regex for claude_code:reject" in result.stdout
    assert (
        "error=backend_summary expected_outcome for opencode:send_reply must be accepted"
    ) in result.stdout


def test_admin_target_evidence_check_rejects_weak_backend_summary_report_identity(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    _write_complete_target_evidence_bundle(evidence_dir)
    summary_path = evidence_dir / "backend-summary.json"
    summary = json.loads(summary_path.read_text("utf-8"))
    summary["reports"][0]["schema_version"] = 0
    summary["reports"][0]["profile"] = "current"
    summary["reports"][0]["ok"] = False
    summary_path.write_text(json.dumps(summary), encoding="utf-8")

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert (
        "error=backend_summary report claude_code:send_reply schema_version must be 1"
        in result.stdout
    )
    assert (
        "error=backend_summary report claude_code:send_reply profile must be target"
        in result.stdout
    )
    assert "error=backend_summary report claude_code:send_reply ok must be true" in result.stdout


def test_admin_target_evidence_check_rejects_external_backend_summary_report_paths(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    _write_complete_target_evidence_bundle(evidence_dir)
    summary_path = evidence_dir / "backend-summary.json"
    summary = json.loads(summary_path.read_text("utf-8"))
    summary["output_dir"] = str(tmp_path / "other-evidence")
    summary["reports"][0]["report"] = str(
        tmp_path / "other" / "backend-claude_code-send_reply.json"
    )
    summary_path.write_text(json.dumps(summary), encoding="utf-8")

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert "error=backend_summary output_dir must match evidence directory" in result.stdout
    assert (
        "error=backend_summary report claude_code:send_reply must stay inside evidence directory"
    ) in result.stdout


def test_admin_target_evidence_check_rejects_shifted_backend_summary_report_paths(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    _write_complete_target_evidence_bundle(evidence_dir)
    summary_path = evidence_dir / "backend-summary.json"
    summary = json.loads(summary_path.read_text("utf-8"))
    summary["reports"][0]["report"] = str(
        evidence_dir / "nested" / "backend-claude_code-send_reply.json"
    )
    summary_path.write_text(json.dumps(summary), encoding="utf-8")

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert (
        "error=backend_summary report claude_code:send_reply must match evidence file "
        "backend-claude_code-send_reply.json"
    ) in result.stdout


def test_admin_target_evidence_check_rejects_required_agent_hook_failure(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    evidence_dir.mkdir()
    (evidence_dir / "summary.json").write_text(
        json.dumps({"ok": True, "profile": "target", "failed_required": []}),
        encoding="utf-8",
    )
    (evidence_dir / "acceptance-target.json").write_text(
        json.dumps({"ok": True, "profile": "target", "failed_required": []}),
        encoding="utf-8",
    )
    (evidence_dir / "environment.json").write_text(
        json.dumps({"profile": "target"}),
        encoding="utf-8",
    )
    (evidence_dir / "tmux-control.json").write_text(
        json.dumps({"ok": True, "required": True, "skipped": False}),
        encoding="utf-8",
    )
    (evidence_dir / "systemd-units.json").write_text(
        json.dumps({"ok": True, "required": True, "skipped": False}),
        encoding="utf-8",
    )
    (evidence_dir / "agent-hooks.json").write_text(
        json.dumps({"ok": False, "required": True, "checks": []}),
        encoding="utf-8",
    )
    for agent in ("claude_code", "opencode"):
        for action in ("send_reply", "approve", "reject"):
            (evidence_dir / f"backend-{agent}-{action}.json").write_text(
                json.dumps(
                    {
                        "ok": True,
                        "agent": agent,
                        "action": action,
                        "expected_regex": "accepted",
                        "matched_expected": True,
                        "output_changed": True,
                        "before_hash": f"{agent}-{action}-before",
                        "after_hash": f"{agent}-{action}-after",
                        "action_result": {"ok": True},
                    }
                ),
                encoding="utf-8",
            )

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert "error=agent_hooks ok must be true" in result.stdout


def test_admin_target_evidence_check_rejects_required_agent_hooks_missing_checks(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    _write_complete_target_evidence_bundle(evidence_dir)
    agent_hooks_path = evidence_dir / "agent-hooks.json"
    agent_hooks = json.loads(agent_hooks_path.read_text("utf-8"))
    agent_hooks["checks"] = [
        {
            "name": "hook_script",
            "ok": True,
            "required": True,
            "detail": "/home/test/.local/share/coding-pet/hooks/coding-pet-hook",
        }
    ]
    agent_hooks_path.write_text(json.dumps(agent_hooks), encoding="utf-8")

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert "error=agent_hooks missing ok check hook_script_smoke" in result.stdout
    assert "error=agent_hooks missing ok check claude_settings" in result.stdout
    assert "error=agent_hooks missing ok check opencode_plugin" in result.stdout


def test_admin_target_evidence_check_rejects_required_agent_hooks_failed_check(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    _write_complete_target_evidence_bundle(evidence_dir)
    agent_hooks_path = evidence_dir / "agent-hooks.json"
    agent_hooks = json.loads(agent_hooks_path.read_text("utf-8"))
    for check in agent_hooks["checks"]:
        if check["name"] == "opencode_plugin":
            check["ok"] = False
            break
    agent_hooks_path.write_text(json.dumps(agent_hooks), encoding="utf-8")

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert "error=agent_hooks check opencode_plugin ok must be true" in result.stdout


def test_admin_target_evidence_check_rejects_agent_hook_path_mismatch(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    _write_complete_target_evidence_bundle(evidence_dir)
    agent_hooks_path = evidence_dir / "agent-hooks.json"
    agent_hooks = json.loads(agent_hooks_path.read_text("utf-8"))
    for check in agent_hooks["checks"]:
        if check["name"] == "hook_script":
            check["detail"] = "/tmp/coding-pet-hook.sh"
        elif check["name"] == "hook_script_smoke":
            check["detail"] = "/home/test/.config/coding-pet/hooks/coding-pet-hook.sh:returncode=1"
        elif check["name"] == "claude_settings":
            check["detail"] = "/tmp/claude-settings.json"
        elif check["name"] == "opencode_plugin":
            check["detail"] = "/tmp/coding-pet-opencode-plugin.js"
    agent_hooks_path.write_text(json.dumps(agent_hooks), encoding="utf-8")

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert (
        "error=agent_hooks check hook_script detail must point to hook script under hooks_dir"
    ) in result.stdout
    assert (
        "error=agent_hooks check hook_script_smoke detail must end with :returncode=0"
        in result.stdout
    )
    assert (
        "error=agent_hooks check claude_settings detail must match claude_settings" in result.stdout
    )
    assert (
        "error=agent_hooks check opencode_plugin detail must match opencode_plugin" in result.stdout
    )


def test_admin_target_evidence_check_rejects_required_wheelhouse_failure(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    evidence_dir.mkdir()
    (evidence_dir / "summary.json").write_text(
        json.dumps({"ok": True, "profile": "target", "failed_required": []}),
        encoding="utf-8",
    )
    (evidence_dir / "acceptance-target.json").write_text(
        json.dumps({"ok": True, "profile": "target", "failed_required": []}),
        encoding="utf-8",
    )
    (evidence_dir / "environment.json").write_text(
        json.dumps({"profile": "target"}),
        encoding="utf-8",
    )
    (evidence_dir / "tmux-control.json").write_text(
        json.dumps({"ok": True, "required": True, "skipped": False}),
        encoding="utf-8",
    )
    (evidence_dir / "systemd-units.json").write_text(
        json.dumps({"ok": True, "required": True, "skipped": False}),
        encoding="utf-8",
    )
    (evidence_dir / "wheelhouse.json").write_text(
        json.dumps({"ok": False, "required": True, "skipped": False}),
        encoding="utf-8",
    )
    for agent in ("claude_code", "opencode"):
        for action in ("send_reply", "approve", "reject"):
            (evidence_dir / f"backend-{agent}-{action}.json").write_text(
                json.dumps(
                    {
                        "ok": True,
                        "agent": agent,
                        "action": action,
                        "expected_regex": "accepted",
                        "matched_expected": True,
                        "output_changed": True,
                        "before_hash": f"{agent}-{action}-before",
                        "after_hash": f"{agent}-{action}-after",
                        "action_result": {"ok": True},
                    }
                ),
                encoding="utf-8",
            )

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert "error=wheelhouse ok must be true" in result.stdout


def test_admin_target_evidence_check_rejects_weak_wheelhouse_manifest(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    _write_complete_target_evidence_bundle(evidence_dir)
    wheelhouse_path = evidence_dir / "wheelhouse.json"
    wheelhouse = json.loads(wheelhouse_path.read_text("utf-8"))
    wheelhouse["present_distributions"] = ["coding-pet"]
    wheelhouse["wheels"] = [
        {
            "filename": "coding_pet-0.1.0-py3-none-any.whl",
            "distribution": "coding-pet",
            "sha256": "not-a-sha",
            "size_bytes": 0,
        }
    ]
    wheelhouse_path.write_text(json.dumps(wheelhouse), encoding="utf-8")

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert "error=wheelhouse missing required distribution pydantic" in result.stdout
    assert (
        "error=wheelhouse wheel coding_pet-0.1.0-py3-none-any.whl sha256 is required"
        in result.stdout
    )
    assert (
        "error=wheelhouse wheel coding_pet-0.1.0-py3-none-any.whl size_bytes must be positive"
    ) in result.stdout


def test_admin_target_evidence_check_rejects_python_incompatible_wheel_record(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    _write_complete_target_evidence_bundle(evidence_dir)
    wheelhouse_path = evidence_dir / "wheelhouse.json"
    wheelhouse = json.loads(wheelhouse_path.read_text("utf-8"))
    for wheel in wheelhouse["wheels"]:
        if wheel["distribution"] == "pillow":
            wheel["filename"] = "Pillow-11.3.0-cp313-cp313-manylinux_2_28_x86_64.whl"
            break
    wheelhouse_path.write_text(json.dumps(wheelhouse), encoding="utf-8")

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert (
        "error=wheelhouse wheel "
        "Pillow-11.3.0-cp313-cp313-manylinux_2_28_x86_64.whl "
        "python tag is incompatible with Python 3.12 target"
    ) in result.stdout


def test_admin_target_evidence_check_rejects_platform_incompatible_wheel_record(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    _write_complete_target_evidence_bundle(evidence_dir)
    wheelhouse_path = evidence_dir / "wheelhouse.json"
    wheelhouse = json.loads(wheelhouse_path.read_text("utf-8"))
    for wheel in wheelhouse["wheels"]:
        if wheel["distribution"] == "pillow":
            wheel["filename"] = "Pillow-11.3.0-cp312-cp312-manylinux_2_28_aarch64.whl"
            break
    wheelhouse_path.write_text(json.dumps(wheelhouse), encoding="utf-8")

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert (
        "error=wheelhouse wheel "
        "Pillow-11.3.0-cp312-cp312-manylinux_2_28_aarch64.whl "
        "platform tag is incompatible with RHEL 8.10 x86_64 target"
    ) in result.stdout


def test_admin_target_evidence_check_rejects_missing_required_wheel_records(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    _write_complete_target_evidence_bundle(evidence_dir)
    wheelhouse_path = evidence_dir / "wheelhouse.json"
    wheelhouse = json.loads(wheelhouse_path.read_text("utf-8"))
    wheelhouse["wheels"] = [
        wheel
        for wheel in wheelhouse["wheels"]
        if wheel["distribution"] not in {"pydantic", "pyside6-essentials"}
    ]
    wheelhouse_path.write_text(json.dumps(wheelhouse), encoding="utf-8")

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert "error=wheelhouse missing wheel record for distribution pydantic" in result.stdout
    assert (
        "error=wheelhouse missing wheel record for distribution pyside6-essentials" in result.stdout
    )


def test_admin_target_evidence_check_rejects_duplicate_wheelhouse_records(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    _write_complete_target_evidence_bundle(evidence_dir)
    wheelhouse_path = evidence_dir / "wheelhouse.json"
    wheelhouse = json.loads(wheelhouse_path.read_text("utf-8"))
    duplicate_wheel = dict(wheelhouse["wheels"][0])
    wheelhouse["wheels"].append(duplicate_wheel)
    wheelhouse_path.write_text(json.dumps(wheelhouse), encoding="utf-8")

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert "error=wheelhouse duplicate wheel distribution coding-pet" in result.stdout
    assert (
        "error=wheelhouse duplicate wheel filename coding_pet-0.1.0-py3-none-any.whl"
        in result.stdout
    )
    assert "error=wheelhouse duplicate wheel sha256" in result.stdout


def test_admin_target_evidence_check_rejects_required_wheelhouse_static_only_smoke(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    _write_complete_target_evidence_bundle(evidence_dir)
    wheelhouse_path = evidence_dir / "wheelhouse.json"
    wheelhouse = json.loads(wheelhouse_path.read_text("utf-8"))
    wheelhouse["install_smoke"] = {
        "ok": True,
        "skipped": True,
        "detail": "install smoke skipped",
    }
    wheelhouse_path.write_text(json.dumps(wheelhouse), encoding="utf-8")

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert "error=wheelhouse install_smoke must not be skipped" in result.stdout


def test_admin_target_evidence_check_rejects_required_wheelhouse_failed_install_smoke(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    _write_complete_target_evidence_bundle(evidence_dir)
    wheelhouse_path = evidence_dir / "wheelhouse.json"
    wheelhouse = json.loads(wheelhouse_path.read_text("utf-8"))
    wheelhouse["install_smoke"] = {
        "ok": False,
        "skipped": False,
        "stage": "install",
        "detail": "offline wheelhouse install failed",
    }
    wheelhouse_path.write_text(json.dumps(wheelhouse), encoding="utf-8")

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert "error=wheelhouse install_smoke.ok must be true" in result.stdout


def test_admin_target_evidence_check_rejects_required_pet_package_failure(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    evidence_dir.mkdir()
    (evidence_dir / "summary.json").write_text(
        json.dumps({"ok": True, "profile": "target", "failed_required": []}),
        encoding="utf-8",
    )
    (evidence_dir / "acceptance-target.json").write_text(
        json.dumps({"ok": True, "profile": "target", "failed_required": []}),
        encoding="utf-8",
    )
    (evidence_dir / "environment.json").write_text(
        json.dumps({"profile": "target"}),
        encoding="utf-8",
    )
    (evidence_dir / "tmux-control.json").write_text(
        json.dumps({"ok": True, "required": True, "skipped": False}),
        encoding="utf-8",
    )
    (evidence_dir / "systemd-units.json").write_text(
        json.dumps({"ok": True, "required": True, "skipped": False}),
        encoding="utf-8",
    )
    (evidence_dir / "pet-packages.json").write_text(
        json.dumps({"ok": False, "required": True, "skipped": False, "failed": 1}),
        encoding="utf-8",
    )
    for agent in ("claude_code", "opencode"):
        for action in ("send_reply", "approve", "reject"):
            (evidence_dir / f"backend-{agent}-{action}.json").write_text(
                json.dumps(
                    {
                        "ok": True,
                        "agent": agent,
                        "action": action,
                        "expected_regex": "accepted",
                        "matched_expected": True,
                        "output_changed": True,
                        "before_hash": f"{agent}-{action}-before",
                        "after_hash": f"{agent}-{action}-after",
                        "action_result": {"ok": True},
                    }
                ),
                encoding="utf-8",
            )

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert "error=pet_packages ok must be true" in result.stdout


def test_admin_target_evidence_check_rejects_weak_pet_package_manifest(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    _write_complete_target_evidence_bundle(evidence_dir)
    pet_packages_path = evidence_dir / "pet-packages.json"
    pet_packages = json.loads(pet_packages_path.read_text("utf-8"))
    pet_packages["total"] = 0
    pet_packages["failed"] = 1
    pet_packages["pets"] = [
        {
            "ok": True,
            "source_package": "/tmp/downloaded-pets/boba.zip",
            "transfer": {
                "kind": "file",
                "sha256": "bad",
                "size_bytes": 0,
            },
        }
    ]
    pet_packages_path.write_text(json.dumps(pet_packages), encoding="utf-8")

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert "error=pet_packages total must be positive" in result.stdout
    assert "error=pet_packages failed must be 0" in result.stdout
    assert "error=pet_packages pet theme_id is required" in result.stdout
    assert "error=pet_packages pet transfer.sha256 is required" in result.stdout
    assert "error=pet_packages pet transfer.size_bytes must be positive" in result.stdout


def test_admin_target_evidence_check_rejects_pet_package_missing_validation_surface(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    _write_complete_target_evidence_bundle(evidence_dir)
    pet_packages_path = evidence_dir / "pet-packages.json"
    pet_packages = json.loads(pet_packages_path.read_text("utf-8"))
    pet = pet_packages["pets"][0]
    pet["theme_format"] = "coding_pet"
    pet.pop("spritesheet")
    pet["atlas_size"] = {"width": 1, "height": 1872}
    pet["mood_rows"] = {"idle": 0}
    pet["frame_counts_by_row"] = {"0": 0}
    pet["atlas_cells"] = {
        "ok": False,
        "errors": ["waiting row 6 column 0 is empty"],
        "warnings": [],
    }
    pet_packages_path.write_text(json.dumps(pet_packages), encoding="utf-8")

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert "error=pet_packages pet theme_format must be codex_pet" in result.stdout
    assert "error=pet_packages pet spritesheet is required" in result.stdout
    assert "error=pet_packages pet atlas_size must match grid and frame size" in result.stdout
    assert "error=pet_packages pet mood_rows missing alert" in result.stdout
    assert "error=pet_packages pet frame_counts_by_row 0 must be positive" in result.stdout
    assert "error=pet_packages pet atlas_cells.ok must be true" in result.stdout
    assert "error=pet_packages pet atlas_cells.errors must be empty" in result.stdout


def test_admin_target_evidence_check_rejects_pet_package_count_mismatch(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    _write_complete_target_evidence_bundle(evidence_dir)
    pet_packages_path = evidence_dir / "pet-packages.json"
    pet_packages = json.loads(pet_packages_path.read_text("utf-8"))
    pet_packages["total"] = 2
    pet_packages["passed"] = 0
    pet_packages_path.write_text(json.dumps(pet_packages), encoding="utf-8")

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert "error=pet_packages total must match pets count" in result.stdout
    assert "error=pet_packages passed plus failed must equal total" in result.stdout
    assert "error=pet_packages passed must equal total when failed is 0" in result.stdout


def test_admin_target_evidence_check_rejects_duplicate_pet_package_records(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    _write_complete_target_evidence_bundle(evidence_dir)
    pet_packages_path = evidence_dir / "pet-packages.json"
    pet_packages = json.loads(pet_packages_path.read_text("utf-8"))
    duplicate_pet = dict(pet_packages["pets"][0])
    duplicate_pet["manifest"] = "/tmp/downloaded-pets/boba-copy/pet.json"
    pet_packages["pets"].append(duplicate_pet)
    pet_packages["total"] = 2
    pet_packages["passed"] = 2
    pet_packages_path.write_text(json.dumps(pet_packages), encoding="utf-8")

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert "error=pet_packages duplicate theme_id boba" in result.stdout
    assert (
        "error=pet_packages duplicate source_package /tmp/downloaded-pets/boba.zip" in result.stdout
    )
    assert "error=pet_packages duplicate transfer.sha256" in result.stdout


def test_admin_target_evidence_check_rejects_boolean_pet_package_counts(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    _write_complete_target_evidence_bundle(evidence_dir)
    pet_packages_path = evidence_dir / "pet-packages.json"
    pet_packages = json.loads(pet_packages_path.read_text("utf-8"))
    pet_packages["total"] = True
    pet_packages["passed"] = False
    pet_packages["failed"] = False
    pet_packages_path.write_text(json.dumps(pet_packages), encoding="utf-8")

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert "error=pet_packages total must be positive" in result.stdout
    assert "error=pet_packages passed must be a non-negative integer" in result.stdout
    assert "error=pet_packages failed must be 0" in result.stdout


def test_admin_target_evidence_check_rejects_weak_petdex_sidecar_metadata(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    _write_complete_target_evidence_bundle(evidence_dir)
    pet_packages_path = evidence_dir / "pet-packages.json"
    pet_packages = json.loads(pet_packages_path.read_text("utf-8"))
    pet_packages["pets"][0]["petdex_metadata"] = {
        "path": "/tmp/downloaded-pets/boba.petdex.json",
        "sha256": "bad",
        "size_bytes": 0,
        "schema_version": 1,
        "source": "petdex",
        "slug": "boba",
        "zip_url": "https://example.invalid/boba.zip",
        "archive_sha256": "0" * 64,
        "archive_size_bytes": 1,
    }
    pet_packages_path.write_text(json.dumps(pet_packages), encoding="utf-8")

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert "error=pet_packages pet petdex_metadata.sha256 is required" in result.stdout
    assert "error=pet_packages pet petdex_metadata.size_bytes must be positive" in result.stdout
    assert (
        "error=pet_packages pet petdex_metadata archive_sha256 must match transfer.sha256"
        in result.stdout
    )


def test_admin_target_evidence_check_rejects_backend_summary_failure(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "target-evidence"
    evidence_dir.mkdir()
    (evidence_dir / "summary.json").write_text(
        json.dumps({"ok": True, "profile": "target", "failed_required": []}),
        encoding="utf-8",
    )
    (evidence_dir / "acceptance-target.json").write_text(
        json.dumps({"ok": True, "profile": "target", "failed_required": []}),
        encoding="utf-8",
    )
    (evidence_dir / "environment.json").write_text(
        json.dumps({"profile": "target"}),
        encoding="utf-8",
    )
    (evidence_dir / "tmux-control.json").write_text(
        json.dumps({"ok": True, "required": True, "skipped": False}),
        encoding="utf-8",
    )
    (evidence_dir / "systemd-units.json").write_text(
        json.dumps({"ok": True, "required": True, "skipped": False}),
        encoding="utf-8",
    )
    (evidence_dir / "backend-summary.json").write_text(
        json.dumps(
            {
                "ok": False,
                "reports": [
                    {"ok": True, "agent": "claude_code", "action": "send_reply"},
                ],
            }
        ),
        encoding="utf-8",
    )
    for agent in ("claude_code", "opencode"):
        for action in ("send_reply", "approve", "reject"):
            (evidence_dir / f"backend-{agent}-{action}.json").write_text(
                json.dumps(
                    {
                        "ok": True,
                        "agent": agent,
                        "action": action,
                        "expected_regex": "accepted",
                        "matched_expected": True,
                        "output_changed": True,
                        "before_hash": f"{agent}-{action}-before",
                        "after_hash": f"{agent}-{action}-after",
                        "action_result": {"ok": True},
                    }
                ),
                encoding="utf-8",
            )

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert "error=backend_summary ok must be true" in result.stdout
    assert "error=backend_summary missing ok report for claude_code:approve" in result.stdout


def test_admin_target_evidence_check_rejects_incomplete_target_bundle(tmp_path: Path) -> None:
    evidence_dir = tmp_path / "target-evidence"
    evidence_dir.mkdir()
    (evidence_dir / "summary.json").write_text(
        json.dumps({"ok": True, "profile": "current", "failed_required": []}),
        encoding="utf-8",
    )
    (evidence_dir / "acceptance-target.json").write_text(
        json.dumps(
            {
                "ok": False,
                "profile": "target",
                "failed_required": ["gui_runtime"],
            }
        ),
        encoding="utf-8",
    )
    (evidence_dir / "environment.json").write_text(
        json.dumps({"profile": "target"}),
        encoding="utf-8",
    )
    (evidence_dir / "tmux-control.json").write_text(
        json.dumps({"ok": False, "required": True, "skipped": True}),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["admin", "target-evidence-check", str(evidence_dir)])

    assert result.exit_code != 0
    assert "target_evidence=failed" in result.stdout
    assert "error=summary profile must be target" in result.stdout
    assert "error=acceptance ok must be true" in result.stdout
    assert "error=tmux_control ok must be true" in result.stdout
    assert "error=systemd-units.json could not be read" in result.stdout
    assert "error=missing backend evidence: backend-claude_code-send_reply.json" in result.stdout


def test_admin_collect_target_backend_evidence_writes_six_reports(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from coding_pet.tmux.client import TmuxCommandResult
    from coding_pet.tmux.models import TmuxPaneInfo

    monkeypatch.setenv("HOME", str(tmp_path))
    loaded_texts: list[str] = []

    class FakeTmuxClient:
        def __init__(self) -> None:
            self.loaded_text = ""
            self.delivered = False

        def list_panes(self) -> list[TmuxPaneInfo]:
            return [
                TmuxPaneInfo("%claude", "claude-safe", "0.0", "claude", "/tmp/claude", None),
                TmuxPaneInfo(
                    "%opencode",
                    "opencode-safe",
                    "0.0",
                    "opencode",
                    "/tmp/opencode",
                    None,
                ),
            ]

        def capture_pane(self, pane_id: str, *, lines: int) -> str:
            assert lines == 200
            if self.delivered:
                return f"collected target evidence for {pane_id}: {self.loaded_text}"
            return f"waiting for target evidence on {pane_id}"

        def run(self, argv: list[str]) -> TmuxCommandResult:
            if argv[0] == "load-buffer":
                self.loaded_text = Path(argv[-1]).read_text(encoding="utf-8")
                loaded_texts.append(self.loaded_text)
            if argv[0] == "send-keys" and argv[-1] == "Enter":
                self.delivered = True
            return TmuxCommandResult()

    monkeypatch.setattr("coding_pet.cli.TmuxClient", FakeTmuxClient)
    output_dir = tmp_path / "target-evidence"

    result = runner.invoke(
        app,
        [
            "admin",
            "collect-target-backend-evidence",
            "--output-dir",
            str(output_dir),
            "--claude-pane",
            "%claude",
            "--opencode-pane",
            "%opencode",
            "--reply-text",
            "계속 진행",
            "--reply-expect-regex",
            "collected target evidence",
            "--approve-expect-regex",
            "collected target evidence",
            "--reject-expect-regex",
            "collected target evidence",
        ],
    )
    summary = json.loads((output_dir / "backend-summary.json").read_text("utf-8"))

    assert result.exit_code == 0
    assert "backend_evidence_collection=ok" in result.stdout
    assert summary["schema_version"] == 1
    assert summary["profile"] == "target"
    assert summary["ok"] is True
    assert len(summary["reports"]) == 6
    capabilities = {
        (report["agent"], report["action"]): report["capability"] for report in summary["reports"]
    }
    expected_delivered_texts = {
        (report["agent"], report["action"]): report["expected_delivered_text"]
        for report in summary["reports"]
    }
    expected_outcomes = {
        (report["agent"], report["action"]): report["expected_outcome"]
        for report in summary["reports"]
    }
    assert expected_delivered_texts == {
        ("claude_code", "send_reply"): "계속 진행",
        ("claude_code", "approve"): "approve",
        ("claude_code", "reject"): "reject",
        ("opencode", "send_reply"): "계속 진행",
        ("opencode", "approve"): "approve",
        ("opencode", "reject"): "reject",
    }
    assert expected_outcomes == {
        ("claude_code", "send_reply"): "accepted",
        ("claude_code", "approve"): "accepted",
        ("claude_code", "reject"): "accepted",
        ("opencode", "send_reply"): "accepted",
        ("opencode", "approve"): "accepted",
        ("opencode", "reject"): "accepted",
    }
    assert capabilities[("claude_code", "send_reply")] == {
        "action": "send_reply",
        "transport": "tmux_buffer",
        "requires_text": True,
        "press_enter_default": True,
        "semantics": "agent_reply",
    }
    assert capabilities[("opencode", "approve")] == {
        "action": "approve",
        "transport": "tmux_buffer",
        "requires_text": False,
        "press_enter_default": True,
        "semantics": "agent_control",
    }
    assert loaded_texts == [
        "계속 진행",
        "approve",
        "reject",
        "계속 진행",
        "approve",
        "reject",
    ]
    for agent in ("claude_code", "opencode"):
        for action in ("send_reply", "approve", "reject"):
            report = json.loads((output_dir / f"backend-{agent}-{action}.json").read_text("utf-8"))
            assert report["ok"] is True
            assert report["matched_expected"] is True


def test_admin_collect_target_backend_evidence_updates_existing_summary_manifest(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from coding_pet.tmux.client import TmuxCommandResult
    from coding_pet.tmux.models import TmuxPaneInfo

    monkeypatch.setenv("HOME", str(tmp_path))

    class FakeTmuxClient:
        def __init__(self) -> None:
            self.loaded_text = ""
            self.delivered = False

        def list_panes(self) -> list[TmuxPaneInfo]:
            return [
                TmuxPaneInfo("%claude", "claude-safe", "0.0", "claude", "/tmp/claude", None),
                TmuxPaneInfo(
                    "%opencode",
                    "opencode-safe",
                    "0.0",
                    "opencode",
                    "/tmp/opencode",
                    None,
                ),
            ]

        def capture_pane(self, pane_id: str, *, lines: int) -> str:
            assert lines == 200
            if self.delivered:
                return f"collected target evidence for {pane_id}: {self.loaded_text}"
            return f"waiting for target evidence on {pane_id}"

        def run(self, argv: list[str]) -> TmuxCommandResult:
            if argv[0] == "load-buffer":
                self.loaded_text = Path(argv[-1]).read_text(encoding="utf-8")
            if argv[0] == "send-keys" and argv[-1] == "Enter":
                self.delivered = True
            return TmuxCommandResult()

    monkeypatch.setattr("coding_pet.cli.TmuxClient", FakeTmuxClient)
    output_dir = tmp_path / "target-evidence"
    output_dir.mkdir()
    (output_dir / "summary.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "ok": True,
                "profile": "target",
                "output_dir": str(output_dir),
                "generated_at": datetime.now(UTC).isoformat(),
                "failed_required": [],
                "artifacts": {
                    "environment": str(output_dir / "environment.json"),
                },
            }
        ),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "admin",
            "collect-target-backend-evidence",
            "--output-dir",
            str(output_dir),
            "--claude-pane",
            "%claude",
            "--opencode-pane",
            "%opencode",
            "--reply-expect-regex",
            "collected target evidence",
            "--approve-expect-regex",
            "collected target evidence",
            "--reject-expect-regex",
            "collected target evidence",
        ],
    )
    summary = json.loads((output_dir / "summary.json").read_text("utf-8"))

    assert result.exit_code == 0
    assert summary["artifacts"]["backend_summary"] == str(output_dir / "backend-summary.json")
    assert summary["artifacts"]["backend_claude_code_approve"] == str(
        output_dir / "backend-claude_code-approve.json"
    )
    assert summary["artifacts"]["backend_opencode_reject"] == str(
        output_dir / "backend-opencode-reject.json"
    )
    assert summary["ok"] is True
    assert summary["failed_required"] == []


def test_admin_collect_target_backend_evidence_rejects_weak_reports(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from coding_pet.tmux.client import TmuxCommandResult
    from coding_pet.tmux.models import TmuxPaneInfo

    monkeypatch.setenv("HOME", str(tmp_path))

    class FakeTmuxClient:
        def list_panes(self) -> list[TmuxPaneInfo]:
            return [
                TmuxPaneInfo("%claude", "claude-safe", "0.0", "claude", "/tmp/claude", None),
                TmuxPaneInfo(
                    "%opencode",
                    "opencode-safe",
                    "0.0",
                    "opencode",
                    "/tmp/opencode",
                    None,
                ),
            ]

        def capture_pane(self, pane_id: str, *, lines: int) -> str:
            return f"still waiting on {pane_id}"

        def run(self, argv: list[str]) -> TmuxCommandResult:
            return TmuxCommandResult()

    monkeypatch.setattr("coding_pet.cli.TmuxClient", FakeTmuxClient)
    output_dir = tmp_path / "target-evidence"
    output_dir.mkdir()
    (output_dir / "summary.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "ok": True,
                "profile": "target",
                "output_dir": str(output_dir),
                "generated_at": datetime.now(UTC).isoformat(),
                "failed_required": [],
                "artifacts": {
                    "environment": str(output_dir / "environment.json"),
                },
            }
        ),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "admin",
            "collect-target-backend-evidence",
            "--output-dir",
            str(output_dir),
            "--claude-pane",
            "%claude",
            "--opencode-pane",
            "%opencode",
            "--reply-expect-regex",
            "collected target evidence",
            "--approve-expect-regex",
            "collected target evidence",
            "--reject-expect-regex",
            "collected target evidence",
            "--timeout-s",
            "0.1",
        ],
    )
    summary = json.loads((output_dir / "backend-summary.json").read_text("utf-8"))
    top_summary = json.loads((output_dir / "summary.json").read_text("utf-8"))

    assert result.exit_code != 0
    assert "backend_evidence_collection=failed" in result.stdout
    assert "error=backend-claude_code-send_reply.json: report ok must be true" in result.stdout
    assert summary["ok"] is False
    assert len(summary["reports"]) == 6
    assert top_summary["ok"] is False
    assert top_summary["failed_required"] == ["backend_evidence"]
    assert top_summary["artifacts"]["backend_summary"] == str(output_dir / "backend-summary.json")


def test_admin_collect_target_backend_evidence_exception_reports_have_identity(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))

    class FakeTmuxClient:
        def capture_pane(self, pane_id: str, *, lines: int) -> str:
            raise RuntimeError(f"cannot capture {pane_id}")

    monkeypatch.setattr("coding_pet.cli.TmuxClient", FakeTmuxClient)
    output_dir = tmp_path / "target-evidence"

    result = runner.invoke(
        app,
        [
            "admin",
            "collect-target-backend-evidence",
            "--output-dir",
            str(output_dir),
            "--claude-pane",
            "%claude",
            "--opencode-pane",
            "%opencode",
            "--reply-expect-regex",
            "collected target evidence",
            "--approve-expect-regex",
            "collected target evidence",
            "--reject-expect-regex",
            "collected target evidence",
        ],
    )
    report = json.loads((output_dir / "backend-claude_code-send_reply.json").read_text("utf-8"))

    assert result.exit_code != 0
    assert report["schema_version"] == 1
    assert report["profile"] == "target"
    assert report["ok"] is False
    assert report["pane"] == "%claude"
    assert report["agent"] == "claude_code"
    assert report["action"] == "send_reply"
    assert report["capability"] == {
        "action": "send_reply",
        "transport": "tmux_buffer",
        "requires_text": True,
        "press_enter_default": True,
        "semantics": "agent_reply",
    }
    assert report["expected_regex"] == "collected target evidence"
    assert report["action_result"]["outcome"] == "backend_failed"
    assert report["action_result"]["action"] == "send_reply"
    assert "cannot capture %claude" in report["error"]


def test_admin_write_agent_hooks_writes_offline_hook_files(tmp_path: Path) -> None:
    output_dir = tmp_path / "hooks"

    result = runner.invoke(
        app,
        [
            "admin",
            "write-agent-hooks",
            "--output-dir",
            str(output_dir),
        ],
    )
    script = output_dir / "coding-pet-hook.sh"
    claude = output_dir / "claude-settings-snippet.json"
    opencode = output_dir / "coding-pet-opencode-plugin.js"
    claude_payload = json.loads(claude.read_text("utf-8"))
    opencode_source = opencode.read_text("utf-8")

    assert result.exit_code == 0
    assert "hook_script=" in result.stdout
    assert script.exists()
    assert "daemon hook-event" in script.read_text("utf-8")
    assert 'if [ -z "${CODING_PET_BIN:-}" ]; then' in script.read_text("utf-8")
    assert claude_payload["hooks"]["PreToolUse"][0]["hooks"][0]["args"] == [
        "claude_code",
        "PreToolUse",
    ]
    assert str(script) in opencode_source
    assert "tool.execute.before" in opencode_source


def test_admin_install_agent_hooks_merges_settings_and_writes_plugin(
    tmp_path: Path,
) -> None:
    from coding_pet.hooks import CLAUDE_HOOK_EVENTS

    hooks_dir = tmp_path / "hooks"
    claude_settings = tmp_path / "claude" / "settings.json"
    opencode_plugin = tmp_path / "opencode" / "plugins" / "coding-pet.js"
    claude_settings.parent.mkdir(parents=True)
    claude_settings.write_text(
        json.dumps(
            {
                "theme": "dark",
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": "Bash",
                            "hooks": [{"type": "command", "command": "existing-hook"}],
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "admin",
            "install-agent-hooks",
            "--hooks-dir",
            str(hooks_dir),
            "--claude-settings",
            str(claude_settings),
            "--opencode-plugin",
            str(opencode_plugin),
        ],
    )
    second_result = runner.invoke(
        app,
        [
            "admin",
            "install-agent-hooks",
            "--hooks-dir",
            str(hooks_dir),
            "--claude-settings",
            str(claude_settings),
            "--opencode-plugin",
            str(opencode_plugin),
        ],
    )

    script = hooks_dir / "coding-pet-hook.sh"
    settings = json.loads(claude_settings.read_text("utf-8"))
    plugin_source = opencode_plugin.read_text("utf-8")

    assert result.exit_code == 0, result.stdout
    assert second_result.exit_code == 0, second_result.stdout
    assert "agent_hooks_install=ok" in result.stdout
    assert script.stat().st_mode & 0o111 != 0
    assert settings["theme"] == "dark"
    assert settings["hooks"]["PreToolUse"][0]["hooks"][0]["command"] == "existing-hook"
    for event in CLAUDE_HOOK_EVENTS:
        handlers = [
            handler
            for group in settings["hooks"][event]
            for handler in group.get("hooks", [])
            if handler.get("command") == str(script)
            and handler.get("args") == ["claude_code", event]
        ]
        assert len(handlers) == 1
    assert str(script) in plugin_source
    assert "tool.execute.before" in plugin_source
    assert "permission.asked" in plugin_source
    assert "session.error" in plugin_source


def test_admin_agent_hooks_doctor_reports_missing_and_installed_hooks(
    tmp_path: Path,
) -> None:
    hooks_dir = tmp_path / "hooks"
    claude_settings = tmp_path / "claude" / "settings.json"
    opencode_plugin = tmp_path / "opencode" / "plugins" / "coding-pet.js"
    installed_report_path = tmp_path / "agent-hooks.json"

    missing_result = runner.invoke(
        app,
        [
            "admin",
            "agent-hooks-doctor",
            "--hooks-dir",
            str(hooks_dir),
            "--claude-settings",
            str(claude_settings),
            "--opencode-plugin",
            str(opencode_plugin),
        ],
    )
    install_result = runner.invoke(
        app,
        [
            "admin",
            "install-agent-hooks",
            "--hooks-dir",
            str(hooks_dir),
            "--claude-settings",
            str(claude_settings),
            "--opencode-plugin",
            str(opencode_plugin),
        ],
    )
    installed_result = runner.invoke(
        app,
        [
            "admin",
            "agent-hooks-doctor",
            "--hooks-dir",
            str(hooks_dir),
            "--claude-settings",
            str(claude_settings),
            "--opencode-plugin",
            str(opencode_plugin),
            "--json-out",
            str(installed_report_path),
        ],
    )
    installed_report = json.loads(installed_report_path.read_text("utf-8"))

    assert missing_result.exit_code != 0
    assert "agent_hooks=failed" in missing_result.stdout
    assert "check=hook_script ok=false" in missing_result.stdout
    assert install_result.exit_code == 0, install_result.stdout
    assert installed_result.exit_code == 0, installed_result.stdout
    assert installed_report["schema_version"] == 1
    datetime.fromisoformat(installed_report["generated_at"])
    assert "agent_hooks=ok" in installed_result.stdout
    assert "check=hook_script_smoke ok=true" in installed_result.stdout
    assert "check=claude_settings ok=true" in installed_result.stdout
    assert "check=opencode_plugin ok=true" in installed_result.stdout


def test_admin_agent_hooks_doctor_rejects_broken_hook_script(
    tmp_path: Path,
) -> None:
    hooks_dir = tmp_path / "hooks"
    claude_settings = tmp_path / "claude" / "settings.json"
    opencode_plugin = tmp_path / "opencode" / "plugins" / "coding-pet.js"
    install_result = runner.invoke(
        app,
        [
            "admin",
            "install-agent-hooks",
            "--hooks-dir",
            str(hooks_dir),
            "--claude-settings",
            str(claude_settings),
            "--opencode-plugin",
            str(opencode_plugin),
        ],
    )
    script = hooks_dir / "coding-pet-hook.sh"
    script.write_text("#!/usr/bin/env bash\nexit 7\n", encoding="utf-8")
    script.chmod(0o755)

    result = runner.invoke(
        app,
        [
            "admin",
            "agent-hooks-doctor",
            "--hooks-dir",
            str(hooks_dir),
            "--claude-settings",
            str(claude_settings),
            "--opencode-plugin",
            str(opencode_plugin),
        ],
    )

    assert install_result.exit_code == 0, install_result.stdout
    assert result.exit_code == 1
    assert "agent_hooks=failed" in result.stdout
    assert "check=hook_script_smoke ok=false" in result.stdout
    assert "returncode=7" in result.stdout


def test_daemon_send_tmux_action_reports_invalid_requests(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from coding_pet.tmux.models import TmuxPaneInfo

    monkeypatch.setenv("HOME", str(tmp_path))

    class FakeTmuxClient:
        def list_panes(self) -> list[TmuxPaneInfo]:
            return [
                TmuxPaneInfo("%3", "claude-auth", "0.0", "claude", "/proj/ws/auth", None),
            ]

        def capture_pane(self, pane_id: str, *, lines: int) -> str:
            return "Need clarification: which env?"

    monkeypatch.setattr("coding_pet.cli.TmuxClient", lambda: FakeTmuxClient())

    result = runner.invoke(
        app,
        [
            "daemon",
            "send-tmux-action",
            "--pane",
            "%3",
            "--agent",
            "claude_code",
            "--action",
            "send_reply",
        ],
    )

    assert result.exit_code != 0
    assert "invalid action request:" in result.stdout.lower()
    assert "send_reply requires reply_text" in result.stdout


def test_admin_doctor_reports_tmux_and_transcript_health(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("CODING_PET_TMUX_ENABLED", "1")
    monkeypatch.setattr(
        "coding_pet.agents.registry.shutil.which",
        lambda name: None if name in {"claude", "opencode", "codex"} else "/usr/bin/fake",
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
    assert "transcript_redact_secrets=true" in result.stdout
    assert "transcript_custom_redaction_patterns=0" in result.stdout


def test_configured_transcript_store_uses_redaction_config(tmp_path: Path) -> None:
    from coding_pet.cli import _configured_transcript_store
    from coding_pet.config import AppConfig, TranscriptConfig

    config = AppConfig(
        config_dir=tmp_path / "cfg",
        state_dir=tmp_path / "state",
        runtime_dir=tmp_path / "run",
        log_dir=tmp_path / "logs",
        state_file=tmp_path / "state" / "state.json",
        transcript=TranscriptConfig(
            enabled=True,
            redact_secrets=False,
            custom_redaction_patterns=(r"PROJECT-[0-9]{4}",),
            db_path=tmp_path / "custom-transcripts.sqlite",
        ),
    )

    store = _configured_transcript_store(config)

    assert store is not None
    assert store.path == tmp_path / "custom-transcripts.sqlite"
    assert store.redact_secrets is False
    assert store.custom_redaction_patterns == (r"PROJECT-[0-9]{4}",)


def test_admin_list_pets_includes_bundled_and_imported_codex_pets(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pets_root = tmp_path / "pets"
    pet_dir = pets_root / "boba"
    pet_dir.mkdir(parents=True)
    write_webp_header(pet_dir / "spritesheet.webp")
    (pet_dir / "pet.json").write_text(
        '{"id":"boba","displayName":"Boba","spritesheetPath":"spritesheet.webp"}',
        encoding="utf-8",
    )
    monkeypatch.setenv("CODING_PET_CODEX_PETS_DIR", str(pets_root))

    result = runner.invoke(app, ["admin", "list-pets"])

    assert result.exit_code == 0
    assert "codex-default" in result.stdout
    assert "coding_pet" in result.stdout
    assert "boba" in result.stdout
    assert "codex_pet" in result.stdout


def test_admin_validate_pet_reports_codex_pet_package(tmp_path: Path) -> None:
    pet_dir = tmp_path / "boba"
    pet_dir.mkdir()
    write_webp_header(pet_dir / "spritesheet.webp")
    (pet_dir / "pet.json").write_text(
        '{"id":"boba","displayName":"Boba","spritesheetPath":"spritesheet.webp"}',
        encoding="utf-8",
    )

    result = runner.invoke(app, ["admin", "validate-pet", str(pet_dir)])

    assert result.exit_code == 0
    assert "valid_pet=boba" in result.stdout
    assert "display_name=Boba" in result.stdout
    assert "theme_format=codex_pet" in result.stdout
    assert "spritesheet=spritesheet.webp" in result.stdout
    assert "atlas_size=1536x1872" in result.stdout
    assert "atlas_cells=ok" in result.stdout
    assert "atlas_warnings=0" in result.stdout


def test_admin_validate_pet_writes_official_style_json_report(tmp_path: Path) -> None:
    pet_dir = tmp_path / "boba"
    pet_dir.mkdir()
    write_webp_header(pet_dir / "spritesheet.webp")
    (pet_dir / "pet.json").write_text(
        '{"id":"boba","displayName":"Boba","spritesheetPath":"spritesheet.webp"}',
        encoding="utf-8",
    )
    report_path = tmp_path / "qa" / "validation.json"

    result = runner.invoke(
        app,
        [
            "admin",
            "validate-pet",
            str(pet_dir),
            "--json-out",
            str(report_path),
        ],
    )

    report = json.loads(report_path.read_text("utf-8"))

    assert result.exit_code == 0
    assert report["ok"] is True
    assert report["theme_id"] == "boba"
    assert report["theme_format"] == "codex_pet"
    assert report["spritesheet"] == "spritesheet.webp"
    assert report["atlas_size"] == {"width": 1536, "height": 1872}
    assert report["atlas_grid"] == {"columns": 8, "rows": 9}
    assert report["frame_size"] == {"width": 192, "height": 208}
    assert report["frame_counts_by_row"]["4"] == 5
    assert report["frame_durations_by_row"]["0"] == [280, 110, 110, 140, 140, 320]
    assert report["frame_durations_by_row"]["7"] == [120, 120, 120, 120, 120, 220]
    assert report["mood_rows"]["typing"] == 7
    assert report["atlas_cells"]["ok"] is True
    assert report["atlas_cells"]["errors"] == []


def test_admin_validate_pet_accepts_zip_package(tmp_path: Path) -> None:
    pet_dir = tmp_path / "download" / "boba"
    pet_dir.mkdir(parents=True)
    write_webp_header(pet_dir / "spritesheet.webp")
    (pet_dir / "pet.json").write_text(
        '{"id":"boba","displayName":"Boba","spritesheetPath":"spritesheet.webp"}',
        encoding="utf-8",
    )
    archive = tmp_path / "boba.zip"
    write_pet_zip(pet_dir, archive, top_level="boba")
    report_path = tmp_path / "qa" / "validation.json"

    result = runner.invoke(
        app,
        ["admin", "validate-pet", str(archive), "--json-out", str(report_path)],
    )
    report = json.loads(report_path.read_text("utf-8"))

    assert result.exit_code == 0
    assert "valid_pet=boba" in result.stdout
    assert report["source_package"] == str(archive)
    assert report["theme_id"] == "boba"


def test_admin_validate_pet_accepts_petdex_petjson_package(tmp_path: Path) -> None:
    pet_dir = tmp_path / "boba"
    pet_dir.mkdir()
    write_webp_header(pet_dir / "spritesheet.webp")
    (pet_dir / "petjson.json").write_text(
        '{"slug":"boba","displayName":"Boba","spritesheetPath":"spritesheet.webp"}',
        encoding="utf-8",
    )
    report_path = tmp_path / "validation.json"

    result = runner.invoke(
        app,
        ["admin", "validate-pet", str(pet_dir), "--json-out", str(report_path)],
    )
    report = json.loads(report_path.read_text("utf-8"))

    assert result.exit_code == 0
    assert "valid_pet=boba" in result.stdout
    assert report["manifest"].endswith("petjson.json")
    assert report["theme_id"] == "boba"


def test_admin_validate_pet_infers_petdex_layout_without_states(
    tmp_path: Path,
) -> None:
    pet_dir = tmp_path / "boba"
    pet_dir.mkdir()
    write_webp_header(pet_dir / "spritesheet.webp", width=1728, height=1664)
    (pet_dir / "pet.json").write_text(
        '{"id":"boba","displayName":"Boba","spritesheetPath":"spritesheet.webp"}',
        encoding="utf-8",
    )
    report_path = tmp_path / "validation.json"

    result = runner.invoke(
        app,
        ["admin", "validate-pet", str(pet_dir), "--json-out", str(report_path)],
    )
    report = json.loads(report_path.read_text("utf-8"))

    assert result.exit_code == 0
    assert "valid_pet=boba" in result.stdout
    assert "atlas_size=1728x1664" in result.stdout
    assert report["atlas_grid"] == {"columns": 9, "rows": 8}
    assert report["frame_counts_by_row"]["0"] == 6
    assert report["frame_durations_by_row"]["0"] == [184, 184, 183, 183, 183, 183]
    assert report["mood_rows"]["typing"] == 2
    assert report["mood_rows"]["alert"] == 4
    assert report["mood_rows"]["celebrate"] == 5


def test_admin_download_petdex_writes_zip_metadata_and_validates_package(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source" / "boba"
    source.mkdir(parents=True)
    write_webp_header(source / "spritesheet.webp")
    (source / "pet.json").write_text(
        '{"id":"boba","displayName":"Boba","spritesheetPath":"spritesheet.webp"}',
        encoding="utf-8",
    )
    archive = tmp_path / "source" / "boba.zip"
    write_pet_zip(source, archive)
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "generatedAt": "2026-06-02T00:00:00Z",
                "total": 1,
                "pets": [
                    {
                        "slug": "boba",
                        "displayName": "Boba",
                        "kind": "creature",
                        "zipUrl": archive.as_uri(),
                        "petJsonUrl": (source / "pet.json").as_uri(),
                        "spritesheetUrl": (source / "spritesheet.webp").as_uri(),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    output_dir = tmp_path / "staging"
    report_path = tmp_path / "download-report.json"

    result = runner.invoke(
        app,
        [
            "admin",
            "download-petdex",
            "boba",
            "--manifest-url",
            manifest.as_uri(),
            "--output-dir",
            str(output_dir),
            "--json-out",
            str(report_path),
        ],
    )
    metadata = json.loads((output_dir / "boba.petdex.json").read_text("utf-8"))
    report = json.loads(report_path.read_text("utf-8"))

    assert result.exit_code == 0
    assert "petdex_download=ok" in result.stdout
    assert f"archive={output_dir / 'boba.zip'}" in result.stdout
    assert f"metadata={output_dir / 'boba.petdex.json'}" in result.stdout
    assert "valid_pet=boba" in result.stdout
    assert (output_dir / "boba.zip").read_bytes() == archive.read_bytes()
    assert metadata == report
    assert metadata["ok"] is True
    assert metadata["slug"] == "boba"
    assert metadata["display_name"] == "Boba"
    assert metadata["zip_url"] == archive.as_uri()
    assert metadata["archive"] == str(output_dir / "boba.zip")
    assert len(metadata["archive_sha256"]) == 64
    assert metadata["archive_size_bytes"] == archive.stat().st_size
    assert metadata["validation"]["theme_id"] == "boba"
    assert metadata["validation"]["atlas_grid"] == {"columns": 8, "rows": 9}


def test_admin_download_petdex_rejects_missing_slug_without_archive(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps({"pets": [{"slug": "doraemon", "zipUrl": "file:///tmp/doraemon.zip"}]}),
        encoding="utf-8",
    )
    output_dir = tmp_path / "staging"

    result = runner.invoke(
        app,
        [
            "admin",
            "download-petdex",
            "boba",
            "--manifest-url",
            manifest.as_uri(),
            "--output-dir",
            str(output_dir),
        ],
    )

    assert result.exit_code != 0
    assert "petdex_download=failed" in result.stdout
    assert "Petdex pet slug not found: boba" in result.stdout
    assert (output_dir / "boba.zip").exists() is False


def test_admin_download_petdex_refuses_existing_archive_without_replace(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source" / "boba"
    source.mkdir(parents=True)
    write_webp_header(source / "spritesheet.webp")
    (source / "pet.json").write_text(
        '{"id":"boba","displayName":"Boba","spritesheetPath":"spritesheet.webp"}',
        encoding="utf-8",
    )
    archive = tmp_path / "source" / "boba.zip"
    write_pet_zip(source, archive)
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps({"pets": [{"slug": "boba", "zipUrl": archive.as_uri()}]}),
        encoding="utf-8",
    )
    output_dir = tmp_path / "staging"
    output_dir.mkdir()
    existing = output_dir / "boba.zip"
    existing.write_text("keep me", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "admin",
            "download-petdex",
            "boba",
            "--manifest-url",
            manifest.as_uri(),
            "--output-dir",
            str(output_dir),
        ],
    )

    assert result.exit_code != 0
    assert "petdex_download=failed" in result.stdout
    assert "already exists" in result.stdout
    assert existing.read_text("utf-8") == "keep me"


def test_admin_validate_pet_fails_for_broken_package(tmp_path: Path) -> None:
    pet_dir = tmp_path / "broken"
    pet_dir.mkdir()
    (pet_dir / "pet.json").write_text(
        '{"id":"broken","spritesheetPath":"missing.webp"}',
        encoding="utf-8",
    )

    result = runner.invoke(app, ["admin", "validate-pet", str(pet_dir)])

    assert result.exit_code != 0
    assert "invalid pet package:" in result.stdout.lower()
    assert "missing assets: missing.webp" in result.stdout


def test_admin_validate_pet_writes_json_report_for_invalid_package(tmp_path: Path) -> None:
    pet_dir = tmp_path / "broken"
    pet_dir.mkdir()
    (pet_dir / "pet.json").write_text(
        '{"id":"broken","spritesheetPath":"missing.webp"}',
        encoding="utf-8",
    )
    report_path = tmp_path / "qa" / "validation.json"

    result = runner.invoke(
        app,
        [
            "admin",
            "validate-pet",
            str(pet_dir),
            "--json-out",
            str(report_path),
        ],
    )

    report = json.loads(report_path.read_text("utf-8"))

    assert result.exit_code != 0
    assert report == {
        "ok": False,
        "package": str(pet_dir),
        "error": "missing assets: missing.webp",
    }


def test_admin_validate_pet_batch_reports_multiple_copied_packages(tmp_path: Path) -> None:
    source_dir = tmp_path / "downloaded"
    source_dir.mkdir()
    boba_dir = source_dir / "boba"
    boba_dir.mkdir()
    write_webp_header(boba_dir / "spritesheet.webp")
    (boba_dir / "pet.json").write_text(
        '{"id":"boba","displayName":"Boba","spritesheetPath":"spritesheet.webp"}',
        encoding="utf-8",
    )
    dora_dir = tmp_path / "doraemon-source"
    dora_dir.mkdir()
    write_webp_header(dora_dir / "spritesheet.webp")
    (dora_dir / "pet.json").write_text(
        '{"id":"doraemon","displayName":"Doraemon","spritesheetPath":"spritesheet.webp"}',
        encoding="utf-8",
    )
    write_pet_zip(dora_dir, source_dir / "doraemon.zip")
    broken_dir = source_dir / "broken"
    broken_dir.mkdir()
    (broken_dir / "pet.json").write_text(
        '{"id":"broken","spritesheetPath":"missing.webp"}',
        encoding="utf-8",
    )
    report_path = tmp_path / "batch.json"

    result = runner.invoke(
        app,
        [
            "admin",
            "validate-pet-batch",
            str(source_dir),
            "--json-out",
            str(report_path),
        ],
    )
    report = json.loads(report_path.read_text("utf-8"))

    assert result.exit_code != 0
    assert "pet_batch=failed" in result.stdout
    assert "total=3" in result.stdout
    assert "passed=2" in result.stdout
    assert "failed=1" in result.stdout
    assert "pet=boba ok=true warnings=0" in result.stdout
    assert "pet=doraemon ok=true warnings=0" in result.stdout
    assert "missing assets: missing.webp" in result.stdout
    assert report["ok"] is False
    assert report["total"] == 3
    assert report["passed"] == 2
    assert report["failed"] == 1
    assert [pet["ok"] for pet in report["pets"]] == [True, False, True]
    assert report["pets"][0]["theme_id"] == "boba"
    assert report["pets"][2]["theme_id"] == "doraemon"


def test_admin_validate_pet_batch_accepts_single_zip_source(tmp_path: Path) -> None:
    source_dir = tmp_path / "boba-source"
    source_dir.mkdir()
    write_webp_header(source_dir / "spritesheet.webp")
    (source_dir / "pet.json").write_text(
        '{"id":"boba","displayName":"Boba","spritesheetPath":"spritesheet.webp"}',
        encoding="utf-8",
    )
    archive = tmp_path / "boba.zip"
    write_pet_zip(source_dir, archive)
    report_path = tmp_path / "batch.json"

    result = runner.invoke(
        app,
        [
            "admin",
            "validate-pet-batch",
            str(archive),
            "--json-out",
            str(report_path),
        ],
    )
    report = json.loads(report_path.read_text("utf-8"))

    assert result.exit_code == 0
    assert "pet_batch=ok" in result.stdout
    assert "total=1" in result.stdout
    assert report["ok"] is True
    assert report["pets"][0]["theme_id"] == "boba"


def test_admin_validate_pet_batch_records_petdex_sidecar_metadata(
    tmp_path: Path,
) -> None:
    source_dir = tmp_path / "boba-source"
    source_dir.mkdir()
    write_webp_header(source_dir / "spritesheet.webp")
    (source_dir / "pet.json").write_text(
        '{"id":"boba","displayName":"Boba","spritesheetPath":"spritesheet.webp"}',
        encoding="utf-8",
    )
    archive = tmp_path / "boba.zip"
    write_pet_zip(source_dir, archive)
    sidecar = tmp_path / "boba.petdex.json"
    sidecar.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "ok": True,
                "source": "petdex",
                "slug": "boba",
                "display_name": "Boba",
                "zip_url": "https://example.invalid/boba.zip",
                "archive": str(archive),
                "archive_sha256": _sha256(archive),
                "archive_size_bytes": archive.stat().st_size,
            }
        ),
        encoding="utf-8",
    )
    report_path = tmp_path / "batch.json"

    result = runner.invoke(
        app,
        [
            "admin",
            "validate-pet-batch",
            str(archive),
            "--json-out",
            str(report_path),
        ],
    )
    report = json.loads(report_path.read_text("utf-8"))
    pet = report["pets"][0]

    assert result.exit_code == 0
    assert pet["theme_id"] == "boba"
    assert pet["petdex_metadata"] == {
        "path": str(sidecar),
        "sha256": _sha256(sidecar),
        "size_bytes": sidecar.stat().st_size,
        "schema_version": 1,
        "source": "petdex",
        "slug": "boba",
        "display_name": "Boba",
        "zip_url": "https://example.invalid/boba.zip",
        "archive_sha256": _sha256(archive),
        "archive_size_bytes": archive.stat().st_size,
    }


def test_admin_validate_pet_batch_discovers_petdex_petjson_directories(
    tmp_path: Path,
) -> None:
    source_dir = tmp_path / "downloaded"
    source_dir.mkdir()
    pet_dir = source_dir / "boba"
    pet_dir.mkdir()
    write_webp_header(pet_dir / "spritesheet.webp")
    (pet_dir / "petjson.json").write_text(
        '{"slug":"boba","displayName":"Boba","spritesheetPath":"spritesheet.webp"}',
        encoding="utf-8",
    )
    report_path = tmp_path / "batch.json"

    result = runner.invoke(
        app,
        [
            "admin",
            "validate-pet-batch",
            str(source_dir),
            "--json-out",
            str(report_path),
        ],
    )
    report = json.loads(report_path.read_text("utf-8"))

    assert result.exit_code == 0
    assert "pet_batch=ok" in result.stdout
    assert "total=1" in result.stdout
    assert report["ok"] is True
    assert report["pets"][0]["manifest"].endswith("petjson.json")
    assert report["pets"][0]["theme_id"] == "boba"


def test_admin_import_pet_batch_installs_multiple_valid_packages(tmp_path: Path) -> None:
    source_dir = tmp_path / "downloaded"
    source_dir.mkdir()
    boba_dir = source_dir / "boba"
    boba_dir.mkdir()
    write_webp_header(boba_dir / "spritesheet.webp")
    (boba_dir / "pet.json").write_text(
        '{"id":"boba","displayName":"Boba","spritesheetPath":"spritesheet.webp"}',
        encoding="utf-8",
    )
    dora_dir = tmp_path / "doraemon-source"
    dora_dir.mkdir()
    write_webp_header(dora_dir / "spritesheet.webp")
    (dora_dir / "pet.json").write_text(
        '{"id":"doraemon","displayName":"Doraemon","spritesheetPath":"spritesheet.webp"}',
        encoding="utf-8",
    )
    write_pet_zip(dora_dir, source_dir / "doraemon.zip")
    pets_root = tmp_path / "installed"
    report_path = tmp_path / "import-batch.json"

    result = runner.invoke(
        app,
        [
            "admin",
            "import-pet-batch",
            str(source_dir),
            "--pets-root",
            str(pets_root),
            "--json-out",
            str(report_path),
        ],
    )
    report = json.loads(report_path.read_text("utf-8"))

    assert result.exit_code == 0
    assert "pet_batch_import=ok" in result.stdout
    assert "total=2" in result.stdout
    assert "validated=2" in result.stdout
    assert "imported=2" in result.stdout
    assert f"target={pets_root / 'boba'}" in result.stdout
    assert f"target={pets_root / 'doraemon'}" in result.stdout
    assert (pets_root / "boba" / "pet.json").exists()
    assert (pets_root / "doraemon" / "spritesheet.webp").exists()
    assert report["ok"] is True
    assert report["imported"] == 2
    assert [entry["theme_id"] for entry in report["imports"]] == ["boba", "doraemon"]


def test_admin_import_pet_batch_refuses_invalid_batch_without_partial_import(
    tmp_path: Path,
) -> None:
    source_dir = tmp_path / "downloaded"
    source_dir.mkdir()
    boba_dir = source_dir / "boba"
    boba_dir.mkdir()
    write_webp_header(boba_dir / "spritesheet.webp")
    (boba_dir / "pet.json").write_text(
        '{"id":"boba","displayName":"Boba","spritesheetPath":"spritesheet.webp"}',
        encoding="utf-8",
    )
    broken_dir = source_dir / "broken"
    broken_dir.mkdir()
    (broken_dir / "pet.json").write_text(
        '{"id":"broken","spritesheetPath":"missing.webp"}',
        encoding="utf-8",
    )
    pets_root = tmp_path / "installed"

    result = runner.invoke(
        app,
        ["admin", "import-pet-batch", str(source_dir), "--pets-root", str(pets_root)],
    )

    assert result.exit_code != 0
    assert "pet_batch_import=failed" in result.stdout
    assert "validated=1" in result.stdout
    assert "imported=0" in result.stdout
    assert "validation failed" in result.stdout
    assert (pets_root / "boba").exists() is False


def test_admin_import_pet_batch_refuses_existing_target_without_partial_import(
    tmp_path: Path,
) -> None:
    source_dir = tmp_path / "downloaded"
    source_dir.mkdir()
    boba_dir = source_dir / "boba"
    boba_dir.mkdir()
    write_webp_header(boba_dir / "spritesheet.webp")
    (boba_dir / "pet.json").write_text(
        '{"id":"boba","displayName":"Boba","spritesheetPath":"spritesheet.webp"}',
        encoding="utf-8",
    )
    dora_dir = source_dir / "doraemon"
    dora_dir.mkdir()
    write_webp_header(dora_dir / "spritesheet.webp")
    (dora_dir / "pet.json").write_text(
        '{"id":"doraemon","displayName":"Doraemon","spritesheetPath":"spritesheet.webp"}',
        encoding="utf-8",
    )
    pets_root = tmp_path / "installed"
    (pets_root / "boba").mkdir(parents=True)

    result = runner.invoke(
        app,
        ["admin", "import-pet-batch", str(source_dir), "--pets-root", str(pets_root)],
    )

    assert result.exit_code != 0
    assert "pet_batch_import=failed" in result.stdout
    assert "pet package already exists" in result.stdout
    assert (pets_root / "doraemon").exists() is False


def test_admin_build_pet_qa_writes_official_bundle(tmp_path: Path) -> None:
    pet_dir = tmp_path / "boba"
    pet_dir.mkdir()
    write_webp_header(pet_dir / "spritesheet.webp")
    (pet_dir / "pet.json").write_text(
        '{"id":"boba","displayName":"Boba","spritesheetPath":"spritesheet.webp"}',
        encoding="utf-8",
    )
    output_dir = tmp_path / "qa"

    result = runner.invoke(
        app,
        [
            "admin",
            "build-pet-qa",
            str(pet_dir),
            "--output-dir",
            str(output_dir),
            "--cell-width",
            "24",
            "--size",
            "32",
        ],
    )

    validation = json.loads((output_dir / "validation.json").read_text("utf-8"))
    summary = json.loads((output_dir / "run-summary.json").read_text("utf-8"))

    assert result.exit_code == 0
    assert "qa_pet=boba" in result.stdout
    assert "animation_preview_count=9" in result.stdout
    assert validation["ok"] is True
    assert validation["theme_id"] == "boba"
    assert summary["ok"] is True
    assert summary["theme_id"] == "boba"
    assert summary["artifacts"]["validation"] == str(output_dir / "validation.json")
    assert summary["artifacts"]["contact_sheet"] == str(output_dir / "contact-sheet.png")
    assert len(summary["artifacts"]["animation_previews"]) == 9
    assert (output_dir / "contact-sheet.png").read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert (output_dir / "animation-previews" / "idle.gif").read_bytes().startswith(b"GIF")


def test_admin_build_pet_qa_accepts_zip_package(tmp_path: Path) -> None:
    pet_dir = tmp_path / "download" / "boba"
    pet_dir.mkdir(parents=True)
    write_webp_header(pet_dir / "spritesheet.webp")
    (pet_dir / "pet.json").write_text(
        '{"id":"boba","displayName":"Boba","spritesheetPath":"spritesheet.webp"}',
        encoding="utf-8",
    )
    archive = tmp_path / "boba.zip"
    write_pet_zip(pet_dir, archive, top_level="boba")
    output_dir = tmp_path / "qa"

    result = runner.invoke(
        app,
        [
            "admin",
            "build-pet-qa",
            str(archive),
            "--output-dir",
            str(output_dir),
            "--cell-width",
            "24",
            "--size",
            "32",
        ],
    )
    validation = json.loads((output_dir / "validation.json").read_text("utf-8"))

    assert result.exit_code == 0
    assert "qa_pet=boba" in result.stdout
    assert validation["source_package"] == str(archive)
    assert (output_dir / "contact-sheet.png").exists()
    assert (output_dir / "animation-previews" / "idle.gif").exists()


def test_admin_build_pet_qa_writes_failure_reports_for_invalid_package(tmp_path: Path) -> None:
    pet_dir = tmp_path / "broken"
    pet_dir.mkdir()
    (pet_dir / "pet.json").write_text(
        '{"id":"broken","spritesheetPath":"missing.webp"}',
        encoding="utf-8",
    )
    output_dir = tmp_path / "qa"

    result = runner.invoke(
        app,
        [
            "admin",
            "build-pet-qa",
            str(pet_dir),
            "--output-dir",
            str(output_dir),
        ],
    )

    validation = json.loads((output_dir / "validation.json").read_text("utf-8"))
    summary = json.loads((output_dir / "run-summary.json").read_text("utf-8"))

    assert result.exit_code != 0
    assert "pet qa failed:" in result.stdout.lower()
    assert validation == {
        "ok": False,
        "package": str(pet_dir),
        "error": "missing assets: missing.webp",
    }
    assert summary["ok"] is False
    assert summary["error"] == "missing assets: missing.webp"
    assert (output_dir / "contact-sheet.png").exists() is False


def test_admin_import_pet_installs_package_into_codex_pets_root(tmp_path: Path) -> None:
    source = tmp_path / "download" / "boba"
    source.mkdir(parents=True)
    write_webp_header(source / "spritesheet.webp")
    (source / "pet.json").write_text(
        '{"id":"boba","displayName":"Boba","spritesheetPath":"spritesheet.webp"}',
        encoding="utf-8",
    )
    pets_root = tmp_path / "installed"

    result = runner.invoke(
        app,
        ["admin", "import-pet", str(source), "--pets-root", str(pets_root)],
    )

    assert result.exit_code == 0
    assert "imported_pet=boba" in result.stdout
    assert "theme_format=codex_pet" in result.stdout
    assert "atlas_size=1536x1872" in result.stdout
    assert "atlas_cells=ok" in result.stdout
    assert f"target={pets_root / 'boba'}" in result.stdout
    assert (pets_root / "boba" / "pet.json").exists()
    assert (pets_root / "boba" / "spritesheet.webp").exists()


def test_admin_import_pet_accepts_zip_package(tmp_path: Path) -> None:
    source = tmp_path / "download" / "boba"
    source.mkdir(parents=True)
    write_webp_header(source / "spritesheet.webp")
    (source / "pet.json").write_text(
        '{"id":"boba","displayName":"Boba","spritesheetPath":"spritesheet.webp"}',
        encoding="utf-8",
    )
    archive = tmp_path / "boba.zip"
    write_pet_zip(source, archive, top_level="boba")
    pets_root = tmp_path / "installed"

    result = runner.invoke(
        app,
        ["admin", "import-pet", str(archive), "--pets-root", str(pets_root)],
    )

    assert result.exit_code == 0
    assert "imported_pet=boba" in result.stdout
    assert f"target={pets_root / 'boba'}" in result.stdout
    assert (pets_root / "boba" / "pet.json").exists()
    assert (pets_root / "boba" / "spritesheet.webp").exists()


def test_admin_import_pet_normalizes_petdex_petjson_zip(tmp_path: Path) -> None:
    source = tmp_path / "download" / "boba"
    source.mkdir(parents=True)
    write_webp_header(source / "spritesheet.webp")
    (source / "petjson.json").write_text(
        '{"slug":"boba","displayName":"Boba","spritesheetPath":"spritesheet.webp"}',
        encoding="utf-8",
    )
    archive = tmp_path / "boba.zip"
    write_pet_zip(source, archive, top_level="boba")
    pets_root = tmp_path / "installed"

    result = runner.invoke(
        app,
        ["admin", "import-pet", str(archive), "--pets-root", str(pets_root)],
    )

    assert result.exit_code == 0
    assert "imported_pet=boba" in result.stdout
    assert f"manifest={pets_root / 'boba' / 'pet.json'}" in result.stdout
    assert (pets_root / "boba" / "pet.json").exists()
    assert (pets_root / "boba" / "petjson.json").exists()


def test_admin_set_pet_persists_imported_theme_in_service_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pets_root = tmp_path / "pets"
    pet_dir = pets_root / "boba"
    pet_dir.mkdir(parents=True)
    write_webp_header(pet_dir / "spritesheet.webp")
    (pet_dir / "pet.json").write_text(
        '{"id":"boba","displayName":"Boba","spritesheetPath":"spritesheet.webp"}',
        encoding="utf-8",
    )
    service_env = tmp_path / "config" / "service.env"
    service_env.parent.mkdir()
    service_env.write_text(
        "# keep this comment\nCODING_PET_LOG_LEVEL=debug\nCODING_PET_THEME=old\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CODING_PET_CODEX_PETS_DIR", str(pets_root))

    result = runner.invoke(
        app,
        ["admin", "set-pet", "boba", "--service-env", str(service_env)],
    )

    assert result.exit_code == 0
    assert "selected_pet=boba" in result.stdout
    assert f"service_env={service_env}" in result.stdout
    assert "CODING_PET_THEME=boba" in service_env.read_text("utf-8")
    assert f"CODING_PET_CODEX_PETS_DIR={pets_root}" in service_env.read_text("utf-8")
    assert "# keep this comment" in service_env.read_text("utf-8")
    assert "CODING_PET_LOG_LEVEL=debug" in service_env.read_text("utf-8")
    assert "CODING_PET_THEME=old" not in service_env.read_text("utf-8")


def test_admin_set_pet_fails_when_theme_is_unknown(tmp_path: Path) -> None:
    service_env = tmp_path / "config" / "service.env"

    result = runner.invoke(
        app,
        ["admin", "set-pet", "missing-pet", "--service-env", str(service_env)],
    )

    assert result.exit_code != 0
    assert "pet selection failed:" in result.stdout.lower()
    assert service_env.exists() is False


def test_admin_inspect_pet_reports_codex_animation_plan(
    tmp_path: Path,
) -> None:
    pets_root = tmp_path / "pets"
    pet_dir = pets_root / "boba"
    pet_dir.mkdir(parents=True)
    write_webp_header(pet_dir / "spritesheet.webp")
    (pet_dir / "pet.json").write_text(
        '{"id":"boba","displayName":"Boba","spritesheetPath":"spritesheet.webp"}',
        encoding="utf-8",
    )

    result = runner.invoke(app, ["admin", "inspect-pet", "boba", "--pets-root", str(pets_root)])

    assert result.exit_code == 0
    assert "pet=boba" in result.stdout
    assert "theme_format=codex_pet" in result.stdout
    assert "atlas_size=1536x1872" in result.stdout
    assert "atlas_grid=8x9" in result.stdout
    assert "frame_size=192x208" in result.stdout
    assert "mood=alert row=6 frames=6 first_rect=0,1248,192,208" in result.stdout
    assert "mood=celebrate row=4 frames=5 first_rect=0,832,192,208" in result.stdout


def test_admin_inspect_pet_reports_bundled_theme_assets() -> None:
    result = runner.invoke(app, ["admin", "inspect-pet", "codex-default"])

    assert result.exit_code == 0
    assert "pet=codex-default" in result.stdout
    assert "theme_format=coding_pet" in result.stdout
    assert "mood=idle asset=codex-default/idle.png exists=true" in result.stdout


def test_admin_render_pet_frame_writes_codex_preview_png(tmp_path: Path) -> None:
    pets_root = tmp_path / "pets"
    pet_dir = pets_root / "boba"
    pet_dir.mkdir(parents=True)
    write_solid_png(pet_dir / "spritesheet.png", width=16, height=18)
    (pet_dir / "pet.json").write_text(
        (
            '{"id":"boba","displayName":"Boba","spritesheetPath":"spritesheet.png",'
            '"columns":8,"rows":9,"frame":{"width":2,"height":2}}'
        ),
        encoding="utf-8",
    )
    output = tmp_path / "preview.png"

    result = runner.invoke(
        app,
        [
            "admin",
            "render-pet-frame",
            "boba",
            "--mood",
            "alert",
            "--output",
            str(output),
            "--pets-root",
            str(pets_root),
        ],
    )

    assert result.exit_code == 0
    assert "rendered_pet=boba" in result.stdout
    assert "mood=alert" in result.stdout
    assert "source_rect=0,12,2,2" in result.stdout
    assert "output_size=96x96" in result.stdout
    assert output.exists()
    assert output.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


def test_admin_render_pet_contact_sheet_writes_codex_qa_png(tmp_path: Path) -> None:
    pets_root = tmp_path / "pets"
    pet_dir = pets_root / "boba"
    pet_dir.mkdir(parents=True)
    write_webp_header(pet_dir / "spritesheet.webp")
    (pet_dir / "pet.json").write_text(
        '{"id":"boba","displayName":"Boba","spritesheetPath":"spritesheet.webp"}',
        encoding="utf-8",
    )
    output = tmp_path / "contact-sheet.png"

    result = runner.invoke(
        app,
        [
            "admin",
            "render-pet-contact-sheet",
            "boba",
            "--output",
            str(output),
            "--pets-root",
            str(pets_root),
            "--cell-width",
            "24",
        ],
    )

    assert result.exit_code == 0
    assert "rendered_pet=boba" in result.stdout
    assert "atlas_grid=8x9" in result.stdout
    assert "used_frames=57" in result.stdout
    assert "output_size=366x322" in result.stdout
    assert output.exists()
    assert output.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


def test_admin_render_pet_contact_sheet_fails_for_text_theme(tmp_path: Path) -> None:
    output = tmp_path / "contact-sheet.png"

    result = runner.invoke(
        app,
        [
            "admin",
            "render-pet-contact-sheet",
            "classic",
            "--output",
            str(output),
        ],
    )

    assert result.exit_code != 0
    assert "pet contact sheet failed:" in result.stdout.lower()
    assert "contact sheets require a Codex pet spritesheet" in result.stdout
    assert output.exists() is False


def test_admin_render_pet_animation_previews_writes_codex_gifs(tmp_path: Path) -> None:
    pets_root = tmp_path / "pets"
    pet_dir = pets_root / "boba"
    pet_dir.mkdir(parents=True)
    write_webp_header(pet_dir / "spritesheet.webp")
    (pet_dir / "pet.json").write_text(
        '{"id":"boba","displayName":"Boba","spritesheetPath":"spritesheet.webp"}',
        encoding="utf-8",
    )
    output_dir = tmp_path / "previews"

    result = runner.invoke(
        app,
        [
            "admin",
            "render-pet-animation-previews",
            "boba",
            "--output-dir",
            str(output_dir),
            "--pets-root",
            str(pets_root),
            "--size",
            "32",
        ],
    )

    assert result.exit_code == 0
    assert "rendered_pet=boba" in result.stdout
    assert "atlas_grid=8x9" in result.stdout
    assert "preview_count=9" in result.stdout
    assert "idle.gif" in result.stdout
    assert "running-right.gif" in result.stdout
    assert (output_dir / "idle.gif").read_bytes().startswith(b"GIF")
    assert (output_dir / "running-right.gif").read_bytes().startswith(b"GIF")
    assert len(list(output_dir.glob("*.gif"))) == 9
    from PIL import Image, ImageSequence

    with Image.open(output_dir / "idle.gif") as gif:
        durations = [frame.info["duration"] for frame in ImageSequence.Iterator(gif)]
    assert durations == [280, 110, 110, 140, 140, 320]


def test_admin_render_pet_animation_previews_fails_for_text_theme(tmp_path: Path) -> None:
    output_dir = tmp_path / "previews"

    result = runner.invoke(
        app,
        [
            "admin",
            "render-pet-animation-previews",
            "classic",
            "--output-dir",
            str(output_dir),
        ],
    )

    assert result.exit_code != 0
    assert "pet animation previews failed:" in result.stdout.lower()
    assert "animation previews require a Codex pet spritesheet" in result.stdout
    assert output_dir.exists() is False


def test_admin_render_pet_frame_fails_for_text_theme(tmp_path: Path) -> None:
    output = tmp_path / "preview.png"

    result = runner.invoke(
        app,
        [
            "admin",
            "render-pet-frame",
            "classic",
            "--mood",
            "idle",
            "--output",
            str(output),
        ],
    )

    assert result.exit_code != 0
    assert "pet render failed:" in result.stdout.lower()
    assert output.exists() is False
