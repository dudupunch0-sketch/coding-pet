from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid
import zipfile
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TypeGuard, cast

import typer

from coding_pet.agents.registry import AgentBackendRegistry
from coding_pet.config import AppConfig, load_config
from coding_pet.daemon.action_router import SessionActionRequest, SupportedAction
from coding_pet.daemon.app import DaemonApp
from coding_pet.daemon.manager import MonitorManager
from coding_pet.daemon.runtime import DaemonRuntime, default_socket_path
from coding_pet.daemon.session_registry import SessionRegistry
from coding_pet.daemon.tmux_monitor import TmuxMonitorService, session_id_for_pane
from coding_pet.gui.runtime import gui_runtime_status, has_graphical_session
from coding_pet.gui.theme import (
    CODEX_PET_MANIFEST_FILENAMES,
    REMOVED_LEGACY_THEME_NAMES,
    WidgetMood,
    codex_pet_frame_count,
    codex_pet_frame_duration_ms,
    codex_pet_frame_rect,
    codex_pet_package_source,
    configured_theme,
    default_assets_root,
    default_codex_pets_root,
    default_theme_registry_path,
    discover_theme_choices,
    import_codex_pet_package,
    load_manifest_for_theme,
    load_theme_registry,
    read_image_size,
    resolve_sprite_for_mood,
    validate_codex_pet_package,
    validate_theme_assets,
)
from coding_pet.gui.widget import CodingPetWidgetShell
from coding_pet.hooks import (
    claude_settings_has_hooks,
    claude_settings_snippet,
    hook_script_source,
    hook_session_id,
    merge_claude_settings,
    opencode_plugin_has_hooks,
    opencode_plugin_source,
)
from coding_pet.ipc.client import IpcClient
from coding_pet.models import (
    ActionOutcome,
    AgentKind,
    AttentionState,
    SessionStatus,
    action_capability_for,
)
from coding_pet.state_store import StateStore
from coding_pet.tmux.capture import snapshot_hash
from coding_pet.tmux.client import TmuxClient, TmuxCommandError
from coding_pet.tmux.control import (
    DEFAULT_TMUX_CONTROL_CHECK_TEXT,
    run_tmux_control_check,
)
from coding_pet.tmux.discovery import discover_agent_panes
from coding_pet.tmux.models import MatchedTmuxPane
from coding_pet.transcripts.store import TranscriptStore, redact_transcript_text

AGENT_OPTION = typer.Option(..., "--agent", case_sensitive=False)
CMD_OPTION = typer.Option(..., "--cmd")
WORKSPACE_OPTION = typer.Option(..., "--workspace")
OPTIONAL_WORKSPACE_OPTION = typer.Option(None, "--workspace")
TITLE_OPTION = typer.Option(None, "--title")
SUMMARY_OPTION = typer.Option(None, "--summary")
SESSION_ID_OPTION = typer.Option(None, "--session-id")
REQUIRED_SESSION_ID_OPTION = typer.Option(..., "--session-id")
PACKAGE_ARGUMENT = typer.Argument(...)
REPORT_ARGUMENT = typer.Argument(...)
EVIDENCE_DIR_ARGUMENT = typer.Argument(...)
THEME_ARGUMENT = typer.Argument(...)
WHEELHOUSE_ARGUMENT = typer.Argument(...)
PETS_ROOT_OPTION = typer.Option(None, "--pets-root")
REPLACE_OPTION = typer.Option(False, "--replace")
SERVICE_ENV_OPTION = typer.Option(None, "--service-env")
MOOD_OPTION = typer.Option(WidgetMood.IDLE, "--mood", case_sensitive=False)
OUTPUT_OPTION = typer.Option(..., "--output")
OUTPUT_DIR_OPTION = typer.Option(..., "--output-dir")
HOOKS_DIR_OPTION = typer.Option(None, "--hooks-dir")
CLAUDE_SETTINGS_OPTION = typer.Option(None, "--claude-settings")
OPENCODE_PLUGIN_OPTION = typer.Option(None, "--opencode-plugin")
WHEELHOUSE_OPTION = typer.Option(None, "--wheelhouse")
PET_SOURCE_OPTION = typer.Option(None, "--pet-source")
SKIP_CLAUDE_OPTION = typer.Option(False, "--skip-claude")
SKIP_OPENCODE_OPTION = typer.Option(False, "--skip-opencode")
REQUIRE_AGENT_HOOKS_OPTION = typer.Option(False, "--require-agent-hooks")
REQUIRE_WHEELHOUSE_OPTION = typer.Option(False, "--require-wheelhouse")
REQUIRE_PET_PACKAGES_OPTION = typer.Option(False, "--require-pet-packages")
WIDGET_SMOKE_REQUIRED_OPTION = typer.Option(False, "--required")
CELL_WIDTH_OPTION = typer.Option(96, "--cell-width")
PREVIEW_SIZE_OPTION = typer.Option(96, "--size")
PANE_OPTION = typer.Option(..., "--pane")
CLAUDE_PANE_OPTION = typer.Option(..., "--claude-pane")
OPENCODE_PANE_OPTION = typer.Option(..., "--opencode-pane")
CLAUDE_REPLY_PANE_OPTION = typer.Option(None, "--claude-reply-pane")
CLAUDE_APPROVE_PANE_OPTION = typer.Option(None, "--claude-approve-pane")
CLAUDE_REJECT_PANE_OPTION = typer.Option(None, "--claude-reject-pane")
OPENCODE_REPLY_PANE_OPTION = typer.Option(None, "--opencode-reply-pane")
OPENCODE_APPROVE_PANE_OPTION = typer.Option(None, "--opencode-approve-pane")
OPENCODE_REJECT_PANE_OPTION = typer.Option(None, "--opencode-reject-pane")
ACTION_OPTION = typer.Option(..., "--action")
OPTIONAL_ACTION_OPTION = typer.Option(None, "--action")
OPTIONAL_AGENT_OPTION = typer.Option(None, "--agent", case_sensitive=False)
EVENT_OPTION = typer.Option(..., "--event")
REPLY_TEXT_OPTION = typer.Option(None, "--reply-text")
TARGET_REPLY_TEXT_OPTION = typer.Option(
    "coding-pet target validation: please acknowledge this harmless reply.",
    "--reply-text",
)
REPLY_EXPECT_REGEX_OPTION = typer.Option(..., "--reply-expect-regex")
APPROVE_EXPECT_REGEX_OPTION = typer.Option(..., "--approve-expect-regex")
REJECT_EXPECT_REGEX_OPTION = typer.Option(..., "--reject-expect-regex")
NO_ENTER_OPTION = typer.Option(False, "--no-enter")
SOCKET_OPTION = typer.Option(None, "--socket")
JSON_OUT_OPTION = typer.Option(None, "--json-out")
EXPECT_REGEX_OPTION = typer.Option(
    None,
    "--expect-regex",
    help="Regex expected in the tmux pane after the action is sent.",
)
ALLOW_UNCHANGED_OUTPUT_OPTION = typer.Option(
    False,
    "--allow-unchanged-output",
    help="Accept evidence even when before/after tmux output hashes are identical.",
)
CAPTURE_LINES_OPTION = typer.Option(200, "--capture-lines")
SKIP_TMUX_CONTROL_OPTION = typer.Option(
    False,
    "--skip-tmux-control",
    help="Skip the disposable tmux raw-input probe in evidence bundles.",
)
SKIP_SYSTEMD_VERIFY_OPTION = typer.Option(
    False,
    "--skip-systemd-verify",
    help="Skip systemd user unit syntax verification in evidence bundles.",
)
SKIP_INSTALL_SMOKE_OPTION = typer.Option(
    False,
    "--skip-install-smoke",
    help="Only inspect wheelhouse files; do not create a temporary venv install smoke test.",
)
INSTALL_TARGET_OPTION = typer.Option(
    "coding-pet[gui]",
    "--install-target",
    help="Package spec to install during wheelhouse smoke validation.",
)
TMUX_CONTROL_CHECK_TEXT_OPTION = typer.Option(
    DEFAULT_TMUX_CONTROL_CHECK_TEXT,
    "--text",
    help="Text to paste into the disposable tmux probe session.",
)
TMUX_CONTROL_CHECK_TIMEOUT_OPTION = typer.Option(
    5.0,
    "--timeout-s",
    help="Seconds to wait for the disposable tmux probe.",
)
ACCEPTANCE_PROFILE_OPTION = typer.Option(
    "current",
    "--profile",
    help="Acceptance profile: current or target.",
)
PETDEX_DEFAULT_MANIFEST_URL = "https://petdex.crafter.run/api/manifest"
PETDEX_USER_AGENT = "coding-pet/0.1 Petdex staging downloader"
PETDEX_MANIFEST_URL_OPTION = typer.Option(
    PETDEX_DEFAULT_MANIFEST_URL,
    "--manifest-url",
    help="Petdex manifest URL. Override this for mirrors or tests.",
)
DOWNLOAD_TIMEOUT_OPTION = typer.Option(
    30.0,
    "--timeout-s",
    help="Seconds to wait for Petdex manifest and ZIP downloads.",
)

REDHAT_RELEASE_PATH = Path("/etc/redhat-release")
TARGET_REQUIRED_AGENTS = (AgentKind.CLAUDE_CODE, AgentKind.OPENCODE)
TARGET_ACCEPTANCE_REQUIRED_CHECKS = (
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
TARGET_BACKEND_EVIDENCE_REQUIREMENTS = (
    (AgentKind.CLAUDE_CODE, "send_reply"),
    (AgentKind.CLAUDE_CODE, "approve"),
    (AgentKind.CLAUDE_CODE, "reject"),
    (AgentKind.OPENCODE, "send_reply"),
    (AgentKind.OPENCODE, "approve"),
    (AgentKind.OPENCODE, "reject"),
)
TARGET_AGENT_HOOK_REQUIRED_CHECKS = (
    "hook_script",
    "hook_script_smoke",
    "claude_settings",
    "opencode_plugin",
)
BACKEND_EVIDENCE_SUMMARY_FILENAME = "backend-summary.json"
EVIDENCE_BUNDLE_SCHEMA_VERSION = 1
SYSTEMD_UNIT_NAMES = (
    "coding-pet-daemon.service",
    "coding-pet-widget.service",
    "coding-pet.target",
)
SYSTEMD_RUNTIME_UNIT_NAMES = SYSTEMD_UNIT_NAMES
HOOK_EVENT_SMOKE_AGENT = AgentKind.CLAUDE_CODE
HOOK_EVENT_SMOKE_EVENT = "PreToolUse"
HOOK_EVENT_SMOKE_SESSION_ID = "coding-pet-hook-smoke"
HOOK_EVENT_SMOKE_TITLE = "Coding Pet Hook Smoke"
HOOK_EVENT_SMOKE_SUMMARY = "coding-pet hook event smoke"
HOOK_EVENT_SMOKE_TRANSCRIPT_TEXT = f"{HOOK_EVENT_SMOKE_EVENT}: {HOOK_EVENT_SMOKE_SUMMARY}"
RHEL8_WHEELHOUSE_REQUIRED_DISTS = (
    "coding-pet",
    "pydantic",
    "typer",
    "pillow",
    "pyside6",
    "pyside6-addons",
    "pyside6-essentials",
    "shiboken6",
)
SAFE_PETDEX_SLUG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
CODING_PET_REQUIRED_WHEEL_SHARED_DATA = (
    "share/coding-pet/assets/sprites/theme-manifest.json",
    "share/coding-pet/assets/sprites/theme-registry.json",
    "share/coding-pet/assets/sprites/codex-default/idle.png",
    "share/coding-pet/assets/sprites/codex-default/thinking.png",
    "share/coding-pet/docs/operations/rhel8-setup.md",
    "share/coding-pet/docs/operations/offline-rhel8-wheelhouse.md",
    "share/coding-pet/docs/operations/codex-pet-packages.md",
    "share/coding-pet/requirements/constraints-rhel8.txt",
    "share/coding-pet/requirements/rhel8-runtime.txt",
    "share/coding-pet/requirements/rhel8-dev.txt",
    "share/coding-pet/systemd/coding-pet-daemon.service",
    "share/coding-pet/systemd/coding-pet-widget.service",
    "share/coding-pet/systemd/coding-pet.target",
    "share/coding-pet/systemd/coding-pet.service.env.example",
)

app = typer.Typer(help="Coding Pet command line interface")
daemon_app = typer.Typer(help="Run and manage the Coding Pet daemon")
widget_app = typer.Typer(help="Run and manage Coding Pet widgets")
admin_app = typer.Typer(help="Administrative and diagnostic commands")

app.add_typer(daemon_app, name="daemon")
app.add_typer(widget_app, name="widget")
app.add_typer(admin_app, name="admin")


@dataclass(frozen=True, slots=True)
class AcceptanceCheck:
    name: str
    ok: bool
    required: bool
    detail: str


@dataclass(frozen=True, slots=True)
class BackendEvidenceSpec:
    agent: AgentKind
    pane: str
    action: str
    reply_text: str | None
    expect_regex: str


@dataclass(frozen=True, slots=True)
class AgentHookFiles:
    hooks_dir: Path
    hook_script: Path
    claude_settings_snippet: Path
    opencode_plugin_snippet: Path


def _configured_transcript_store(config: AppConfig) -> TranscriptStore | None:
    if not config.transcript.enabled or config.transcript.db_path is None:
        return None
    return TranscriptStore(
        config.transcript.db_path,
        redact_secrets=config.transcript.redact_secrets,
        custom_redaction_patterns=config.transcript.custom_redaction_patterns,
    )


async def _serve_daemon_runtime(*, oneshot: bool) -> DaemonRuntime:
    config = load_config()
    transcript_store = _configured_transcript_store(config)
    runtime = DaemonRuntime(
        runtime_dir=config.runtime_dir,
        state_store=StateStore(config.state_file),
        tmux_config=config.tmux,
        transcript_store=transcript_store,
        state_detection_config=config.state_detection,
        completed_retention=timedelta(seconds=config.ui.show_completed_for_sec),
        process_stop_timeout=timedelta(seconds=config.process_stop_timeout_seconds),
    )
    ready_message = (
        "coding-pet daemon ready "
        f"runtime_dir={config.runtime_dir} "
        f"state_file={config.state_file} "
        f"socket_path={runtime.socket_path}"
    )
    typer.echo(ready_message)
    await runtime.serve(oneshot=oneshot)
    return runtime


@daemon_app.command("run")
def daemon_run() -> None:
    """Run the Coding Pet daemon."""
    oneshot = os.getenv("CODING_PET_DAEMON_ONESHOT") in {"1", "true", "yes", "on"}
    try:
        asyncio.run(_serve_daemon_runtime(oneshot=oneshot))
    except KeyboardInterrupt:
        typer.echo("coding-pet daemon stopped")


@daemon_app.command("monitor")
def daemon_monitor(
    agent: AgentKind = AGENT_OPTION,
    cmd: str = CMD_OPTION,
    workspace: str = WORKSPACE_OPTION,
    title: str | None = TITLE_OPTION,
    session_id: str | None = SESSION_ID_OPTION,
) -> None:
    """Launch and monitor a single agent command."""
    backend = AgentBackendRegistry.default().describe(agent)
    if not backend.available:
        typer.echo(f"backend {agent.value} is unavailable: {backend.reason}")
        raise typer.Exit(code=1)
    resolved_session_id = session_id or f"{agent.value}-{uuid.uuid4().hex[:8]}"
    app_instance = DaemonApp()
    asyncio.run(
        app_instance.monitor_command(
            agent_kind=agent,
            command=cmd,
            workspace=workspace,
            session_id=resolved_session_id,
            title=title,
        )
    )
    typer.echo(f"Monitored session {resolved_session_id}")


@daemon_app.command("discover-tmux")
def daemon_discover_tmux() -> None:
    """List tmux panes and show which panes match agent-session rules."""
    config = load_config()
    try:
        panes = TmuxClient().list_panes()
    except TmuxCommandError as exc:
        typer.echo(f"tmux discovery failed: {exc}")
        raise typer.Exit(code=1) from exc
    discovery = discover_agent_panes(panes, config=config.tmux)
    for matched in discovery.matched:
        pane = matched.pane
        typer.echo(
            f"{pane.pane_id}  {pane.session_name:<16}  "
            f"{matched.agent_kind.value:<11}  {pane.current_path:<24}  matched"
        )
    for ignored in discovery.ignored:
        pane = ignored.pane
        typer.echo(
            f"{pane.pane_id}  {pane.session_name:<16}  "
            f"{pane.current_command:<11}  {pane.current_path:<24}  ignored:{ignored.reason}"
        )


async def _monitor_tmux_once(*, pane: str, agent: str, title: str | None) -> str:
    config = load_config()
    client = TmuxClient()
    panes = client.list_panes()
    selected = next((info for info in panes if info.pane_id == pane), None)
    if selected is None:
        raise RuntimeError(f"tmux pane not found: {pane}")
    selected = replace(selected, title=title or selected.title)
    store = _configured_transcript_store(config)
    if store is not None:
        await store.initialize()

    registry = SessionRegistry()
    manager = MonitorManager(registry=registry)
    monitor = TmuxMonitorService(
        registry=registry,
        manager=manager,
        client=client,
        transcript_store=store,
        config=config.tmux,
        stalled_after=timedelta(seconds=config.state_detection.stalled_after_sec),
    )
    session_id = session_id_for_pane(selected)
    await monitor._upsert_matched_pane(
        MatchedTmuxPane(
            pane=selected,
            agent_kind=AgentKind(agent),
            reason="manual",
        )
    )
    status = await registry.get(session_id)
    if status is None:
        raise RuntimeError(f"tmux pane was not captured: {pane}")
    return (
        f"Captured tmux pane {pane} ({agent}) "
        f"session_id={status.session_id} state={status.state.value} "
        f"title={status.title} cwd={status.workspace}"
    )


@daemon_app.command("monitor-tmux")
def daemon_monitor_tmux(
    pane: str = PANE_OPTION,
    agent: AgentKind = AGENT_OPTION,
    title: str | None = TITLE_OPTION,
) -> None:
    """Capture and classify a manually selected tmux pane once."""
    try:
        result = asyncio.run(_monitor_tmux_once(pane=pane, agent=agent.value, title=title))
    except Exception as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc
    typer.echo(result)


async def _send_tmux_action_once(
    *,
    pane: str,
    agent: AgentKind,
    action: str,
    reply_text: str | None,
    title: str | None,
    press_enter: bool,
    client: TmuxClient | None = None,
) -> dict[str, object]:
    config = load_config()
    tmux_client = client or TmuxClient()
    panes = tmux_client.list_panes()
    selected = next((info for info in panes if info.pane_id == pane), None)
    if selected is None:
        raise RuntimeError(f"tmux pane not found: {pane}")
    selected = replace(selected, title=title or selected.title)
    store = _configured_transcript_store(config)
    if store is not None:
        await store.initialize()

    registry = SessionRegistry()
    manager = MonitorManager(registry=registry)
    monitor = TmuxMonitorService(
        registry=registry,
        manager=manager,
        client=tmux_client,
        transcript_store=store,
        config=config.tmux,
        stalled_after=timedelta(seconds=config.state_detection.stalled_after_sec),
    )
    session_id = session_id_for_pane(selected)
    await monitor._upsert_matched_pane(
        MatchedTmuxPane(
            pane=selected,
            agent_kind=agent,
            reason="manual",
        )
    )
    payload: dict[str, object] = {
        "type": "action_request",
        "session_id": session_id,
        "action": action,
        "press_enter": press_enter,
    }
    if reply_text is not None:
        payload["reply_text"] = reply_text
    try:
        request = SessionActionRequest.from_message(payload)
    except ValueError as exc:
        raise RuntimeError(f"invalid action request: {exc}") from exc
    return await manager.route_action(request)


async def _verify_tmux_action_once(
    *,
    pane: str,
    agent: AgentKind,
    action: str,
    reply_text: str | None,
    title: str | None,
    press_enter: bool,
    expect_regex: str | None,
    timeout_s: float,
    capture_lines: int,
) -> dict[str, object]:
    client = TmuxClient()
    before = client.capture_pane(pane, lines=capture_lines)
    action_result = await _send_tmux_action_once(
        pane=pane,
        agent=agent,
        action=action,
        reply_text=reply_text,
        title=title,
        press_enter=press_enter,
        client=client,
    )
    compiled = re.compile(expect_regex, re.MULTILINE | re.DOTALL) if expect_regex else None
    deadline = time.monotonic() + max(0.0, timeout_s)
    after = client.capture_pane(pane, lines=capture_lines)
    matched = compiled.search(after) is not None if compiled is not None else None
    while compiled is not None and not matched and time.monotonic() < deadline:
        await asyncio.sleep(0.1)
        after = client.capture_pane(pane, lines=capture_lines)
        matched = compiled.search(after) is not None
    output_changed = before != after
    action_ok = action_result.get("ok") is True
    verified = action_ok and (matched is not False)
    return {
        "schema_version": EVIDENCE_BUNDLE_SCHEMA_VERSION,
        "ok": verified,
        "profile": "target",
        "pane": pane,
        "agent": agent.value,
        "action": action_result.get("action", action),
        "capability": _target_backend_action_capability(action),
        "expected_regex": expect_regex,
        "matched_expected": matched,
        "output_changed": output_changed,
        "before_hash": snapshot_hash(before),
        "after_hash": snapshot_hash(after),
        "before_tail": _evidence_text_tail(before),
        "after_tail": _evidence_text_tail(after),
        "action_result": action_result,
        "detail": (
            "action delivered and expected output matched"
            if verified and matched is True
            else "action delivered; no expected output was configured"
            if verified
            else "action verification failed"
        ),
    }


def _backend_action_exception_report(
    *,
    pane: str,
    agent: AgentKind,
    action: str,
    expect_regex: str | None,
    exc: BaseException,
) -> dict[str, object]:
    error = redact_transcript_text(str(exc))
    return {
        "schema_version": EVIDENCE_BUNDLE_SCHEMA_VERSION,
        "ok": False,
        "profile": "target",
        "pane": pane,
        "agent": agent.value,
        "action": action,
        "capability": _target_backend_action_capability(action),
        "expected_regex": expect_regex,
        "matched_expected": False if expect_regex else None,
        "output_changed": False,
        "before_hash": None,
        "after_hash": None,
        "before_tail": "",
        "after_tail": "",
        "action_result": {
            "ok": False,
            "outcome": ActionOutcome.BACKEND_FAILED.value,
            "action": action,
            "reason": "exception",
            "detail": error,
        },
        "error": error,
        "detail": "action verification raised an exception",
    }


def _text_tail(text: str, *, limit: int = 4000) -> str:
    if len(text) <= limit:
        return text
    return text[-limit:]


def _evidence_text_tail(text: str, *, limit: int = 4000) -> str:
    return redact_transcript_text(_text_tail(text, limit=limit))


@daemon_app.command("send-tmux-action")
def daemon_send_tmux_action(
    pane: str = PANE_OPTION,
    agent: AgentKind = AGENT_OPTION,
    action: str = ACTION_OPTION,
    reply_text: str | None = REPLY_TEXT_OPTION,
    title: str | None = TITLE_OPTION,
    no_enter: bool = NO_ENTER_OPTION,
) -> None:
    """Send one action to a manually selected tmux pane using daemon control logic."""
    try:
        result = asyncio.run(
            _send_tmux_action_once(
                pane=pane,
                agent=agent,
                action=action,
                reply_text=reply_text,
                title=title,
                press_enter=not no_enter,
            )
        )
    except Exception as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc

    typer.echo(f"session_id={result.get('session_id', '')}")
    typer.echo(f"agent={agent.value}")
    typer.echo(f"sent_action={result.get('action', action)}")
    typer.echo(f"ok={str(result.get('ok') is True).lower()}")
    if "reason" in result:
        typer.echo(f"reason={result['reason']}")
    if "detail" in result:
        typer.echo(f"detail={result['detail']}")
    if result.get("ok") is not True:
        raise typer.Exit(code=1)


@daemon_app.command("verify-tmux-action")
def daemon_verify_tmux_action(
    pane: str = PANE_OPTION,
    agent: AgentKind = AGENT_OPTION,
    action: str = ACTION_OPTION,
    reply_text: str | None = REPLY_TEXT_OPTION,
    title: str | None = TITLE_OPTION,
    no_enter: bool = NO_ENTER_OPTION,
    expect_regex: str | None = EXPECT_REGEX_OPTION,
    timeout_s: float = TMUX_CONTROL_CHECK_TIMEOUT_OPTION,
    capture_lines: int = CAPTURE_LINES_OPTION,
    json_out: Path | None = JSON_OUT_OPTION,
) -> None:
    """Send one tmux action and capture before/after evidence."""
    try:
        report = asyncio.run(
            _verify_tmux_action_once(
                pane=pane,
                agent=agent,
                action=action,
                reply_text=reply_text,
                title=title,
                press_enter=not no_enter,
                expect_regex=expect_regex,
                timeout_s=timeout_s,
                capture_lines=capture_lines,
            )
        )
    except Exception as exc:
        if json_out is not None:
            _write_json_report(
                json_out,
                _backend_action_exception_report(
                    pane=pane,
                    agent=agent,
                    action=action,
                    expect_regex=expect_regex,
                    exc=exc,
                ),
            )
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc

    if json_out is not None:
        _write_json_report(json_out, report)
    typer.echo(f"pane={report['pane']}")
    typer.echo(f"agent={report['agent']}")
    typer.echo(f"sent_action={report['action']}")
    typer.echo(f"ok={_bool_text(report['ok'] is True)}")
    typer.echo(f"output_changed={_bool_text(report['output_changed'] is True)}")
    if report["matched_expected"] is not None:
        typer.echo(f"matched_expected={_bool_text(report['matched_expected'] is True)}")
    typer.echo(f"before_hash={report['before_hash']}")
    typer.echo(f"after_hash={report['after_hash']}")
    typer.echo(f"detail={report['detail']}")
    if report["ok"] is not True:
        raise typer.Exit(code=1)


async def _send_daemon_action_once(
    *,
    socket_path: Path,
    session_id: str,
    action: str,
    reply_text: str | None,
    press_enter: bool,
) -> dict[str, object]:
    payload_action = "send_without_enter" if action == "send_reply" and not press_enter else action
    payload: dict[str, object] = {
        "type": "action_request",
        "session_id": session_id,
        "action": payload_action,
        "press_enter": press_enter,
    }
    if reply_text is not None:
        payload["reply_text"] = reply_text
    try:
        request = SessionActionRequest.from_message(payload)
    except ValueError as exc:
        raise RuntimeError(f"invalid action request: {exc}") from exc

    request_payload: dict[str, object] = {
        "type": "action_request",
        "session_id": request.session_id,
        "action": request.action,
    }
    if request.reply_text is not None:
        request_payload["reply_text"] = request.reply_text
    if request.action in {"send_reply", "send_without_enter"}:
        request_payload["press_enter"] = request.press_enter
    if request.state_override is not None:
        request_payload["state_override"] = request.state_override.value

    client = IpcClient(socket_path)
    await client.connect()
    try:
        await asyncio.wait_for(client.read_message(), timeout=5)
        await client.send(request_payload)
        while True:
            message = await asyncio.wait_for(client.read_message(), timeout=5)
            if (
                message.get("type") == "action_result"
                and message.get("session_id") == request.session_id
                and message.get("action") == request.action
            ):
                return dict(message)
    finally:
        await client.close()


async def _send_hook_event_once(
    *,
    socket_path: Path,
    agent: AgentKind,
    event: str,
    session_id: str,
    workspace: str,
    title: str | None,
    summary: str | None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "type": "hook_event",
        "agent": agent.value,
        "event": event,
        "session_id": session_id,
        "workspace": workspace,
    }
    if title is not None:
        payload["title"] = title
    if summary is not None:
        payload["summary"] = summary

    client = IpcClient(socket_path)
    await client.connect()
    try:
        await asyncio.wait_for(client.read_message(), timeout=5)
        await client.send(payload)
        while True:
            message = await asyncio.wait_for(client.read_message(), timeout=5)
            if message.get("type") == "hook_event_result":
                return dict(message)
    finally:
        await client.close()


@daemon_app.command("send-action")
def daemon_send_action(
    session_id: str = typer.Option(..., "--session-id"),
    action: str = ACTION_OPTION,
    reply_text: str | None = REPLY_TEXT_OPTION,
    no_enter: bool = NO_ENTER_OPTION,
    socket: Path | None = SOCKET_OPTION,
) -> None:
    """Send one action_request to a running daemon over IPC."""
    config = load_config()
    socket_path = socket or default_socket_path(config.runtime_dir)
    try:
        result = asyncio.run(
            _send_daemon_action_once(
                socket_path=socket_path,
                session_id=session_id,
                action=action,
                reply_text=reply_text,
                press_enter=not no_enter,
            )
        )
    except Exception as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc

    typer.echo(f"session_id={result.get('session_id', '')}")
    typer.echo(f"sent_action={result.get('action', action)}")
    typer.echo(f"ok={str(result.get('ok') is True).lower()}")
    if "reason" in result:
        typer.echo(f"reason={result['reason']}")
    if "detail" in result:
        typer.echo(f"detail={result['detail']}")
    if result.get("ok") is not True:
        raise typer.Exit(code=1)


@daemon_app.command("hook-event")
def daemon_hook_event(
    agent: AgentKind = AGENT_OPTION,
    event: str = EVENT_OPTION,
    session_id: str = REQUIRED_SESSION_ID_OPTION,
    workspace: Path | None = OPTIONAL_WORKSPACE_OPTION,
    title: str | None = TITLE_OPTION,
    summary: str | None = SUMMARY_OPTION,
    socket: Path | None = SOCKET_OPTION,
) -> None:
    """Send one agent hook event to a running daemon over IPC."""
    config = load_config()
    socket_path = socket or default_socket_path(config.runtime_dir)
    resolved_workspace = str(workspace or Path.cwd())
    try:
        result = asyncio.run(
            _send_hook_event_once(
                socket_path=socket_path,
                agent=agent,
                event=event,
                session_id=session_id,
                workspace=resolved_workspace,
                title=title,
                summary=summary,
            )
        )
    except Exception as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc

    typer.echo(f"hook_event={'ok' if result.get('ok') is True else 'failed'}")
    if result.get("session_id") is not None:
        typer.echo(f"session_id={result['session_id']}")
    if result.get("state") is not None:
        typer.echo(f"state={result['state']}")
    if "reason" in result:
        typer.echo(f"reason={result['reason']}")
    if "detail" in result:
        typer.echo(f"detail={result['detail']}")
    if result.get("ok") is not True:
        raise typer.Exit(code=1)


@widget_app.command("run")
def widget_run() -> None:
    """Run the Coding Pet widget layer."""
    config = load_config()
    from coding_pet.gui.app import CodingPetWidgetApp
    from coding_pet.models import AgentKind, AttentionState, SessionStatus

    socket_path = default_socket_path(config.runtime_dir)
    app = CodingPetWidgetApp(
        socket_path=socket_path,
        state_store=StateStore(config.state_file),
    )
    live_mode = socket_path.exists()
    widget_status = (
        "coding-pet widget "
        f"runtime_dir={config.runtime_dir} "
        f"state_file={config.state_file} "
        f"live_mode={str(live_mode).lower()}"
    )
    typer.echo(widget_status)
    try:
        qt_app = app.ensure_app()
    except Exception:
        typer.echo("PySide6 GUI runtime is unavailable in this environment.")
        return

    async def prepare() -> None:
        await app.load_snapshot()
        if app.socket_path is not None and app.socket_path.exists():
            await app.connect_to_daemon()
            return
        demo = SessionStatus(
            session_id="demo",
            agent_kind=AgentKind.CLAUDE_CODE,
            title="Demo Session",
            workspace=str(Path.cwd()),
            state=AttentionState.NEEDS_PERMISSION,
            summary="Waiting for approval to apply changes.",
            last_event_at=datetime.now(UTC),
        )
        app.show_sessions([demo])

    asyncio.run(prepare())
    raise typer.Exit(code=qt_app.exec())


def _path_health(path: Path) -> str:
    exists = path.exists()
    parent = path if path.is_dir() else path.parent
    if parent.exists():
        writable_parent = os.access(parent, os.W_OK)
    else:
        writable_parent = os.access(parent.parent, os.W_OK)
    return f"{'exists' if exists else 'missing'},writable_parent={str(writable_parent).lower()}"


def _gui_runtime_status() -> str:
    return gui_runtime_status()


def _bool_text(value: bool) -> str:
    return str(value).lower()


def _write_json_report(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _versioned_evidence_report(payload: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": EVIDENCE_BUNDLE_SCHEMA_VERSION,
        **payload,
        "generated_at": datetime.now(UTC).isoformat(),
    }


def _stamp_evidence_profile(payload: dict[str, object], profile: str) -> dict[str, object]:
    payload["profile"] = profile
    return payload


def _normalize_distribution_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _wheel_distribution_name(path: Path) -> str | None:
    if path.suffix != ".whl":
        return None
    stem = path.name[:-4]
    parts = stem.split("-")
    if len(parts) < 5:
        return None
    return _normalize_distribution_name(parts[0])


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _manylinux_versions(filename: str) -> list[tuple[int, int]]:
    versions: list[tuple[int, int]] = []
    for major, minor in re.findall(r"manylinux_(\d+)_(\d+)", filename):
        versions.append((int(major), int(minor)))
    if "manylinux2014" in filename:
        versions.append((2, 17))
    return versions


def _wheel_python_abi_tags(filename: str) -> tuple[list[str], list[str]]:
    if not filename.endswith(".whl"):
        return ([], [])
    parts = filename[:-4].split("-")
    if len(parts) < 5:
        return ([], [])
    return (parts[-3].split("."), parts[-2].split("."))


def _wheel_platform_tags(filename: str) -> list[str]:
    if not filename.endswith(".whl"):
        return []
    parts = filename[:-4].split("-")
    if len(parts) < 5:
        return []
    return parts[-1].split(".")


def _cpython_tag_version(tag: str) -> tuple[int, int] | None:
    match = re.fullmatch(r"cp(\d)(\d+)", tag)
    if match is None:
        return None
    return (int(match.group(1)), int(match.group(2)))


def _wheel_python_tags_compatible_with_target(filename: str) -> bool:
    python_tags, abi_tags = _wheel_python_abi_tags(filename)
    if not python_tags:
        return True
    target = (3, 12)
    for tag in python_tags:
        if tag in {"py3", "py312", "cp312"}:
            return True
        version = _cpython_tag_version(tag)
        if version is not None and version[0] == 3 and version <= target and "abi3" in abi_tags:
            return True
    return False


def _incompatible_python_wheels(wheels: list[Path]) -> list[str]:
    return [
        wheel.name for wheel in wheels if not _wheel_python_tags_compatible_with_target(wheel.name)
    ]


def _wheel_platform_tags_compatible_with_rhel8_x86_64(filename: str) -> bool:
    platform_tags = _wheel_platform_tags(filename)
    if not platform_tags:
        return True
    for tag in platform_tags:
        if tag == "any":
            return True
        if tag.startswith(("manylinux", "linux")) and tag.endswith("_x86_64"):
            return True
    return False


def _incompatible_rhel8_wheels(wheels: list[Path]) -> list[str]:
    incompatible: list[str] = []
    for wheel in wheels:
        if not _wheel_platform_tags_compatible_with_rhel8_x86_64(wheel.name):
            incompatible.append(wheel.name)
            continue
        for major, minor in _manylinux_versions(wheel.name):
            if major > 2 or (major == 2 and minor > 28):
                incompatible.append(wheel.name)
                break
    return incompatible


def _coding_pet_wheel_content_report(wheels: list[Path]) -> dict[str, object]:
    coding_pet_wheels = [
        wheel for wheel in wheels if _wheel_distribution_name(wheel) == "coding-pet"
    ]
    if not coding_pet_wheels:
        return {
            "ok": False,
            "wheel": None,
            "missing_shared_data": list(CODING_PET_REQUIRED_WHEEL_SHARED_DATA),
            "detail": "coding-pet wheel missing",
        }
    wheel = coding_pet_wheels[-1]
    try:
        with zipfile.ZipFile(wheel) as archive:
            names = archive.namelist()
    except zipfile.BadZipFile:
        return {
            "ok": False,
            "wheel": str(wheel),
            "missing_shared_data": list(CODING_PET_REQUIRED_WHEEL_SHARED_DATA),
            "detail": "coding-pet wheel is not a valid zip archive",
        }
    missing = [
        suffix
        for suffix in CODING_PET_REQUIRED_WHEEL_SHARED_DATA
        if not any(name.endswith(suffix) for name in names)
    ]
    return {
        "ok": not missing,
        "wheel": str(wheel),
        "required_shared_data": list(CODING_PET_REQUIRED_WHEEL_SHARED_DATA),
        "missing_shared_data": missing,
        "detail": "coding-pet wheel contains required shared data"
        if not missing
        else "coding-pet wheel missing required shared data",
    }


def _wheelhouse_install_smoke_report(
    *,
    wheelhouse: Path,
    install_target: str,
    timeout_s: float,
) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="coding-pet-wheelhouse-") as temp_dir:
        venv_dir = Path(temp_dir) / "venv"
        venv_result = subprocess.run(
            [sys.executable, "-m", "venv", str(venv_dir)],
            capture_output=True,
            check=False,
            text=True,
            timeout=timeout_s,
        )
        if venv_result.returncode != 0:
            return {
                "ok": False,
                "skipped": False,
                "stage": "venv",
                "returncode": venv_result.returncode,
                "stdout": venv_result.stdout,
                "stderr": venv_result.stderr,
                "detail": "temporary venv creation failed",
            }

        python_bin = venv_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        install_command = [
            str(python_bin),
            "-m",
            "pip",
            "install",
            "--no-index",
            "--find-links",
            str(wheelhouse),
            install_target,
        ]
        install_result = subprocess.run(
            install_command,
            capture_output=True,
            check=False,
            text=True,
            timeout=timeout_s,
        )
        if install_result.returncode != 0:
            return {
                "ok": False,
                "skipped": False,
                "stage": "install",
                "command": install_command,
                "returncode": install_result.returncode,
                "stdout": install_result.stdout,
                "stderr": install_result.stderr,
                "detail": "offline wheelhouse install failed",
            }

        import_command = [
            str(python_bin),
            "-c",
            (
                "import coding_pet, pydantic, typer, PIL; "
                "from PySide6 import QtCore; "
                "from coding_pet.gui.theme import WidgetTheme, load_manifest_for_theme; "
                "from coding_pet.cli import _systemd_unit_paths; "
                "manifest = load_manifest_for_theme(WidgetTheme.CODEX_DEFAULT); "
                "assert manifest.name == 'codex-default'; "
                "assert all(path.exists() for path in _systemd_unit_paths())"
            ),
        ]
        import_result = subprocess.run(
            import_command,
            capture_output=True,
            check=False,
            text=True,
            timeout=timeout_s,
        )
        return {
            "ok": import_result.returncode == 0,
            "skipped": False,
            "stage": "import",
            "command": install_command,
            "import_command": import_command,
            "returncode": import_result.returncode,
            "stdout": import_result.stdout,
            "stderr": import_result.stderr,
            "detail": "offline wheelhouse install smoke passed"
            if import_result.returncode == 0
            else "offline wheelhouse import smoke failed",
        }


def _wheelhouse_check_report(
    *,
    wheelhouse: Path,
    install_target: str,
    skip_install_smoke: bool,
    timeout_s: float,
) -> dict[str, object]:
    if not wheelhouse.exists() or not wheelhouse.is_dir():
        return _versioned_evidence_report(
            {
                "ok": False,
                "wheelhouse": str(wheelhouse),
                "errors": ["wheelhouse directory is missing"],
            }
        )

    wheels = sorted(wheelhouse.glob("*.whl"))
    wheel_records = [
        {
            "filename": wheel.name,
            "distribution": _wheel_distribution_name(wheel),
            "sha256": _file_sha256(wheel),
            "size_bytes": wheel.stat().st_size,
        }
        for wheel in wheels
    ]
    distributions = {
        distribution
        for distribution in (_wheel_distribution_name(wheel) for wheel in wheels)
        if distribution is not None
    }
    required = list(RHEL8_WHEELHOUSE_REQUIRED_DISTS)
    missing = [name for name in required if name not in distributions]
    incompatible = _incompatible_rhel8_wheels(wheels)
    incompatible_python = _incompatible_python_wheels(wheels)
    coding_pet_wheel = _coding_pet_wheel_content_report(wheels)
    errors: list[str] = []
    if missing:
        errors.append("missing required wheels")
    if incompatible:
        errors.append("wheel platform tag is incompatible with RHEL 8.10 x86_64 target")
    if incompatible_python:
        errors.append("wheel python tag is incompatible with Python 3.12 target")
    if coding_pet_wheel.get("ok") is not True:
        errors.append(str(coding_pet_wheel.get("detail")))

    if skip_install_smoke:
        install_smoke: dict[str, object] = {
            "ok": True,
            "skipped": True,
            "detail": "install smoke skipped",
        }
    elif not errors:
        install_smoke = _wheelhouse_install_smoke_report(
            wheelhouse=wheelhouse,
            install_target=install_target,
            timeout_s=timeout_s,
        )
        if install_smoke.get("ok") is not True:
            errors.append("offline install smoke failed")
    else:
        install_smoke = {
            "ok": False,
            "skipped": True,
            "detail": "install smoke skipped because static wheelhouse checks failed",
        }

    return _versioned_evidence_report(
        {
            "ok": not errors,
            "wheelhouse": str(wheelhouse),
            "required_distributions": required,
            "present_distributions": sorted(distributions),
            "missing_distributions": missing,
            "incompatible_platform_wheels": incompatible,
            "incompatible_python_wheels": incompatible_python,
            "coding_pet_wheel": coding_pet_wheel,
            "wheels": wheel_records,
            "install_target": install_target,
            "install_smoke": install_smoke,
            "errors": errors,
        }
    )


def _wheelhouse_evidence_report(
    *,
    wheelhouse: Path | None,
    required: bool,
    install_target: str,
    skip_install_smoke: bool,
    timeout_s: float,
) -> dict[str, object]:
    if wheelhouse is None:
        return _versioned_evidence_report(
            {
                "ok": False,
                "required": required,
                "skipped": True,
                "detail": "wheelhouse not provided",
            }
        )
    report = _wheelhouse_check_report(
        wheelhouse=wheelhouse,
        install_target=install_target,
        skip_install_smoke=skip_install_smoke,
        timeout_s=timeout_s,
    )
    report["required"] = required
    report["skipped"] = False
    return report


def _version_tuple(value: str) -> tuple[int, ...]:
    parts: list[int] = []
    for part in value.split("."):
        if not part.isdigit():
            break
        parts.append(int(part))
    return tuple(parts)


def _version_at_least(value: str, minimum: str) -> bool:
    parsed = _version_tuple(value)
    required = _version_tuple(minimum)
    if not parsed:
        return False
    length = max(len(parsed), len(required))
    return parsed + (0,) * (length - len(parsed)) >= required + (0,) * (length - len(required))


def _module_available(module: str) -> bool:
    return importlib.util.find_spec(module) is not None


def _acceptance_profile(profile: str) -> str:
    normalized = profile.strip().lower()
    if normalized not in {"current", "target"}:
        raise ValueError("profile must be current or target")
    return normalized


def _rhel_release_text() -> str | None:
    if not REDHAT_RELEASE_PATH.exists():
        return None
    return REDHAT_RELEASE_PATH.read_text("utf-8").strip()


def _path_writable_parent(path: Path) -> bool:
    parent = path if path.exists() and path.is_dir() else path.parent
    probe = parent
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    return os.access(probe, os.W_OK)


def _theme_acceptance_detail() -> tuple[bool, str]:
    assets_root = default_assets_root()
    theme_name = configured_theme()
    manifest = load_manifest_for_theme(theme_name, assets_root=assets_root)
    asset_root = manifest.asset_root or assets_root
    missing = validate_theme_assets(manifest, asset_root)
    if missing:
        missing_summary = ",".join(path.as_posix() for path in missing)
        return False, f"{manifest.name}:missing={missing_summary}"
    if manifest.spritesheet is not None and manifest.asset_root is not None:
        package = validate_codex_pet_package(manifest.asset_root)
        atlas = f"{package.image_size[0]}x{package.image_size[1]}"
        return True, f"{package.theme_id}:codex_pet:atlas={atlas}"
    return True, f"{manifest.name}:coding_pet"


def _build_acceptance_checks(profile: str) -> tuple[str, list[AcceptanceCheck]]:
    normalized = _acceptance_profile(profile)
    target = normalized == "target"
    config = load_config()
    checks: list[AcceptanceCheck] = []

    py_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    checks.append(
        AcceptanceCheck(
            "python",
            sys.version_info.major == 3 and sys.version_info.minor == 12,
            True,
            py_version,
        )
    )

    checks.append(
        AcceptanceCheck(
            "linux",
            platform.system() == "Linux",
            target,
            platform.platform(),
        )
    )

    libc_name, libc_version = platform.libc_ver()
    glibc_ok = libc_name == "glibc" and _version_at_least(libc_version, "2.28")
    checks.append(
        AcceptanceCheck(
            "glibc",
            glibc_ok,
            target,
            f"{libc_name or 'unknown'} {libc_version or 'unknown'}; need glibc>=2.28",
        )
    )

    release_text = _rhel_release_text()
    rhel_ok = (
        release_text is not None
        and "Red Hat Enterprise Linux" in release_text
        and "8.10" in release_text
    )
    checks.append(
        AcceptanceCheck(
            "rhel_8_10",
            rhel_ok,
            target,
            release_text or f"{REDHAT_RELEASE_PATH} missing",
        )
    )

    for module, package in (
        ("pydantic", "pydantic"),
        ("typer", "typer"),
        ("PIL", "Pillow"),
    ):
        checks.append(
            AcceptanceCheck(
                f"dependency_{package.lower()}",
                _module_available(module),
                True,
                package,
            )
        )

    gui_status = _gui_runtime_status()
    checks.append(
        AcceptanceCheck(
            "gui_runtime",
            gui_status == "available",
            target,
            gui_status,
        )
    )

    tmux_path = shutil.which("tmux")
    checks.append(
        AcceptanceCheck(
            "tmux",
            tmux_path is not None,
            target,
            tmux_path or "unavailable",
        )
    )

    notify_path = shutil.which("notify-send")
    checks.append(
        AcceptanceCheck(
            "notify_send",
            notify_path is not None,
            False,
            notify_path or "unavailable",
        )
    )

    try:
        theme_ok, theme_detail = _theme_acceptance_detail()
    except Exception as exc:
        theme_ok, theme_detail = False, str(exc)
    checks.append(AcceptanceCheck("theme", theme_ok, True, theme_detail))

    for name, path in (
        ("config_dir", config.config_dir),
        ("state_dir", config.state_dir),
        ("runtime_dir", config.runtime_dir),
        ("log_dir", config.log_dir),
        ("state_file", config.state_file),
    ):
        checks.append(
            AcceptanceCheck(
                f"path_{name}",
                _path_writable_parent(path),
                True,
                str(path),
            )
        )

    required_agents = TARGET_REQUIRED_AGENTS if target else ()
    for backend in AgentBackendRegistry.default().list_all():
        required = backend.agent_kind in required_agents
        checks.append(
            AcceptanceCheck(
                f"backend_{backend.agent_kind.value}",
                backend.available,
                required,
                backend.reason,
            )
        )

    return normalized, checks


def _acceptance_report(profile: str, checks: list[AcceptanceCheck]) -> dict[str, object]:
    failed_required = [check.name for check in checks if check.required and not check.ok]
    return {
        "schema_version": EVIDENCE_BUNDLE_SCHEMA_VERSION,
        "ok": not failed_required,
        "profile": profile,
        "generated_at": datetime.now(UTC).isoformat(),
        "failed_required": failed_required,
        "checks": [
            {
                "name": check.name,
                "ok": check.ok,
                "required": check.required,
                "detail": check.detail,
            }
            for check in checks
        ],
    }


def _environment_evidence_report(profile: str) -> dict[str, object]:
    config = load_config()
    libc_name, libc_version = platform.libc_ver()
    try:
        theme_ok, theme_detail = _theme_acceptance_detail()
    except Exception as exc:
        theme_ok, theme_detail = False, str(exc)
    registry = AgentBackendRegistry.default()
    return {
        "schema_version": EVIDENCE_BUNDLE_SCHEMA_VERSION,
        "profile": profile,
        "generated_at": datetime.now(UTC).isoformat(),
        "python": {
            "version": (
                f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
            ),
            "executable": sys.executable,
        },
        "platform": {
            "system": platform.system(),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "release": platform.release(),
        },
        "libc": {
            "name": libc_name or "unknown",
            "version": libc_version or "unknown",
        },
        "redhat_release": _rhel_release_text(),
        "gui_runtime": _gui_runtime_status(),
        "tmux_binary": shutil.which("tmux"),
        "notify_send": shutil.which("notify-send"),
        "paths": {
            "config_dir": str(config.config_dir),
            "state_dir": str(config.state_dir),
            "runtime_dir": str(config.runtime_dir),
            "state_file": str(config.state_file),
            "log_dir": str(config.log_dir),
            "transcript_db": str(config.transcript.db_path),
        },
        "transcript": {
            "enabled": config.transcript.enabled,
            "backend": config.transcript.backend,
            "db_path": str(config.transcript.db_path),
            "max_events_per_session": config.transcript.max_events_per_session,
            "redact_secrets": config.transcript.redact_secrets,
            "custom_redaction_pattern_count": len(config.transcript.custom_redaction_patterns),
        },
        "theme": {
            "name": configured_theme(),
            "ok": theme_ok,
            "detail": theme_detail,
        },
        "backends": [
            {
                "agent_kind": backend.agent_kind.value,
                "available": backend.available,
                "binary_name": backend.binary_name,
                "binary_path": backend.binary_path,
                "reason": backend.reason,
                "control_messages": {
                    "approve": backend.adapter.control_message(action="approve"),
                    "reject": backend.adapter.control_message(action="reject"),
                },
            }
            for backend in registry.list_all()
        ],
    }


def _tmux_control_evidence_report(
    *,
    required: bool,
    skip: bool,
    timeout_s: float,
) -> dict[str, object]:
    if skip:
        return _versioned_evidence_report(
            {
                "ok": False,
                "required": required,
                "skipped": True,
                "detail": "tmux control check skipped",
            }
        )
    if shutil.which("tmux") is None:
        return _versioned_evidence_report(
            {
                "ok": False,
                "required": required,
                "skipped": False,
                "detail": "tmux unavailable",
            }
        )
    try:
        result = run_tmux_control_check(timeout_s=timeout_s)
    except Exception as exc:
        return _versioned_evidence_report(
            {
                "ok": False,
                "required": required,
                "skipped": False,
                "detail": str(exc),
            }
        )
    report = result.as_report()
    report["required"] = required
    report["skipped"] = False
    return _versioned_evidence_report(report)


def _systemd_unit_dir_candidates() -> list[Path]:
    source_root = Path(__file__).resolve().parents[2]
    return [
        source_root / "packaging" / "systemd",
        Path(sys.prefix) / "share" / "coding-pet" / "systemd",
    ]


def _systemd_unit_paths() -> list[Path]:
    for unit_dir in _systemd_unit_dir_candidates():
        paths = [unit_dir / name for name in SYSTEMD_UNIT_NAMES]
        if all(path.exists() for path in paths):
            return paths
    first = _systemd_unit_dir_candidates()[0]
    return [first / name for name in SYSTEMD_UNIT_NAMES]


def _systemd_unit_evidence_report(
    *,
    required: bool,
    skip: bool,
    timeout_s: float,
) -> dict[str, object]:
    unit_paths = _systemd_unit_paths()
    if skip:
        return _versioned_evidence_report(
            {
                "ok": False,
                "required": required,
                "skipped": True,
                "units": [str(path) for path in unit_paths],
                "detail": "systemd unit verification skipped",
            }
        )

    binary = shutil.which("systemd-analyze")
    if binary is None:
        return _versioned_evidence_report(
            {
                "ok": False,
                "required": required,
                "skipped": False,
                "units": [str(path) for path in unit_paths],
                "detail": "systemd-analyze unavailable",
            }
        )

    missing = [path for path in unit_paths if not path.exists()]
    if missing:
        return _versioned_evidence_report(
            {
                "ok": False,
                "required": required,
                "skipped": False,
                "units": [str(path) for path in unit_paths],
                "missing_units": [str(path) for path in missing],
                "detail": "missing systemd unit files",
            }
        )

    command = [binary, "--user", "verify", *(str(path) for path in unit_paths)]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            check=False,
            text=True,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired:
        return _versioned_evidence_report(
            {
                "ok": False,
                "required": required,
                "skipped": False,
                "units": [str(path) for path in unit_paths],
                "command": command,
                "detail": f"systemd-analyze verify timed out after {timeout_s:g}s",
            }
        )
    except OSError as exc:
        return _versioned_evidence_report(
            {
                "ok": False,
                "required": required,
                "skipped": False,
                "units": [str(path) for path in unit_paths],
                "command": command,
                "detail": str(exc),
            }
        )

    return _versioned_evidence_report(
        {
            "ok": completed.returncode == 0,
            "required": required,
            "skipped": False,
            "units": [str(path) for path in unit_paths],
            "command": command,
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "detail": "systemd user units verified"
            if completed.returncode == 0
            else "systemd user unit verification failed",
        }
    )


def _systemd_session_environment_report() -> dict[str, object]:
    display = os.environ.get("DISPLAY")
    wayland_display = os.environ.get("WAYLAND_DISPLAY")
    xdg_runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
    dbus_session_bus = os.environ.get("DBUS_SESSION_BUS_ADDRESS")
    return {
        "has_display": bool(display),
        "has_wayland_display": bool(wayland_display),
        "has_xdg_runtime_dir": bool(xdg_runtime_dir),
        "has_dbus_session_bus": bool(dbus_session_bus),
        "DISPLAY": display,
        "WAYLAND_DISPLAY": wayland_display,
        "XDG_RUNTIME_DIR": xdg_runtime_dir,
        "DBUS_SESSION_BUS_ADDRESS": dbus_session_bus,
    }


def _run_systemctl_user(
    binary: str,
    args: list[str],
    *,
    timeout_s: float,
) -> dict[str, object]:
    command = [binary, "--user", *args]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            check=False,
            text=True,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired:
        return {
            "command": command,
            "returncode": None,
            "stdout": "",
            "stderr": "",
            "timed_out": True,
        }
    except OSError as exc:
        return {
            "command": command,
            "returncode": None,
            "stdout": "",
            "stderr": str(exc),
            "timed_out": False,
        }
    return {
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "timed_out": False,
    }


def _first_output_line(result: dict[str, object]) -> str:
    stdout = result.get("stdout")
    if not isinstance(stdout, str):
        return ""
    return stdout.strip().splitlines()[0] if stdout.strip() else ""


def _systemd_runtime_evidence_report(
    *,
    required: bool,
    timeout_s: float,
) -> dict[str, object]:
    binary = shutil.which("systemctl")
    session_environment = _systemd_session_environment_report()
    if binary is None:
        return _versioned_evidence_report(
            {
                "ok": False,
                "required": required,
                "skipped": False,
                "systemctl": None,
                "session_environment": session_environment,
                "detail": "systemctl unavailable",
                "errors": ["systemctl unavailable"],
            }
        )

    errors: list[str] = []
    if required:
        if session_environment["has_xdg_runtime_dir"] is not True:
            errors.append("XDG_RUNTIME_DIR is required for systemd user services")
        if (
            session_environment["has_display"] is not True
            and session_environment["has_wayland_display"] is not True
        ):
            errors.append("DISPLAY or WAYLAND_DISPLAY is required for the widget service")
        if session_environment["has_dbus_session_bus"] is not True:
            errors.append("DBUS_SESSION_BUS_ADDRESS is required for desktop user services")

    user_manager = _run_systemctl_user(binary, ["status"], timeout_s=timeout_s)
    user_manager_ok = user_manager.get("returncode") == 0
    if not user_manager_ok:
        errors.append("systemd user manager is not reachable")

    enabled_raw = _run_systemctl_user(
        binary,
        ["is-enabled", "coding-pet.target"],
        timeout_s=timeout_s,
    )
    enabled_state = _first_output_line(enabled_raw)
    enabled_ok = enabled_raw.get("returncode") == 0 and enabled_state == "enabled"
    if not enabled_ok:
        errors.append("coding-pet.target is not enabled")

    units: list[dict[str, object]] = []
    for unit in SYSTEMD_RUNTIME_UNIT_NAMES:
        active_raw = _run_systemctl_user(binary, ["is-active", unit], timeout_s=timeout_s)
        active_state = _first_output_line(active_raw)
        active_ok = active_raw.get("returncode") == 0 and active_state == "active"
        if not active_ok:
            errors.append(f"unit {unit} is not active")
        units.append(
            {
                "unit": unit,
                "state": active_state or "unknown",
                "ok": active_ok,
                "returncode": active_raw.get("returncode"),
                "command": active_raw.get("command"),
                "stderr": active_raw.get("stderr"),
            }
        )

    return _versioned_evidence_report(
        {
            "ok": not errors,
            "required": required,
            "skipped": False,
            "systemctl": binary,
            "session_environment": session_environment,
            "user_manager": {
                "ok": user_manager_ok,
                "returncode": user_manager.get("returncode"),
                "command": user_manager.get("command"),
                "stderr": user_manager.get("stderr"),
            },
            "target_enabled": {
                "unit": "coding-pet.target",
                "state": enabled_state or "unknown",
                "ok": enabled_ok,
                "returncode": enabled_raw.get("returncode"),
                "command": enabled_raw.get("command"),
                "stderr": enabled_raw.get("stderr"),
            },
            "units": units,
            "errors": errors,
            "detail": "systemd user runtime verified"
            if not errors
            else "systemd user runtime verification failed",
        }
    )


def _widget_smoke_evidence_report(*, required: bool) -> dict[str, object]:
    gui_status = _gui_runtime_status()
    theme_name = configured_theme()
    errors: list[str] = []
    try:
        theme_ok, theme_detail = _theme_acceptance_detail()
    except Exception as exc:  # noqa: BLE001
        theme_ok, theme_detail = False, str(exc)

    if not theme_ok:
        errors.append("theme assets are not valid")

    shell_created = False
    qt_widget_created = False
    qt_app_created = False
    qt_probe: dict[str, object] = {"attempted": False}
    sprite_asset: str | None = None
    presentation: dict[str, object] | None = None
    available_actions: list[str] = []
    action_surfaces: dict[str, dict[str, object]] = {}

    def surface_for(
        *,
        label: str,
        state: AttentionState,
        summary: str,
    ) -> dict[str, object]:
        status = SessionStatus(
            session_id=f"widget-smoke-{label}",
            agent_kind=AgentKind.CLAUDE_CODE,
            title=f"Widget Smoke {label}",
            workspace=str(Path.cwd()),
            state=state,
            summary=summary,
            last_event_at=datetime.now(UTC),
            supported_actions=["send_reply", "send_without_enter", "approve", "reject"],
        )
        shell = CodingPetWidgetShell(status=status, theme=theme_name)
        widget_presentation = shell.presentation()
        sprite = shell.sprite_asset_path(widget_presentation.mood)
        surface: dict[str, object] = {
            "state": state.value,
            "presentation": {
                "mood": widget_presentation.mood,
                "bubble_text": widget_presentation.bubble_text,
            },
            "available_actions": shell.available_panel_actions(),
            "reply_shortcuts": shell.available_reply_shortcuts(),
            "sprite_asset": str(sprite) if sprite is not None else None,
            "qt_widget_created": getattr(shell, "_widget", None) is not None,
        }
        return surface

    try:
        action_surfaces = {
            "needs_permission": surface_for(
                label="needs-permission",
                state=AttentionState.NEEDS_PERMISSION,
                summary="Widget smoke validation",
            ),
            "needs_input": surface_for(
                label="needs-input",
                state=AttentionState.NEEDS_INPUT,
                summary="Widget input validation",
            ),
        }
        permission_surface = action_surfaces["needs_permission"]
        shell_created = True
        presentation = cast(dict[str, object], permission_surface["presentation"])
        sprite_asset = (
            str(permission_surface["sprite_asset"])
            if permission_surface.get("sprite_asset") is not None
            else None
        )
        raw_available_actions = permission_surface.get("available_actions")
        available_actions = (
            [str(action) for action in raw_available_actions]
            if isinstance(raw_available_actions, list)
            else []
        )
        qt_widget_created = any(
            surface.get("qt_widget_created") is True for surface in action_surfaces.values()
        )
    except Exception as exc:  # noqa: BLE001
        errors.append(f"widget shell failed: {exc}")

    if not shell_created:
        errors.append("widget shell was not created")
    if sprite_asset is None:
        errors.append("widget sprite asset was not resolved")

    if gui_status == "available" and has_graphical_session():
        qt_probe = _widget_qt_smoke_probe(theme=theme_name)
        qt_app_created = qt_probe.get("qt_app_created") is True
        qt_widget_created = qt_probe.get("qt_widget_created") is True

    gui_validated = gui_status == "available" and qt_widget_created
    if required and not gui_validated:
        errors.append("GUI validation required")

    return {
        "schema_version": EVIDENCE_BUNDLE_SCHEMA_VERSION,
        "ok": not errors,
        "required": required,
        "skipped": False,
        "generated_at": datetime.now(UTC).isoformat(),
        "gui_runtime": gui_status,
        "gui_validated": gui_validated,
        "theme": theme_name,
        "theme_ok": theme_ok,
        "theme_detail": theme_detail,
        "shell_created": shell_created,
        "qt_app_created": qt_app_created,
        "qt_widget_created": qt_widget_created,
        "qt_probe": qt_probe,
        "sprite_asset": sprite_asset,
        "presentation": presentation,
        "available_actions": available_actions,
        "action_surfaces": action_surfaces,
        "errors": errors,
    }


def _widget_qt_smoke_probe(*, theme: str) -> dict[str, object]:
    script = """
from __future__ import annotations

import json
import sys
from datetime import UTC, datetime

from PySide6.QtWidgets import QApplication

from coding_pet.gui.widget import CodingPetWidgetShell
from coding_pet.models import AgentKind, AttentionState, SessionStatus

payload = json.loads(sys.stdin.read())
app = QApplication.instance() or QApplication([])
status = SessionStatus(
    session_id="widget-smoke",
    agent_kind=AgentKind.CLAUDE_CODE,
    title="Widget Smoke",
    workspace=payload["workspace"],
    state=AttentionState.NEEDS_PERMISSION,
    summary="Widget smoke validation",
    last_event_at=datetime.now(UTC),
    supported_actions=["send_reply", "send_without_enter", "approve", "reject"],
)
shell = CodingPetWidgetShell(status=status, theme=payload["theme"])
presentation = shell.presentation()
sprite = shell.sprite_asset_path(presentation.mood)
qt_widget_created = getattr(shell, "_widget", None) is not None
print(json.dumps({
    "qt_app_created": True,
    "qt_widget_created": qt_widget_created,
    "sprite_asset": str(sprite) if sprite is not None else None,
}))
raise SystemExit(0 if qt_widget_created else 2)
"""
    try:
        completed = subprocess.run(
            [sys.executable, "-c", script],
            input=json.dumps({"theme": theme, "workspace": str(Path.cwd())}),
            capture_output=True,
            check=False,
            text=True,
            timeout=10.0,
        )
    except subprocess.TimeoutExpired:
        return {
            "attempted": True,
            "ok": False,
            "error": "qt widget smoke timed out",
        }
    except OSError as exc:
        return {
            "attempted": True,
            "ok": False,
            "error": str(exc),
        }

    payload: dict[str, object] = {}
    try:
        if completed.stdout.strip():
            payload = json.loads(completed.stdout.strip().splitlines()[-1])
    except json.JSONDecodeError:
        payload = {}
    return {
        "attempted": True,
        "ok": completed.returncode == 0,
        "returncode": completed.returncode,
        "qt_app_created": payload.get("qt_app_created") is True,
        "qt_widget_created": payload.get("qt_widget_created") is True,
        "sprite_asset": payload.get("sprite_asset"),
        "stderr_tail": _text_tail(completed.stderr, limit=1000),
    }


def _target_backend_action_capability(action: str) -> dict[str, object]:
    return action_capability_for(action, source_kind="tmux").model_dump(mode="json")


def _append_backend_report_capability_errors(
    report: dict[str, object],
    errors: list[str],
    *,
    action: str,
) -> None:
    capability = _json_object(report.get("capability"))
    if capability is None:
        errors.append("capability is required")
        return
    expected = _target_backend_action_capability(action)
    for key in (
        "action",
        "transport",
        "requires_text",
        "press_enter_default",
        "semantics",
    ):
        expected_value = expected.get(key)
        if capability.get(key) != expected_value:
            errors.append(f"capability {key} must be {_expected_value_label(expected_value)}")


def _backend_evidence_check_report(
    report_path: Path,
    *,
    expected_agent: AgentKind | None = None,
    expected_action: str | None = None,
    allow_unchanged_output: bool = False,
) -> dict[str, object]:
    errors: list[str] = []
    try:
        report = json.loads(report_path.read_text("utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "report": str(report_path),
            "errors": [f"could not read report: {exc}"],
        }
    if not isinstance(report, dict):
        return {
            "ok": False,
            "report": str(report_path),
            "errors": ["report must be a JSON object"],
        }

    agent = report.get("agent")
    action = report.get("action")
    action_result = report.get("action_result")
    matched_expected = report.get("matched_expected")
    output_changed = report.get("output_changed")
    expected_regex = report.get("expected_regex")
    before_hash = report.get("before_hash")
    after_hash = report.get("after_hash")
    before_tail = report.get("before_tail")
    after_tail = report.get("after_tail")
    pane = report.get("pane")
    delivered_text: object = None
    if isinstance(action_result, dict):
        delivered_text = action_result.get("delivered_text")

    if report.get("schema_version") != EVIDENCE_BUNDLE_SCHEMA_VERSION:
        errors.append(f"report schema_version must be {EVIDENCE_BUNDLE_SCHEMA_VERSION}")
    if report.get("profile") != "target":
        errors.append(f"report profile must be target, got {report.get('profile')!r}")
    if report.get("ok") is not True:
        errors.append("report ok must be true")
    if not isinstance(pane, str) or not pane:
        errors.append("pane is required")
    if expected_agent is not None and agent != expected_agent.value:
        errors.append(f"agent must be {expected_agent.value}, got {agent!r}")
    if expected_action is not None and action != expected_action:
        errors.append(f"action must be {expected_action}, got {action!r}")
    expected_capability_action = expected_action if expected_action is not None else action
    if isinstance(expected_capability_action, str):
        _append_backend_report_capability_errors(
            report,
            errors,
            action=expected_capability_action,
        )
    else:
        errors.append("capability cannot be verified without action")
    if isinstance(action_result, dict):
        if action_result.get("outcome") != ActionOutcome.ACCEPTED.value:
            errors.append("action_result.outcome must be accepted")
        expected_action_result_action = expected_action if expected_action is not None else action
        if action_result.get("action") != expected_action_result_action:
            errors.append(f"action_result.action must be {expected_action_result_action}")
        if not isinstance(action_result.get("session_id"), str) or not action_result.get(
            "session_id"
        ):
            errors.append("action_result.session_id is required")
    if not isinstance(action_result, dict) or action_result.get("ok") is not True:
        errors.append("action_result.ok must be true")
    elif not isinstance(delivered_text, str) or not delivered_text:
        errors.append("action_result.delivered_text is required")
    elif redact_transcript_text(delivered_text) != delivered_text:
        errors.append("action_result.delivered_text contains unredacted secret-like text")
    if not isinstance(expected_regex, str) or not expected_regex:
        errors.append("expected_regex is required for backend semantic evidence")
    compiled_expected_regex: re.Pattern[str] | None = None
    if isinstance(expected_regex, str) and expected_regex:
        try:
            compiled_expected_regex = re.compile(expected_regex, re.MULTILINE | re.DOTALL)
        except re.error as exc:
            errors.append(f"expected_regex is invalid: {exc}")
    if matched_expected is not True:
        errors.append("matched_expected must be true")
    if output_changed is not True and not allow_unchanged_output:
        errors.append("output_changed must be true")
    if not isinstance(before_hash, str) or not before_hash:
        errors.append("before_hash is required")
    elif not _is_sha256_hex(before_hash):
        errors.append("before_hash must be SHA-256 hex")
    if not isinstance(after_hash, str) or not after_hash:
        errors.append("after_hash is required")
    elif not _is_sha256_hex(after_hash):
        errors.append("after_hash must be SHA-256 hex")
    if (
        isinstance(before_hash, str)
        and isinstance(after_hash, str)
        and before_hash == after_hash
        and not allow_unchanged_output
    ):
        errors.append("before_hash and after_hash must differ")
    if not isinstance(before_tail, str) or not before_tail:
        errors.append("before_tail is required")
    if not isinstance(after_tail, str) or not after_tail:
        errors.append("after_tail is required")
    for key, value in (("before_tail", before_tail), ("after_tail", after_tail)):
        if isinstance(value, str) and redact_transcript_text(value) != value:
            errors.append(f"{key} contains unredacted secret-like text")
    if (
        compiled_expected_regex is not None
        and isinstance(after_tail, str)
        and compiled_expected_regex.search(after_tail) is None
    ):
        errors.append("after_tail must match expected_regex")
    if (
        compiled_expected_regex is not None
        and isinstance(before_tail, str)
        and compiled_expected_regex.search(before_tail) is not None
    ):
        errors.append("before_tail must not match expected_regex")

    return {
        "ok": not errors,
        "report": str(report_path),
        "agent": agent,
        "action": action,
        "pane": pane,
        "expected_agent": expected_agent.value if expected_agent is not None else None,
        "expected_action": expected_action,
        "errors": errors,
        "capability": _json_object(report.get("capability")),
        "action_result": action_result if isinstance(action_result, dict) else None,
        "evidence": {
            "matched_expected": matched_expected,
            "output_changed": output_changed,
            "before_hash": before_hash,
            "after_hash": after_hash,
            "expected_regex": expected_regex,
        },
    }


def _target_backend_report_name(agent: AgentKind, action: str) -> str:
    return f"backend-{agent.value}-{action}.json"


def _target_backend_artifact_filenames() -> dict[str, str]:
    artifacts = {"backend_summary": BACKEND_EVIDENCE_SUMMARY_FILENAME}
    for agent, action in TARGET_BACKEND_EVIDENCE_REQUIREMENTS:
        artifacts[f"backend_{agent.value}_{action}"] = _target_backend_report_name(
            agent,
            action,
        )
    return artifacts


def _target_backend_artifact_paths(output_dir: Path) -> dict[str, str]:
    return {
        key: str(output_dir / filename)
        for key, filename in _target_backend_artifact_filenames().items()
    }


def _target_backend_evidence_specs(
    *,
    claude_pane: str,
    opencode_pane: str,
    claude_reply_pane: str | None,
    claude_approve_pane: str | None,
    claude_reject_pane: str | None,
    opencode_reply_pane: str | None,
    opencode_approve_pane: str | None,
    opencode_reject_pane: str | None,
    reply_text: str,
    reply_expect_regex: str,
    approve_expect_regex: str,
    reject_expect_regex: str,
) -> list[BackendEvidenceSpec]:
    return [
        BackendEvidenceSpec(
            AgentKind.CLAUDE_CODE,
            claude_reply_pane or claude_pane,
            "send_reply",
            reply_text,
            reply_expect_regex,
        ),
        BackendEvidenceSpec(
            AgentKind.CLAUDE_CODE,
            claude_approve_pane or claude_pane,
            "approve",
            None,
            approve_expect_regex,
        ),
        BackendEvidenceSpec(
            AgentKind.CLAUDE_CODE,
            claude_reject_pane or claude_pane,
            "reject",
            None,
            reject_expect_regex,
        ),
        BackendEvidenceSpec(
            AgentKind.OPENCODE,
            opencode_reply_pane or opencode_pane,
            "send_reply",
            reply_text,
            reply_expect_regex,
        ),
        BackendEvidenceSpec(
            AgentKind.OPENCODE,
            opencode_approve_pane or opencode_pane,
            "approve",
            None,
            approve_expect_regex,
        ),
        BackendEvidenceSpec(
            AgentKind.OPENCODE,
            opencode_reject_pane or opencode_pane,
            "reject",
            None,
            reject_expect_regex,
        ),
    ]


async def _collect_target_backend_evidence(
    *,
    output_dir: Path,
    specs: list[BackendEvidenceSpec],
    timeout_s: float,
    capture_lines: int,
) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    reports: list[dict[str, object]] = []
    backend_registry = AgentBackendRegistry.default()
    for spec in specs:
        report_path = output_dir / _target_backend_report_name(spec.agent, spec.action)
        expected_delivered_text = backend_registry.describe(spec.agent).adapter.control_message(
            action=cast(SupportedAction, spec.action),
            reply_text=spec.reply_text,
        )
        try:
            report = await _verify_tmux_action_once(
                pane=spec.pane,
                agent=spec.agent,
                action=spec.action,
                reply_text=spec.reply_text,
                title=None,
                press_enter=True,
                expect_regex=spec.expect_regex,
                timeout_s=timeout_s,
                capture_lines=capture_lines,
            )
        except Exception as exc:  # noqa: BLE001
            report = _backend_action_exception_report(
                pane=spec.pane,
                agent=spec.agent,
                action=spec.action,
                expect_regex=spec.expect_regex,
                exc=exc,
            )
        _write_json_report(report_path, report)
        check = _backend_evidence_check_report(
            report_path,
            expected_agent=spec.agent,
            expected_action=spec.action,
        )
        reports.append(
            {
                "ok": check["ok"] is True,
                "agent": spec.agent.value,
                "action": spec.action,
                "pane": spec.pane,
                "report": str(report_path),
                "expected_delivered_text": expected_delivered_text,
                "expected_regex": spec.expect_regex,
                "expected_outcome": ActionOutcome.ACCEPTED.value,
                "capability": _target_backend_action_capability(spec.action),
                "errors": check.get("errors", []),
            }
        )

    summary: dict[str, object] = {
        "schema_version": EVIDENCE_BUNDLE_SCHEMA_VERSION,
        "ok": all(report.get("ok") is True for report in reports),
        "profile": "target",
        "generated_at": datetime.now(UTC).isoformat(),
        "output_dir": str(output_dir),
        "reports": reports,
    }
    _write_json_report(output_dir / BACKEND_EVIDENCE_SUMMARY_FILENAME, summary)
    _merge_target_backend_artifacts_into_summary(
        output_dir,
        backend_ok=summary["ok"] is True,
    )
    return summary


def _read_json_object(path: Path) -> tuple[dict[str, object] | None, str | None]:
    try:
        payload = json.loads(path.read_text("utf-8"))
    except Exception as exc:  # noqa: BLE001
        return None, str(exc)
    if not isinstance(payload, dict):
        return None, "not a JSON object"
    return payload, None


def _merge_target_backend_artifacts_into_summary(
    output_dir: Path,
    *,
    backend_ok: bool | None = None,
) -> None:
    summary_path = output_dir / "summary.json"
    if not summary_path.exists():
        return
    summary, summary_error = _read_json_object(summary_path)
    if summary_error is not None or summary is None:
        return
    artifacts = _json_object(summary.get("artifacts")) or {}
    artifacts.update(_target_backend_artifact_paths(output_dir))
    summary["artifacts"] = artifacts
    if backend_ok is not None:
        raw_failed_required = summary.get("failed_required")
        failed_required = (
            [str(item) for item in raw_failed_required]
            if isinstance(raw_failed_required, list)
            else []
        )
        failed_required = [item for item in failed_required if item != "backend_evidence"]
        if not backend_ok:
            failed_required.append("backend_evidence")
        summary["failed_required"] = failed_required
        summary["ok"] = not failed_required
    _write_json_report(summary_path, summary)


def _default_agent_hooks_dir() -> Path:
    return load_config().config_dir / "hooks"


def _default_claude_settings_path() -> Path:
    return Path.home() / ".claude" / "settings.json"


def _default_opencode_plugin_path() -> Path:
    return Path.home() / ".config" / "opencode" / "plugins" / "coding-pet.js"


def _agent_hook_files(hooks_dir: Path) -> AgentHookFiles:
    return AgentHookFiles(
        hooks_dir=hooks_dir,
        hook_script=hooks_dir / "coding-pet-hook.sh",
        claude_settings_snippet=hooks_dir / "claude-settings-snippet.json",
        opencode_plugin_snippet=hooks_dir / "coding-pet-opencode-plugin.js",
    )


def _write_agent_hook_files(hooks_dir: Path) -> AgentHookFiles:
    files = _agent_hook_files(hooks_dir)
    hooks_dir.mkdir(parents=True, exist_ok=True)
    files.hook_script.write_text(hook_script_source(), encoding="utf-8")
    os.chmod(files.hook_script, 0o755)
    _write_json_report(
        files.claude_settings_snippet,
        claude_settings_snippet(hook_script=files.hook_script),
    )
    files.opencode_plugin_snippet.write_text(
        opencode_plugin_source(hook_script=files.hook_script),
        encoding="utf-8",
    )
    return files


def _read_optional_json_object(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    payload, error = _read_json_object(path)
    if error is not None or payload is None:
        raise ValueError(f"{path}: {error or 'not a JSON object'}")
    return payload


def _install_claude_hooks(settings_path: Path, *, hook_script: Path) -> None:
    settings = _read_optional_json_object(settings_path)
    merged = merge_claude_settings(settings, hook_script=hook_script)
    _write_json_report(settings_path, merged)


def _install_opencode_plugin(plugin_path: Path, *, hook_script: Path) -> None:
    plugin_path.parent.mkdir(parents=True, exist_ok=True)
    plugin_path.write_text(opencode_plugin_source(hook_script=hook_script), encoding="utf-8")


def _hook_script_smoke_report(hook_script: Path) -> dict[str, object]:
    if not hook_script.exists():
        return {
            "name": "hook_script_smoke",
            "ok": False,
            "required": True,
            "detail": f"{hook_script}:missing",
        }
    env = dict(os.environ)
    env.update(
        {
            "CODING_PET_BIN": "true",
            "CODING_PET_HOOK_SESSION_ID": "doctor",
            "CODING_PET_HOOK_WORKSPACE": str(hook_script.parent),
            "CODING_PET_HOOK_TITLE": "doctor hook smoke",
            "CODING_PET_HOOK_SUMMARY": "doctor smoke",
        }
    )
    try:
        completed = subprocess.run(
            [str(hook_script), AgentKind.CLAUDE_CODE.value, "PreToolUse"],
            input='{"session_id":"doctor","cwd":"/tmp"}',
            capture_output=True,
            check=False,
            env=env,
            text=True,
            timeout=5.0,
        )
    except Exception as exc:  # noqa: BLE001
        return {
            "name": "hook_script_smoke",
            "ok": False,
            "required": True,
            "detail": f"{hook_script}: {exc}",
        }
    return {
        "name": "hook_script_smoke",
        "ok": completed.returncode == 0,
        "required": True,
        "detail": f"{hook_script}:returncode={completed.returncode}",
    }


def _agent_hooks_doctor_report(
    *,
    hooks_dir: Path,
    claude_settings: Path,
    opencode_plugin: Path,
    skip_claude: bool,
    skip_opencode: bool,
) -> dict[str, object]:
    files = _agent_hook_files(hooks_dir)
    checks: list[dict[str, object]] = []

    script_executable = files.hook_script.exists() and files.hook_script.stat().st_mode & 0o111 != 0
    checks.append(
        {
            "name": "hook_script",
            "ok": script_executable,
            "required": True,
            "detail": str(files.hook_script),
        }
    )
    checks.append(_hook_script_smoke_report(files.hook_script))

    if not skip_claude:
        if claude_settings.exists():
            settings, error = _read_json_object(claude_settings)
        else:
            settings, error = None, "missing"
        claude_ok = (
            error is None
            and settings is not None
            and claude_settings_has_hooks(settings, hook_script=files.hook_script)
        )
        checks.append(
            {
                "name": "claude_settings",
                "ok": claude_ok,
                "required": True,
                "detail": str(claude_settings) if error is None else f"{claude_settings}:{error}",
            }
        )

    if not skip_opencode:
        if opencode_plugin.exists():
            source = opencode_plugin.read_text("utf-8")
            opencode_ok = opencode_plugin_has_hooks(source, hook_script=files.hook_script)
            detail = str(opencode_plugin)
        else:
            opencode_ok = False
            detail = f"{opencode_plugin}:missing"
        checks.append(
            {
                "name": "opencode_plugin",
                "ok": opencode_ok,
                "required": True,
                "detail": detail,
            }
        )

    return _versioned_evidence_report(
        {
            "ok": all(check["ok"] is True for check in checks),
            "hooks_dir": str(hooks_dir),
            "checks": checks,
        }
    )


def _agent_hooks_evidence_report(
    *,
    hooks_dir: Path,
    claude_settings: Path,
    opencode_plugin: Path,
    skip_claude: bool,
    skip_opencode: bool,
    required: bool,
) -> dict[str, object]:
    report = _agent_hooks_doctor_report(
        hooks_dir=hooks_dir,
        claude_settings=claude_settings,
        opencode_plugin=opencode_plugin,
        skip_claude=skip_claude,
        skip_opencode=skip_opencode,
    )
    report["required"] = required
    report["claude_settings"] = str(claude_settings)
    report["opencode_plugin"] = str(opencode_plugin)
    return report


def _base_hook_event_smoke_report(
    *,
    required: bool,
    socket_path: Path,
    workspace: Path,
) -> dict[str, object]:
    return {
        "schema_version": EVIDENCE_BUNDLE_SCHEMA_VERSION,
        "ok": False,
        "required": required,
        "skipped": False,
        "generated_at": datetime.now(UTC).isoformat(),
        "socket_path": str(socket_path),
        "event": {
            "agent": HOOK_EVENT_SMOKE_AGENT.value,
            "event": HOOK_EVENT_SMOKE_EVENT,
            "session_id": HOOK_EVENT_SMOKE_SESSION_ID,
            "workspace": str(workspace),
        },
        "hook_result": None,
        "transcript": {
            "enabled": False,
            "verified": False,
            "session_id": None,
            "db_path": None,
            "events": 0,
        },
        "cleanup_result": {
            "ok": False,
            "skipped": True,
            "action": "hide_pet",
        },
        "errors": [],
    }


async def _hook_event_smoke_evidence_report_async(
    *,
    config: AppConfig,
    required: bool,
    socket_path: Path,
    workspace: Path,
    timeout_s: float,
) -> dict[str, object]:
    report = _base_hook_event_smoke_report(
        required=required,
        socket_path=socket_path,
        workspace=workspace,
    )
    errors: list[str] = []

    try:
        hook_result = await asyncio.wait_for(
            _send_hook_event_once(
                socket_path=socket_path,
                agent=HOOK_EVENT_SMOKE_AGENT,
                event=HOOK_EVENT_SMOKE_EVENT,
                session_id=HOOK_EVENT_SMOKE_SESSION_ID,
                workspace=str(workspace),
                title=HOOK_EVENT_SMOKE_TITLE,
                summary=HOOK_EVENT_SMOKE_SUMMARY,
            ),
            timeout=max(1.0, timeout_s),
        )
    except Exception as exc:  # noqa: BLE001
        hook_result = {
            "ok": False,
            "error": str(exc),
        }
        errors.append(f"hook event failed: {exc}")

    report["hook_result"] = hook_result
    if hook_result.get("ok") is not True:
        errors.append("hook_result ok must be true")

    daemon_session_id = hook_result.get("session_id")
    if not isinstance(daemon_session_id, str) or not daemon_session_id:
        errors.append("hook_result session_id is required")

    transcript_store = _configured_transcript_store(config)
    transcript_verified = False
    transcript_count = 0
    if transcript_store is None:
        errors.append("transcript store is disabled")
        report["transcript"] = {
            "enabled": False,
            "verified": False,
            "session_id": None,
            "db_path": None,
            "events": 0,
        }
    elif isinstance(daemon_session_id, str) and daemon_session_id:
        try:
            events = await transcript_store.list_recent_events(daemon_session_id, limit=10)
        except Exception as exc:  # noqa: BLE001
            events = []
            errors.append(f"transcript read failed: {exc}")
        transcript_count = len(events)
        transcript_verified = any(
            event.source == "hook_event" and event.text == HOOK_EVENT_SMOKE_TRANSCRIPT_TEXT
            for event in events
        )
        if not transcript_verified:
            errors.append("hook transcript event was not found")
        report["transcript"] = {
            "enabled": True,
            "verified": transcript_verified,
            "session_id": daemon_session_id,
            "db_path": str(transcript_store.path),
            "events": transcript_count,
        }

    if isinstance(daemon_session_id, str) and daemon_session_id:
        try:
            cleanup_result = await asyncio.wait_for(
                _send_daemon_action_once(
                    socket_path=socket_path,
                    session_id=daemon_session_id,
                    action="hide_pet",
                    reply_text=None,
                    press_enter=True,
                ),
                timeout=max(1.0, timeout_s),
            )
        except Exception as exc:  # noqa: BLE001
            cleanup_result = {
                "ok": False,
                "action": "hide_pet",
                "error": str(exc),
            }
            errors.append(f"hook smoke cleanup failed: {exc}")
        report["cleanup_result"] = cleanup_result
        if cleanup_result.get("ok") is not True:
            errors.append("cleanup_result ok must be true")
        if cleanup_result.get("outcome") != ActionOutcome.LOCAL_UPDATED.value:
            errors.append(f"cleanup_result outcome must be {ActionOutcome.LOCAL_UPDATED.value}")
        if cleanup_result.get("reason") != "hidden":
            errors.append("cleanup_result reason must be hidden")
        cleanup_detail = cleanup_result.get("detail")
        if not isinstance(cleanup_detail, str) or not cleanup_detail:
            errors.append("cleanup_result detail is required")

    report["errors"] = errors
    report["ok"] = not errors
    report["detail"] = (
        "hook event smoke verified" if report["ok"] is True else "hook event smoke failed"
    )
    return report


def _hook_event_smoke_evidence_report(
    *,
    required: bool,
    socket_path: Path,
    workspace: Path,
    timeout_s: float,
) -> dict[str, object]:
    if not socket_path.exists():
        report = _base_hook_event_smoke_report(
            required=required,
            socket_path=socket_path,
            workspace=workspace,
        )
        report["errors"] = ["daemon socket unavailable"]
        report["detail"] = "daemon socket unavailable"
        return report
    config = load_config()
    return asyncio.run(
        _hook_event_smoke_evidence_report_async(
            config=config,
            required=required,
            socket_path=socket_path,
            workspace=workspace,
            timeout_s=timeout_s,
        )
    )


def _json_object(value: object) -> dict[str, object] | None:
    if isinstance(value, dict):
        return cast(dict[str, object], value)
    return None


def _append_target_acceptance_errors(
    acceptance: dict[str, object],
    errors: list[str],
) -> None:
    raw_checks = acceptance.get("checks")
    if not isinstance(raw_checks, list):
        errors.append("acceptance checks must be a list")
        return
    checks_by_name: dict[str, dict[str, object]] = {}
    for raw_check in raw_checks:
        check = _json_object(raw_check)
        if check is None:
            continue
        name = check.get("name")
        if isinstance(name, str):
            if name in checks_by_name:
                errors.append(f"acceptance duplicate check {name}")
                continue
            checks_by_name[name] = check
    for name in TARGET_ACCEPTANCE_REQUIRED_CHECKS:
        check = checks_by_name.get(name)
        if check is None:
            errors.append(f"acceptance missing required check {name}")
            continue
        if check.get("required") is not True:
            errors.append(f"acceptance check {name} required must be true")
        if check.get("ok") is not True:
            errors.append(f"acceptance check {name} ok must be true")
    known_required_checks = set(TARGET_ACCEPTANCE_REQUIRED_CHECKS)
    for name, check in checks_by_name.items():
        if name in known_required_checks:
            continue
        if check.get("required") is True and check.get("ok") is not True:
            errors.append(f"acceptance check {name} ok must be true")


def _target_backend_binary_name(agent: AgentKind) -> str:
    if agent is AgentKind.CLAUDE_CODE:
        return "claude"
    if agent is AgentKind.OPENCODE:
        return "opencode"
    return agent.value


TARGET_ENVIRONMENT_PATH_FIELDS = (
    "config_dir",
    "state_dir",
    "runtime_dir",
    "state_file",
    "log_dir",
    "transcript_db",
)


def _append_removed_legacy_theme_name_error(
    label: str,
    theme_name: object,
    errors: list[str],
) -> None:
    if isinstance(theme_name, str) and theme_name in REMOVED_LEGACY_THEME_NAMES:
        errors.append(f"{label} must not use removed legacy theme {theme_name}")


def _append_removed_legacy_sprite_asset_error(
    label: str,
    sprite_asset: object,
    errors: list[str],
) -> None:
    if not isinstance(sprite_asset, str) or not sprite_asset:
        return
    if any(part in REMOVED_LEGACY_THEME_NAMES for part in Path(sprite_asset).parts):
        errors.append(f"{label} must not point at a removed legacy theme asset")


def _target_environment_paths(
    environment: dict[str, object],
    errors: list[str],
) -> dict[str, str]:
    raw_paths = _json_object(environment.get("paths"))
    if raw_paths is None:
        errors.append("environment paths must be an object")
        return {}
    paths: dict[str, str] = {}
    for name in TARGET_ENVIRONMENT_PATH_FIELDS:
        value = raw_paths.get(name)
        if not isinstance(value, str) or not value:
            errors.append(f"environment paths.{name} is required")
            continue
        paths[name] = value
        path = Path(value)
        if not path.is_absolute():
            errors.append(f"environment paths.{name} must be an absolute path")
        elif name == "runtime_dir" and not value.startswith("/run/user/"):
            errors.append("environment paths.runtime_dir must be under /run/user")
    return paths


def _append_target_environment_errors(
    environment: dict[str, object],
    errors: list[str],
) -> None:
    platform_report = _json_object(environment.get("platform"))
    if platform_report is None:
        errors.append("environment platform must be an object")
    elif platform_report.get("system") != "Linux":
        errors.append(
            f"environment platform.system must be Linux, got {platform_report.get('system')!r}"
        )
    else:
        if platform_report.get("machine") != "x86_64":
            errors.append("environment platform.machine must be x86_64")
        platform_release = platform_report.get("release")
        if not isinstance(platform_release, str) or "el8_10" not in platform_release:
            errors.append("environment platform.release must describe RHEL 8.10")

    python_report = _json_object(environment.get("python"))
    python_version = python_report.get("version") if python_report is not None else None
    if not isinstance(python_version, str) or not python_version.startswith("3.12."):
        errors.append("environment python.version must be 3.12.x")
    python_executable = python_report.get("executable") if python_report is not None else None
    if not isinstance(python_executable, str) or not python_executable:
        errors.append("environment python.executable is required")
    else:
        python_executable_path = Path(python_executable)
        if not python_executable_path.is_absolute():
            errors.append("environment python.executable must be an absolute path")
        elif not python_executable_path.name.startswith("python"):
            errors.append("environment python.executable must point to python")

    libc_report = _json_object(environment.get("libc"))
    libc_name = libc_report.get("name") if libc_report is not None else None
    libc_version = libc_report.get("version") if libc_report is not None else None
    if libc_name != "glibc":
        errors.append("environment libc.name must be glibc")
    if libc_version != "2.28":
        errors.append("environment libc.version must be exactly 2.28")

    release_text = environment.get("redhat_release")
    if (
        not isinstance(release_text, str)
        or "Red Hat Enterprise Linux" not in release_text
        or "8.10" not in release_text
    ):
        errors.append("environment redhat_release must describe RHEL 8.10")

    if environment.get("gui_runtime") != "available":
        errors.append("environment gui_runtime must be available")

    tmux_binary = environment.get("tmux_binary")
    if not isinstance(tmux_binary, str) or not tmux_binary:
        errors.append("environment tmux_binary is required")
    else:
        tmux_binary_path = Path(tmux_binary)
        if not tmux_binary_path.is_absolute():
            errors.append("environment tmux_binary must be an absolute path")
        elif tmux_binary_path.name != "tmux":
            errors.append("environment tmux_binary must point to tmux")

    notify_send = environment.get("notify_send")
    if not isinstance(notify_send, str) or not notify_send:
        errors.append("environment notify_send is required")
    else:
        notify_send_path = Path(notify_send)
        if not notify_send_path.is_absolute():
            errors.append("environment notify_send must be an absolute path")
        elif notify_send_path.name != "notify-send":
            errors.append("environment notify_send must point to notify-send")

    environment_paths = _target_environment_paths(environment, errors)

    transcript = _json_object(environment.get("transcript"))
    if transcript is None:
        errors.append("environment transcript must be an object")
    else:
        if transcript.get("enabled") is not True:
            errors.append("environment transcript.enabled must be true")
        if transcript.get("backend") != "sqlite":
            errors.append("environment transcript.backend must be sqlite")
        if transcript.get("redact_secrets") is not True:
            errors.append("environment transcript.redact_secrets must be true")
        max_events = transcript.get("max_events_per_session")
        if not _is_plain_int(max_events) or max_events <= 0:
            errors.append("environment transcript.max_events_per_session must be positive")
        transcript_db_path = transcript.get("db_path")
        if not isinstance(transcript_db_path, str) or not transcript_db_path:
            errors.append("environment transcript.db_path is required")
        else:
            transcript_db = Path(transcript_db_path)
            if not transcript_db.is_absolute():
                errors.append("environment transcript.db_path must be an absolute path")
            paths_transcript_db = environment_paths.get("transcript_db")
            if (
                isinstance(paths_transcript_db, str)
                and paths_transcript_db
                and transcript_db.resolve() != Path(paths_transcript_db).resolve()
            ):
                errors.append("environment transcript.db_path must match paths.transcript_db")

    theme = _json_object(environment.get("theme"))
    if theme is None:
        errors.append("environment theme must be an object")
    else:
        if theme.get("ok") is not True:
            errors.append("environment theme ok must be true")
        theme_name = theme.get("name")
        if not isinstance(theme_name, str) or not theme_name:
            errors.append("environment theme.name is required")
        else:
            _append_removed_legacy_theme_name_error(
                "environment theme.name",
                theme_name,
                errors,
            )
        if not isinstance(theme.get("detail"), str) or not theme.get("detail"):
            errors.append("environment theme.detail is required")

    raw_backends = environment.get("backends")
    if not isinstance(raw_backends, list):
        errors.append("environment backends must be a list")
        return
    backends_by_kind: dict[str, dict[str, object]] = {}
    for raw_backend in raw_backends:
        backend = _json_object(raw_backend)
        if backend is None:
            continue
        kind = backend.get("agent_kind")
        if isinstance(kind, str):
            backends_by_kind[kind] = backend
    for agent in TARGET_REQUIRED_AGENTS:
        backend = backends_by_kind.get(agent.value)
        if backend is None:
            errors.append(f"environment missing backend {agent.value}")
            continue
        if backend.get("available") is not True:
            errors.append(f"environment backend {agent.value} must be available")
        expected_binary_name = _target_backend_binary_name(agent)
        binary_name = backend.get("binary_name")
        if binary_name != expected_binary_name:
            errors.append(
                f"environment backend {agent.value} binary_name must be {expected_binary_name}"
            )
        binary_path = backend.get("binary_path")
        if not isinstance(binary_path, str) or not binary_path:
            errors.append(f"environment backend {agent.value} binary_path is required")
        else:
            backend_binary_path = Path(binary_path)
            if not backend_binary_path.is_absolute():
                errors.append(
                    f"environment backend {agent.value} binary_path must be an absolute path"
                )
            elif backend_binary_path.name != expected_binary_name:
                errors.append(
                    f"environment backend {agent.value} binary_path must point to "
                    f"{expected_binary_name}"
                )
            reason = backend.get("reason")
            if reason != f"available at {binary_path}":
                errors.append(
                    f"environment backend {agent.value} binary_path must match available reason"
                )
        control_messages = _json_object(backend.get("control_messages"))
        if control_messages is None:
            errors.append(f"environment backend {agent.value} control_messages missing")
            continue
        for action in ("approve", "reject"):
            message = control_messages.get(action)
            if not isinstance(message, str) or not message:
                errors.append(
                    f"environment backend {agent.value} control message {action} is required"
                )


def _is_sha256_hex(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(char in "0123456789abcdef" for char in value)
    )


def _is_plain_int(value: object) -> TypeGuard[int]:
    return isinstance(value, int) and not isinstance(value, bool)


def _append_target_wheelhouse_errors(
    wheelhouse: dict[str, object],
    errors: list[str],
) -> None:
    raw_required = wheelhouse.get("required_distributions")
    raw_present = wheelhouse.get("present_distributions")
    if not isinstance(raw_required, list):
        errors.append("wheelhouse required_distributions must be a list")
        required = list(RHEL8_WHEELHOUSE_REQUIRED_DISTS)
    else:
        required = [str(item) for item in raw_required]
    if not isinstance(raw_present, list):
        errors.append("wheelhouse present_distributions must be a list")
        present: set[str] = set()
    else:
        present = {str(item) for item in raw_present}

    for distribution in required:
        if distribution not in present:
            errors.append(f"wheelhouse missing required distribution {distribution}")

    install_smoke = _json_object(wheelhouse.get("install_smoke"))
    if install_smoke is None:
        errors.append("wheelhouse install_smoke must be an object")
    else:
        if install_smoke.get("ok") is not True:
            errors.append("wheelhouse install_smoke.ok must be true")
        if install_smoke.get("skipped") is True:
            errors.append("wheelhouse install_smoke must not be skipped")
        elif install_smoke.get("skipped") is not False:
            errors.append("wheelhouse install_smoke.skipped must be false")
        if install_smoke.get("stage") != "import":
            errors.append("wheelhouse install_smoke.stage must be import")

    raw_wheels = wheelhouse.get("wheels")
    if not isinstance(raw_wheels, list) or not raw_wheels:
        errors.append("wheelhouse wheels must include transfer hashes")
        return
    wheel_distributions: set[str] = set()
    wheel_filenames: set[str] = set()
    wheel_hashes: set[str] = set()
    for raw_wheel in raw_wheels:
        wheel = _json_object(raw_wheel)
        if wheel is None:
            errors.append("wheelhouse wheel entry must be an object")
            continue
        filename = wheel.get("filename")
        label = filename if isinstance(filename, str) and filename else "<unknown>"
        if not isinstance(filename, str) or not filename.endswith(".whl"):
            errors.append("wheelhouse wheel filename must end with .whl")
        else:
            if filename in wheel_filenames:
                errors.append(f"wheelhouse duplicate wheel filename {filename}")
            else:
                wheel_filenames.add(filename)
            if not _wheel_platform_tags_compatible_with_rhel8_x86_64(filename):
                errors.append(
                    f"wheelhouse wheel {filename} platform tag is incompatible "
                    "with RHEL 8.10 x86_64 target"
                )
            elif not _wheel_python_tags_compatible_with_target(filename):
                errors.append(
                    f"wheelhouse wheel {filename} python tag is incompatible "
                    "with Python 3.12 target"
                )
        wheel_distribution = wheel.get("distribution")
        if isinstance(wheel_distribution, str) and wheel_distribution:
            if wheel_distribution in wheel_distributions:
                errors.append(f"wheelhouse duplicate wheel distribution {wheel_distribution}")
            wheel_distributions.add(wheel_distribution)
        wheel_sha = wheel.get("sha256")
        if not _is_sha256_hex(wheel_sha):
            errors.append(f"wheelhouse wheel {label} sha256 is required")
        elif str(wheel_sha) in wheel_hashes:
            errors.append("wheelhouse duplicate wheel sha256")
        else:
            wheel_hashes.add(str(wheel_sha))
        size_bytes = wheel.get("size_bytes")
        if not isinstance(size_bytes, int) or size_bytes <= 0:
            errors.append(f"wheelhouse wheel {label} size_bytes must be positive")
    for distribution in required:
        if distribution not in wheel_distributions:
            errors.append(f"wheelhouse missing wheel record for distribution {distribution}")


def _append_target_pet_package_errors(
    pet_packages: dict[str, object],
    errors: list[str],
) -> None:
    total = pet_packages.get("total")
    if not _is_plain_int(total) or total <= 0:
        errors.append("pet_packages total must be positive")
    passed = pet_packages.get("passed")
    if not _is_plain_int(passed) or passed < 0:
        errors.append("pet_packages passed must be a non-negative integer")
    failed = pet_packages.get("failed")
    if not _is_plain_int(failed) or failed != 0:
        errors.append("pet_packages failed must be 0")
    pets = pet_packages.get("pets")
    if not isinstance(pets, list) or not pets:
        errors.append("pet_packages pets must be a non-empty list")
        return
    if _is_plain_int(total) and total > 0 and total != len(pets):
        errors.append("pet_packages total must match pets count")
    if (
        _is_plain_int(total)
        and total > 0
        and _is_plain_int(passed)
        and _is_plain_int(failed)
        and passed + failed != total
    ):
        errors.append("pet_packages passed plus failed must equal total")
    if (
        failed == 0
        and _is_plain_int(total)
        and total > 0
        and _is_plain_int(passed)
        and passed != total
    ):
        errors.append("pet_packages passed must equal total when failed is 0")
    seen_theme_ids: set[str] = set()
    seen_source_packages: set[str] = set()
    seen_transfer_hashes: set[str] = set()
    for raw_pet in pets:
        pet = _json_object(raw_pet)
        if pet is None:
            errors.append("pet_packages pet entry must be an object")
            continue
        if pet.get("ok") is not True:
            errors.append("pet_packages pet ok must be true")
        theme_id = pet.get("theme_id")
        if not isinstance(theme_id, str) or not theme_id:
            errors.append("pet_packages pet theme_id is required")
        elif theme_id in seen_theme_ids:
            errors.append(f"pet_packages duplicate theme_id {theme_id}")
        else:
            seen_theme_ids.add(theme_id)
        source_package = pet.get("source_package")
        if not isinstance(source_package, str) or not source_package:
            errors.append("pet_packages pet source_package is required")
        elif source_package in seen_source_packages:
            errors.append(f"pet_packages duplicate source_package {source_package}")
        else:
            seen_source_packages.add(source_package)
        if not isinstance(pet.get("manifest"), str) or not pet.get("manifest"):
            errors.append("pet_packages pet manifest is required")
        if pet.get("theme_format") != "codex_pet":
            errors.append("pet_packages pet theme_format must be codex_pet")
        if not isinstance(pet.get("spritesheet"), str) or not pet.get("spritesheet"):
            errors.append("pet_packages pet spritesheet is required")

        atlas_size = _json_object(pet.get("atlas_size"))
        atlas_grid = _json_object(pet.get("atlas_grid"))
        frame_size = _json_object(pet.get("frame_size"))
        atlas_width = atlas_height = grid_columns = grid_rows = frame_width = frame_height = None
        if atlas_size is None:
            errors.append("pet_packages pet atlas_size must be an object")
        else:
            atlas_width = atlas_size.get("width")
            atlas_height = atlas_size.get("height")
            if not _is_plain_int(atlas_width) or atlas_width <= 0:
                errors.append("pet_packages pet atlas_size.width must be positive")
            if not _is_plain_int(atlas_height) or atlas_height <= 0:
                errors.append("pet_packages pet atlas_size.height must be positive")
        if atlas_grid is None:
            errors.append("pet_packages pet atlas_grid must be an object")
        else:
            grid_columns = atlas_grid.get("columns")
            grid_rows = atlas_grid.get("rows")
            if not _is_plain_int(grid_columns) or grid_columns <= 0:
                errors.append("pet_packages pet atlas_grid.columns must be positive")
            if not _is_plain_int(grid_rows) or grid_rows <= 0:
                errors.append("pet_packages pet atlas_grid.rows must be positive")
        if frame_size is None:
            errors.append("pet_packages pet frame_size must be an object")
        else:
            frame_width = frame_size.get("width")
            frame_height = frame_size.get("height")
            if not _is_plain_int(frame_width) or frame_width <= 0:
                errors.append("pet_packages pet frame_size.width must be positive")
            if not _is_plain_int(frame_height) or frame_height <= 0:
                errors.append("pet_packages pet frame_size.height must be positive")
        if (
            _is_plain_int(atlas_width)
            and _is_plain_int(atlas_height)
            and _is_plain_int(grid_columns)
            and _is_plain_int(grid_rows)
            and _is_plain_int(frame_width)
            and _is_plain_int(frame_height)
            and (
                atlas_width != grid_columns * frame_width
                or atlas_height != grid_rows * frame_height
            )
        ):
            errors.append("pet_packages pet atlas_size must match grid and frame size")

        frame_counts = _json_object(pet.get("frame_counts_by_row"))
        if frame_counts is None or not frame_counts:
            errors.append("pet_packages pet frame_counts_by_row must be a non-empty object")
        else:
            for row_label, count in frame_counts.items():
                if not _is_plain_int(count) or count <= 0:
                    errors.append(
                        f"pet_packages pet frame_counts_by_row {row_label} must be positive"
                    )

        mood_rows = _json_object(pet.get("mood_rows"))
        if mood_rows is None:
            errors.append("pet_packages pet mood_rows must be an object")
        else:
            for mood in WidgetMood:
                mood_row = mood_rows.get(mood.value)
                if not _is_plain_int(mood_row):
                    errors.append(f"pet_packages pet mood_rows missing {mood.value}")
                elif mood_row < 0:
                    errors.append(f"pet_packages pet mood_rows {mood.value} must be non-negative")
                elif _is_plain_int(grid_rows) and mood_row >= grid_rows:
                    errors.append(
                        f"pet_packages pet mood_rows {mood.value} must be within atlas rows"
                    )

        atlas_cells = _json_object(pet.get("atlas_cells"))
        if atlas_cells is None:
            errors.append("pet_packages pet atlas_cells must be an object")
        else:
            if atlas_cells.get("ok") is not True:
                errors.append("pet_packages pet atlas_cells.ok must be true")
            atlas_cell_errors = atlas_cells.get("errors")
            if not isinstance(atlas_cell_errors, list) or atlas_cell_errors:
                errors.append("pet_packages pet atlas_cells.errors must be empty")
            transparent_residue = atlas_cells.get("transparent_rgb_residue_pixels")
            if transparent_residue is not None and (
                not _is_plain_int(transparent_residue) or transparent_residue < 0
            ):
                errors.append(
                    "pet_packages pet atlas_cells.transparent_rgb_residue_pixels "
                    "must be non-negative"
                )
        transfer = _json_object(pet.get("transfer"))
        if transfer is None:
            errors.append("pet_packages pet transfer must be an object")
            continue
        if transfer.get("kind") not in {"file", "directory"}:
            errors.append("pet_packages pet transfer.kind must be file or directory")
        transfer_sha = transfer.get("sha256")
        if not _is_sha256_hex(transfer_sha):
            errors.append("pet_packages pet transfer.sha256 is required")
        elif str(transfer_sha) in seen_transfer_hashes:
            errors.append("pet_packages duplicate transfer.sha256")
        else:
            seen_transfer_hashes.add(str(transfer_sha))
        size_bytes = transfer.get("size_bytes")
        if not _is_plain_int(size_bytes) or size_bytes <= 0:
            errors.append("pet_packages pet transfer.size_bytes must be positive")
        file_count = transfer.get("file_count")
        if not _is_plain_int(file_count) or file_count <= 0:
            errors.append("pet_packages pet transfer.file_count must be positive")
        petdex_metadata_raw = pet.get("petdex_metadata")
        if petdex_metadata_raw is not None:
            petdex_metadata = _json_object(petdex_metadata_raw)
            if petdex_metadata is None:
                errors.append("pet_packages pet petdex_metadata must be an object")
                continue
            if not isinstance(petdex_metadata.get("path"), str) or not petdex_metadata.get("path"):
                errors.append("pet_packages pet petdex_metadata.path is required")
            if not _is_sha256_hex(petdex_metadata.get("sha256")):
                errors.append("pet_packages pet petdex_metadata.sha256 is required")
            metadata_size = petdex_metadata.get("size_bytes")
            if not _is_plain_int(metadata_size) or metadata_size <= 0:
                errors.append("pet_packages pet petdex_metadata.size_bytes must be positive")
            if petdex_metadata.get("source") != "petdex":
                errors.append("pet_packages pet petdex_metadata.source must be petdex")
            if not isinstance(petdex_metadata.get("slug"), str) or not petdex_metadata.get("slug"):
                errors.append("pet_packages pet petdex_metadata.slug is required")
            if not isinstance(
                petdex_metadata.get("zip_url"),
                str,
            ) or not petdex_metadata.get("zip_url"):
                errors.append("pet_packages pet petdex_metadata.zip_url is required")
            metadata_archive_sha = petdex_metadata.get("archive_sha256")
            if not _is_sha256_hex(metadata_archive_sha):
                errors.append("pet_packages pet petdex_metadata.archive_sha256 is required")
            elif metadata_archive_sha != transfer.get("sha256"):
                errors.append(
                    "pet_packages pet petdex_metadata archive_sha256 must match transfer.sha256"
                )
            metadata_archive_size = petdex_metadata.get("archive_size_bytes")
            if not _is_plain_int(metadata_archive_size) or metadata_archive_size <= 0:
                errors.append(
                    "pet_packages pet petdex_metadata.archive_size_bytes must be positive"
                )
            elif metadata_archive_size != transfer.get("size_bytes"):
                errors.append(
                    "pet_packages pet petdex_metadata archive_size_bytes "
                    "must match transfer.size_bytes"
                )


def _append_target_report_status_errors(
    label: str,
    report: dict[str, object],
    errors: list[str],
    *,
    require_skipped: bool = False,
    require_checks: bool = False,
) -> None:
    _append_evidence_report_identity_errors(label, report, errors)
    _append_target_report_profile_error(label, report, errors)
    if not isinstance(report.get("ok"), bool):
        errors.append(f"{label} ok must be boolean")
    if not isinstance(report.get("required"), bool):
        errors.append(f"{label} required must be boolean")
    skipped = report.get("skipped")
    if require_skipped and not isinstance(skipped, bool):
        errors.append(f"{label} skipped must be boolean")
    elif skipped is not None and not isinstance(skipped, bool):
        errors.append(f"{label} skipped must be boolean")
    if require_checks and not isinstance(report.get("checks"), list):
        errors.append(f"{label} checks must be a list")


def _is_absolute_path_text(value: object) -> bool:
    return isinstance(value, str) and value.startswith("/")


def _append_target_agent_hooks_errors(
    agent_hooks: dict[str, object],
    errors: list[str],
) -> None:
    hooks_dir = agent_hooks.get("hooks_dir")
    claude_settings = agent_hooks.get("claude_settings")
    opencode_plugin = agent_hooks.get("opencode_plugin")
    if not _is_absolute_path_text(hooks_dir):
        errors.append("agent_hooks hooks_dir must be an absolute path")
    if not _is_absolute_path_text(claude_settings):
        errors.append("agent_hooks claude_settings must be an absolute path")
    if not _is_absolute_path_text(opencode_plugin):
        errors.append("agent_hooks opencode_plugin must be an absolute path")

    raw_checks = agent_hooks.get("checks")
    if not isinstance(raw_checks, list):
        return

    checks_by_name: dict[str, dict[str, object]] = {}
    for raw_check in raw_checks:
        check = _json_object(raw_check)
        if check is None:
            errors.append("agent_hooks check entry must be an object")
            continue
        name = check.get("name")
        label = name if isinstance(name, str) and name else "<unknown>"
        if not isinstance(name, str) or not name:
            errors.append("agent_hooks check name is required")
        else:
            if name in checks_by_name:
                errors.append(f"agent_hooks duplicate check {name}")
            checks_by_name[name] = check
        if check.get("ok") is not True:
            errors.append(f"agent_hooks check {label} ok must be true")
        if check.get("required") is not True:
            errors.append(f"agent_hooks check {label} required must be true")
        if not isinstance(check.get("detail"), str) or not check.get("detail"):
            errors.append(f"agent_hooks check {label} detail is required")

    for name in TARGET_AGENT_HOOK_REQUIRED_CHECKS:
        check = checks_by_name.get(name)
        if check is None or check.get("ok") is not True:
            errors.append(f"agent_hooks missing ok check {name}")

    hook_script = checks_by_name.get("hook_script")
    if hook_script is not None and _is_absolute_path_text(hooks_dir):
        detail = hook_script.get("detail")
        if (
            not isinstance(detail, str)
            or not detail.startswith(f"{hooks_dir}/")
            or Path(detail).name != "coding-pet-hook.sh"
        ):
            errors.append(
                "agent_hooks check hook_script detail must point to hook script under hooks_dir"
            )

    hook_script_smoke = checks_by_name.get("hook_script_smoke")
    if hook_script_smoke is not None and _is_absolute_path_text(hooks_dir):
        detail = hook_script_smoke.get("detail")
        smoke_path = ""
        if isinstance(detail, str) and ":returncode=" in detail:
            smoke_path = detail.split(":returncode=", 1)[0]
        if not isinstance(detail, str) or not detail.endswith(":returncode=0"):
            errors.append("agent_hooks check hook_script_smoke detail must end with :returncode=0")
        if (
            not smoke_path.startswith(f"{hooks_dir}/")
            or Path(smoke_path).name != "coding-pet-hook.sh"
        ):
            errors.append(
                "agent_hooks check hook_script_smoke detail must point to hook "
                "script under hooks_dir"
            )

    claude_check = checks_by_name.get("claude_settings")
    if claude_check is not None and _is_absolute_path_text(claude_settings):
        if claude_check.get("detail") != claude_settings:
            errors.append("agent_hooks check claude_settings detail must match claude_settings")

    opencode_check = checks_by_name.get("opencode_plugin")
    if opencode_check is not None and _is_absolute_path_text(opencode_plugin):
        if opencode_check.get("detail") != opencode_plugin:
            errors.append("agent_hooks check opencode_plugin detail must match opencode_plugin")


def _resolve_evidence_manifest_path(value: str, evidence_dir: Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path.resolve()
    return (evidence_dir / path).resolve()


def _path_inside(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
    except ValueError:
        return False
    return True


def _expected_evidence_file(evidence_dir: Path, filename: str) -> Path:
    return (evidence_dir / filename).resolve()


def _expected_value_label(value: object) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    if value is None:
        return "null"
    return str(value)


def _append_target_backend_capability_errors(
    report: dict[str, object],
    errors: list[str],
    *,
    agent: str,
    action: str,
) -> None:
    capability = _json_object(report.get("capability"))
    if capability is None:
        errors.append(f"backend_summary missing capability for {agent}:{action}")
        return
    expected = _target_backend_action_capability(action)
    for key in (
        "action",
        "transport",
        "requires_text",
        "press_enter_default",
        "semantics",
    ):
        expected_value = expected.get(key)
        if capability.get(key) != expected_value:
            errors.append(
                f"backend_summary capability {key} for {agent}:{action} must be "
                f"{_expected_value_label(expected_value)}"
            )


def _append_target_backend_summary_errors(
    backend_summary: dict[str, object],
    errors: list[str],
    *,
    evidence_dir: Path,
) -> dict[tuple[str, str], dict[str, object]]:
    backend_summary_reports: dict[tuple[str, str], dict[str, object]] = {}
    if backend_summary.get("schema_version") != EVIDENCE_BUNDLE_SCHEMA_VERSION:
        errors.append(f"backend_summary schema_version must be {EVIDENCE_BUNDLE_SCHEMA_VERSION}")
    if backend_summary.get("profile") != "target":
        errors.append(
            f"backend_summary profile must be target, got {backend_summary.get('profile')!r}"
        )
    if backend_summary.get("ok") is not True:
        errors.append("backend_summary ok must be true")

    generated_at = backend_summary.get("generated_at")
    if not isinstance(generated_at, str):
        errors.append("backend_summary generated_at must be ISO 8601")
    else:
        try:
            datetime.fromisoformat(generated_at)
        except ValueError:
            errors.append("backend_summary generated_at must be ISO 8601")

    output_dir = backend_summary.get("output_dir")
    if not isinstance(output_dir, str) or not output_dir:
        errors.append("backend_summary output_dir is required")
    elif _resolve_evidence_manifest_path(output_dir, evidence_dir) != evidence_dir.resolve():
        errors.append("backend_summary output_dir must match evidence directory")

    reports = backend_summary.get("reports")
    if not isinstance(reports, list):
        errors.append("backend_summary reports must be a list")
        return backend_summary_reports

    expected_keys = {
        (agent.value, action) for agent, action in TARGET_BACKEND_EVIDENCE_REQUIREMENTS
    }
    if len(reports) != len(TARGET_BACKEND_EVIDENCE_REQUIREMENTS):
        errors.append(
            "backend_summary reports must contain exactly "
            f"{len(TARGET_BACKEND_EVIDENCE_REQUIREMENTS)} entries"
        )

    observed_ok: set[tuple[str, str]] = set()
    for raw_report in reports:
        report = _json_object(raw_report)
        if report is None:
            errors.append("backend_summary report entry must be an object")
            continue
        raw_agent = report.get("agent")
        raw_action = report.get("action")
        agent = raw_agent if isinstance(raw_agent, str) else str(raw_agent)
        action = raw_action if isinstance(raw_action, str) else str(raw_action)
        key = (agent, action)
        if report.get("schema_version") != EVIDENCE_BUNDLE_SCHEMA_VERSION:
            errors.append(
                f"backend_summary report {agent}:{action} schema_version must be "
                f"{EVIDENCE_BUNDLE_SCHEMA_VERSION}"
            )
        if report.get("profile") != "target":
            errors.append(f"backend_summary report {agent}:{action} profile must be target")
        if report.get("ok") is not True:
            errors.append(f"backend_summary report {agent}:{action} ok must be true")
        if key in backend_summary_reports:
            errors.append(f"backend_summary duplicate report for {agent}:{action}")
        backend_summary_reports[key] = report
        if key not in expected_keys:
            errors.append(f"backend_summary unexpected report for {agent}:{action}")
            continue
        expected_report_name = _target_backend_report_name(AgentKind(agent), action)
        report_path = report.get("report")
        if not isinstance(report_path, str) or Path(report_path).name != expected_report_name:
            errors.append(
                f"backend_summary report {agent}:{action} must point to {expected_report_name}"
            )
        elif not _path_inside(
            _resolve_evidence_manifest_path(report_path, evidence_dir),
            evidence_dir.resolve(),
        ):
            errors.append(
                f"backend_summary report {agent}:{action} must stay inside evidence directory"
            )
        elif _resolve_evidence_manifest_path(
            report_path,
            evidence_dir,
        ) != _expected_evidence_file(evidence_dir, expected_report_name):
            errors.append(
                f"backend_summary report {agent}:{action} must match evidence file "
                f"{expected_report_name}"
            )
        pane = report.get("pane")
        if not isinstance(pane, str) or not pane:
            errors.append(f"backend_summary report {agent}:{action} pane is required")
        _append_target_backend_capability_errors(
            report,
            errors,
            agent=agent,
            action=action,
        )
        expected_regex = report.get("expected_regex")
        if not isinstance(expected_regex, str) or not expected_regex:
            errors.append(f"backend_summary missing expected_regex for {agent}:{action}")
        else:
            try:
                re.compile(expected_regex, re.MULTILINE | re.DOTALL)
            except re.error as exc:
                errors.append(
                    f"backend_summary expected_regex for {agent}:{action} is invalid: {exc}"
                )
        if report.get("expected_outcome") != ActionOutcome.ACCEPTED.value:
            errors.append(
                f"backend_summary expected_outcome for {agent}:{action} must be "
                f"{ActionOutcome.ACCEPTED.value}"
            )
        if report.get("ok") is True:
            observed_ok.add(key)

    for agent, action in TARGET_BACKEND_EVIDENCE_REQUIREMENTS:
        if (agent.value, action) not in observed_ok:
            errors.append(f"backend_summary missing ok report for {agent.value}:{action}")
    return backend_summary_reports


def _target_backend_control_messages(
    environment: dict[str, object] | None,
) -> dict[str, dict[str, str]]:
    if environment is None:
        return {}
    raw_backends = environment.get("backends")
    if not isinstance(raw_backends, list):
        return {}
    messages: dict[str, dict[str, str]] = {}
    for raw_backend in raw_backends:
        backend = _json_object(raw_backend)
        if backend is None:
            continue
        kind = backend.get("agent_kind")
        raw_control_messages = _json_object(backend.get("control_messages"))
        if not isinstance(kind, str) or raw_control_messages is None:
            continue
        messages[kind] = {
            action: value
            for action, value in (
                ("approve", raw_control_messages.get("approve")),
                ("reject", raw_control_messages.get("reject")),
            )
            if isinstance(value, str)
        }
    return messages


def _summary_artifact_filenames(profile: str) -> dict[str, str]:
    artifacts = {
        "environment": "environment.json",
        "acceptance": f"acceptance-{profile}.json",
        "tmux_control": "tmux-control.json",
        "systemd_units": "systemd-units.json",
        "systemd_runtime": "systemd-runtime.json",
        "widget_smoke": "widget-smoke.json",
        "wheelhouse": "wheelhouse.json",
        "pet_packages": "pet-packages.json",
        "agent_hooks": "agent-hooks.json",
        "hook_event_smoke": "hook-event-smoke.json",
    }
    if profile == "target":
        artifacts.update(_target_backend_artifact_filenames())
    return artifacts


def _append_target_summary_errors(
    summary: dict[str, object],
    errors: list[str],
    *,
    evidence_dir: Path,
) -> None:
    _append_evidence_report_identity_errors("summary", summary, errors)

    output_dir = summary.get("output_dir")
    if not isinstance(output_dir, str) or not output_dir:
        errors.append("summary output_dir is required")
    elif _resolve_evidence_manifest_path(output_dir, evidence_dir) != evidence_dir.resolve():
        errors.append("summary output_dir must match evidence directory")

    artifacts = _json_object(summary.get("artifacts"))
    if artifacts is None:
        errors.append("summary artifacts must be an object")
        return
    for key, filename in _summary_artifact_filenames("target").items():
        value = artifacts.get(key)
        if not isinstance(value, str) or not value:
            errors.append(f"summary artifacts missing {key}")
            continue
        if Path(value).name != filename:
            errors.append(f"summary artifact {key} must point to {filename}")
        elif not _path_inside(
            _resolve_evidence_manifest_path(value, evidence_dir),
            evidence_dir.resolve(),
        ):
            errors.append(f"summary artifact {key} must stay inside evidence directory")
        elif _resolve_evidence_manifest_path(
            value,
            evidence_dir,
        ) != _expected_evidence_file(evidence_dir, filename):
            errors.append(f"summary artifact {key} must match evidence file {filename}")


def _append_evidence_report_identity_errors(
    report_name: str,
    report: dict[str, object],
    errors: list[str],
) -> None:
    if report.get("schema_version") != EVIDENCE_BUNDLE_SCHEMA_VERSION:
        errors.append(f"{report_name} schema_version must be {EVIDENCE_BUNDLE_SCHEMA_VERSION}")

    generated_at = report.get("generated_at")
    if not isinstance(generated_at, str):
        errors.append(f"{report_name} generated_at must be ISO 8601")
    else:
        try:
            datetime.fromisoformat(generated_at)
        except ValueError:
            errors.append(f"{report_name} generated_at must be ISO 8601")


def _append_target_report_profile_error(
    report_name: str,
    report: dict[str, object],
    errors: list[str],
) -> None:
    if report.get("profile") != "target":
        errors.append(f"{report_name} profile must be target, got {report.get('profile')!r}")


def _append_target_systemctl_command_error(
    errors: list[str],
    *,
    label: str,
    report: dict[str, object],
    systemctl_path: object,
    args: list[str],
) -> None:
    command = report.get("command")
    expected_display = "systemctl --user " + " ".join(args)
    if not (
        isinstance(systemctl_path, str)
        and systemctl_path.startswith("/")
        and Path(systemctl_path).name == "systemctl"
    ):
        errors.append(f"systemd_runtime {label} must be {expected_display}")
        return
    expected_command = [systemctl_path, "--user", *args]
    if (
        not isinstance(command, list)
        or not all(isinstance(part, str) for part in command)
        or command != expected_command
    ):
        errors.append(f"systemd_runtime {label} must be {expected_display}")


def _append_widget_surface_sprite_errors(
    *,
    label: str,
    surface: dict[str, object],
    errors: list[str],
) -> None:
    sprite_asset = surface.get("sprite_asset")
    if not isinstance(sprite_asset, str) or not sprite_asset:
        errors.append(f"widget_smoke action_surfaces.{label} sprite_asset is required")
    elif not Path(sprite_asset).is_absolute():
        errors.append(f"widget_smoke action_surfaces.{label} sprite_asset must be an absolute path")
    else:
        _append_removed_legacy_sprite_asset_error(
            f"widget_smoke action_surfaces.{label} sprite_asset",
            sprite_asset,
            errors,
        )


def _append_widget_surface_presentation_errors(
    *,
    label: str,
    surface: dict[str, object],
    errors: list[str],
) -> None:
    presentation = _json_object(surface.get("presentation"))
    if presentation is None:
        errors.append(f"widget_smoke action_surfaces.{label} presentation must be an object")
        return
    if presentation.get("mood") != "alert":
        errors.append(f"widget_smoke action_surfaces.{label} presentation.mood must be alert")
    if not isinstance(presentation.get("bubble_text"), str) or not presentation.get("bubble_text"):
        errors.append(f"widget_smoke action_surfaces.{label} presentation.bubble_text is required")


def _target_evidence_check_report(evidence_dir: Path) -> dict[str, object]:
    errors: list[str] = []
    summary_path = evidence_dir / "summary.json"
    acceptance_path = evidence_dir / "acceptance-target.json"
    environment_path = evidence_dir / "environment.json"
    tmux_control_path = evidence_dir / "tmux-control.json"
    systemd_units_path = evidence_dir / "systemd-units.json"
    systemd_runtime_path = evidence_dir / "systemd-runtime.json"
    widget_smoke_path = evidence_dir / "widget-smoke.json"
    wheelhouse_path = evidence_dir / "wheelhouse.json"
    pet_packages_path = evidence_dir / "pet-packages.json"
    agent_hooks_path = evidence_dir / "agent-hooks.json"
    hook_event_smoke_path = evidence_dir / "hook-event-smoke.json"
    backend_summary_path = evidence_dir / BACKEND_EVIDENCE_SUMMARY_FILENAME

    artifacts: dict[str, str] = {
        "summary": str(summary_path),
        "acceptance": str(acceptance_path),
        "environment": str(environment_path),
        "tmux_control": str(tmux_control_path),
        "systemd_units": str(systemd_units_path),
        "systemd_runtime": str(systemd_runtime_path),
        "widget_smoke": str(widget_smoke_path),
        "wheelhouse": str(wheelhouse_path),
        "pet_packages": str(pet_packages_path),
        "agent_hooks": str(agent_hooks_path),
        "hook_event_smoke": str(hook_event_smoke_path),
        "backend_summary": str(backend_summary_path),
    }

    summary, summary_error = _read_json_object(summary_path)
    if summary_error is not None:
        errors.append(f"summary.json could not be read: {summary_error}")
    elif summary is not None:
        if summary.get("profile") != "target":
            errors.append(f"summary profile must be target, got {summary.get('profile')!r}")
        if summary.get("ok") is not True:
            errors.append("summary ok must be true")
        if summary.get("failed_required") not in ([], None):
            errors.append("summary failed_required must be empty")
        _append_target_summary_errors(summary, errors, evidence_dir=evidence_dir)

    acceptance, acceptance_error = _read_json_object(acceptance_path)
    if acceptance_error is not None:
        errors.append(f"acceptance-target.json could not be read: {acceptance_error}")
    elif acceptance is not None:
        _append_evidence_report_identity_errors("acceptance", acceptance, errors)
        if acceptance.get("profile") != "target":
            errors.append(f"acceptance profile must be target, got {acceptance.get('profile')!r}")
        if acceptance.get("ok") is not True:
            errors.append("acceptance ok must be true")
        if acceptance.get("failed_required") not in ([], None):
            errors.append("acceptance failed_required must be empty")
        _append_target_acceptance_errors(acceptance, errors)

    environment, environment_error = _read_json_object(environment_path)
    if environment_error is not None:
        errors.append(f"environment.json could not be read: {environment_error}")
    elif environment is not None:
        _append_evidence_report_identity_errors("environment", environment, errors)
        if environment.get("profile") != "target":
            errors.append(f"environment profile must be target, got {environment.get('profile')!r}")
        _append_target_environment_errors(environment, errors)

    tmux_control, tmux_error = _read_json_object(tmux_control_path)
    if tmux_error is not None:
        errors.append(f"tmux-control.json could not be read: {tmux_error}")
    elif tmux_control is not None:
        _append_evidence_report_identity_errors("tmux_control", tmux_control, errors)
        _append_target_report_profile_error("tmux_control", tmux_control, errors)
        if tmux_control.get("required") is not True:
            errors.append("tmux_control required must be true")
        if tmux_control.get("ok") is not True:
            errors.append("tmux_control ok must be true")
        if tmux_control.get("skipped") is True:
            errors.append("tmux_control must not be skipped")
        if not isinstance(tmux_control.get("session_name"), str) or not tmux_control.get(
            "session_name"
        ):
            errors.append("tmux_control session_name is required")
        if not isinstance(tmux_control.get("pane_id"), str) or not tmux_control.get("pane_id"):
            errors.append("tmux_control pane_id is required")
        expected_text = tmux_control.get("expected_text")
        if expected_text != DEFAULT_TMUX_CONTROL_CHECK_TEXT:
            errors.append("tmux_control expected_text must match default probe text")
        observed_text = tmux_control.get("observed_text")
        if not isinstance(observed_text, str) or observed_text != expected_text:
            errors.append("tmux_control observed_text must match expected_text")
        if tmux_control.get("detail") != "raw tmux input preserved":
            errors.append("tmux_control detail must be raw tmux input preserved")

    systemd_units, systemd_error = _read_json_object(systemd_units_path)
    if systemd_error is not None:
        errors.append(f"systemd-units.json could not be read: {systemd_error}")
    elif systemd_units is not None:
        _append_evidence_report_identity_errors("systemd_units", systemd_units, errors)
        _append_target_report_profile_error("systemd_units", systemd_units, errors)
        if systemd_units.get("required") is not True:
            errors.append("systemd_units required must be true")
        if systemd_units.get("ok") is not True:
            errors.append("systemd_units ok must be true")
        if systemd_units.get("skipped") is True:
            errors.append("systemd_units must not be skipped")
        raw_systemd_unit_paths = systemd_units.get("units")
        systemd_unit_paths: list[str] = []
        if not isinstance(raw_systemd_unit_paths, list):
            errors.append("systemd_units units must be a list")
        else:
            required_systemd_unit_names = set(SYSTEMD_UNIT_NAMES)
            seen_systemd_unit_names: set[str] = set()
            raw_systemd_unit_names: list[str] = []
            unit_paths_by_name: dict[str, str] = {}
            systemd_unit_names: set[str] = set()
            for raw_path in raw_systemd_unit_paths:
                if not isinstance(raw_path, str) or not raw_path.startswith("/"):
                    errors.append("systemd_units units must be absolute paths")
                    continue
                unit_name = Path(raw_path).name
                systemd_unit_paths.append(raw_path)
                raw_systemd_unit_names.append(unit_name)
                unit_paths_by_name.setdefault(unit_name, raw_path)
                if unit_name in seen_systemd_unit_names:
                    errors.append(f"systemd_units duplicate unit {unit_name}")
                seen_systemd_unit_names.add(unit_name)
                if unit_name not in required_systemd_unit_names:
                    errors.append(f"systemd_units unexpected unit {unit_name}")
                systemd_unit_names.add(unit_name)
            if (
                len(raw_systemd_unit_names) != len(SYSTEMD_UNIT_NAMES)
                or systemd_unit_names != required_systemd_unit_names
            ):
                errors.append(
                    "systemd_units units must contain exactly " + ", ".join(SYSTEMD_UNIT_NAMES)
                )
            for unit_name in SYSTEMD_UNIT_NAMES:
                if unit_name not in systemd_unit_names:
                    errors.append(f"systemd_units missing unit {unit_name}")
        raw_systemd_command = systemd_units.get("command")
        if not isinstance(raw_systemd_command, list) or not all(
            isinstance(part, str) for part in raw_systemd_command
        ):
            errors.append("systemd_units command must be a list")
        else:
            systemd_command = [part for part in raw_systemd_command if isinstance(part, str)]
            if (
                not systemd_command
                or not systemd_command[0].startswith("/")
                or Path(systemd_command[0]).name != "systemd-analyze"
            ):
                errors.append("systemd_units command must start with absolute systemd-analyze path")
            if len(systemd_command) < 3 or systemd_command[1:3] != [
                "--user",
                "verify",
            ]:
                errors.append("systemd_units command must include --user verify")
            elif all(unit_name in unit_paths_by_name for unit_name in SYSTEMD_UNIT_NAMES):
                expected_unit_paths = [
                    unit_paths_by_name[unit_name] for unit_name in SYSTEMD_UNIT_NAMES
                ]
                if systemd_command != [
                    systemd_command[0],
                    "--user",
                    "verify",
                    *expected_unit_paths,
                ]:
                    errors.append("systemd_units command must match verified units")
            elif systemd_command[3:] != systemd_unit_paths:
                errors.append("systemd_units command must match verified units")
            for unit_path in systemd_unit_paths:
                if unit_path not in systemd_command[3:]:
                    errors.append(f"systemd_units command missing unit {Path(unit_path).name}")
        if systemd_units.get("returncode") != 0:
            errors.append("systemd_units returncode must be 0")

    systemd_runtime: dict[str, object] | None = None
    systemd_runtime, systemd_runtime_error = _read_json_object(systemd_runtime_path)
    if systemd_runtime_error is not None:
        errors.append(f"systemd-runtime.json could not be read: {systemd_runtime_error}")
    elif systemd_runtime is not None:
        _append_evidence_report_identity_errors(
            "systemd_runtime",
            systemd_runtime,
            errors,
        )
        _append_target_report_profile_error("systemd_runtime", systemd_runtime, errors)
        if systemd_runtime.get("required") is not True:
            errors.append("systemd_runtime required must be true")
        if systemd_runtime.get("ok") is not True:
            errors.append("systemd_runtime ok must be true")
        if systemd_runtime.get("skipped") is True:
            errors.append("systemd_runtime must not be skipped")
        systemctl_path = systemd_runtime.get("systemctl")
        if (
            not isinstance(systemctl_path, str)
            or not systemctl_path.startswith("/")
            or Path(systemctl_path).name != "systemctl"
        ):
            errors.append("systemd_runtime systemctl must be an absolute systemctl path")
        session_environment = _json_object(systemd_runtime.get("session_environment"))
        if session_environment is None:
            errors.append("systemd_runtime session_environment must be an object")
        else:
            if session_environment.get("has_xdg_runtime_dir") is not True:
                errors.append("systemd_runtime session_environment.XDG_RUNTIME_DIR must be present")
            else:
                xdg_runtime_dir = session_environment.get("XDG_RUNTIME_DIR")
                if not isinstance(xdg_runtime_dir, str) or not xdg_runtime_dir.startswith(
                    "/run/user/"
                ):
                    errors.append(
                        "systemd_runtime session_environment.XDG_RUNTIME_DIR "
                        "value must be an absolute /run/user path"
                    )
            if (
                session_environment.get("has_display") is not True
                and session_environment.get("has_wayland_display") is not True
            ):
                errors.append(
                    "systemd_runtime session_environment DISPLAY or WAYLAND_DISPLAY must be present"
                )
            else:
                display = session_environment.get("DISPLAY")
                wayland_display = session_environment.get("WAYLAND_DISPLAY")
                has_display_value = (
                    session_environment.get("has_display") is True
                    and isinstance(display, str)
                    and bool(display)
                )
                has_wayland_value = (
                    session_environment.get("has_wayland_display") is True
                    and isinstance(wayland_display, str)
                    and bool(wayland_display)
                )
                if not has_display_value and not has_wayland_value:
                    errors.append(
                        "systemd_runtime session_environment DISPLAY or "
                        "WAYLAND_DISPLAY value must be recorded"
                    )
            if session_environment.get("has_dbus_session_bus") is not True:
                errors.append(
                    "systemd_runtime session_environment DBUS_SESSION_BUS_ADDRESS must be present"
                )
            else:
                dbus_session_bus = session_environment.get("DBUS_SESSION_BUS_ADDRESS")
                if not isinstance(dbus_session_bus, str) or "/run/user/" not in dbus_session_bus:
                    errors.append(
                        "systemd_runtime session_environment.DBUS_SESSION_BUS_ADDRESS "
                        "value must use /run/user bus"
                    )
        user_manager = _json_object(systemd_runtime.get("user_manager"))
        if user_manager is None or user_manager.get("ok") is not True:
            errors.append("systemd_runtime user manager must be reachable")
        elif user_manager.get("returncode") != 0:
            errors.append("systemd_runtime user manager returncode must be 0")
        if user_manager is not None:
            _append_target_systemctl_command_error(
                errors,
                label="user_manager.command",
                report=user_manager,
                systemctl_path=systemctl_path,
                args=["status"],
            )
        target_enabled = _json_object(systemd_runtime.get("target_enabled"))
        if target_enabled is None or target_enabled.get("ok") is not True:
            errors.append("systemd_runtime target coding-pet.target must be enabled")
        else:
            if target_enabled.get("returncode") != 0:
                errors.append("systemd_runtime target_enabled.returncode must be 0")
            if target_enabled.get("unit") != "coding-pet.target":
                errors.append("systemd_runtime target_enabled.unit must be coding-pet.target")
            if target_enabled.get("state") != "enabled":
                errors.append("systemd_runtime target coding-pet.target state must be enabled")
            _append_target_systemctl_command_error(
                errors,
                label="target_enabled.command",
                report=target_enabled,
                systemctl_path=systemctl_path,
                args=["is-enabled", "coding-pet.target"],
            )
        raw_units = systemd_runtime.get("units")
        if not isinstance(raw_units, list):
            errors.append("systemd_runtime units must be a list")
        else:
            required_unit_names = set(SYSTEMD_RUNTIME_UNIT_NAMES)
            seen_unit_names: set[str] = set()
            units_by_name: dict[str, dict[str, object]] = {}
            raw_unit_names: list[str] = []
            for raw_unit in raw_units:
                unit = _json_object(raw_unit)
                if unit is None:
                    errors.append("systemd_runtime unit entries must be objects")
                    continue
                raw_unit_name = unit.get("unit")
                if not isinstance(raw_unit_name, str) or not raw_unit_name:
                    errors.append("systemd_runtime unit entries must include unit names")
                    continue
                unit_name = raw_unit_name
                raw_unit_names.append(unit_name)
                if unit_name in seen_unit_names:
                    errors.append(f"systemd_runtime duplicate unit {unit_name}")
                seen_unit_names.add(unit_name)
                if unit_name not in required_unit_names:
                    errors.append(f"systemd_runtime unexpected unit {unit_name}")
                units_by_name.setdefault(unit_name, unit)
            if (
                len(raw_unit_names) != len(SYSTEMD_RUNTIME_UNIT_NAMES)
                or set(raw_unit_names) != required_unit_names
            ):
                errors.append(
                    "systemd_runtime units must contain exactly "
                    + ", ".join(SYSTEMD_RUNTIME_UNIT_NAMES)
                )
            for unit_name in SYSTEMD_RUNTIME_UNIT_NAMES:
                unit = units_by_name.get(unit_name)
                if unit is None:
                    errors.append(f"systemd_runtime missing unit {unit_name}")
                    continue
                if unit.get("ok") is not True or unit.get("state") != "active":
                    errors.append(f"systemd_runtime unit {unit_name} must be active")
                if unit.get("returncode") != 0:
                    errors.append(f"systemd_runtime unit {unit_name} returncode must be 0")
                _append_target_systemctl_command_error(
                    errors,
                    label=f"unit {unit_name} command",
                    report=unit,
                    systemctl_path=systemctl_path,
                    args=["is-active", unit_name],
                )

    widget_smoke: dict[str, object] | None = None
    widget_smoke, widget_smoke_error = _read_json_object(widget_smoke_path)
    if widget_smoke_error is not None:
        errors.append(f"widget-smoke.json could not be read: {widget_smoke_error}")
    elif widget_smoke is not None:
        _append_evidence_report_identity_errors("widget_smoke", widget_smoke, errors)
        _append_target_report_profile_error("widget_smoke", widget_smoke, errors)
        if widget_smoke.get("required") is not True:
            errors.append("widget_smoke required must be true")
        if widget_smoke.get("ok") is not True:
            errors.append("widget_smoke ok must be true")
        if widget_smoke.get("skipped") is True:
            errors.append("widget_smoke must not be skipped")
        if widget_smoke.get("gui_runtime") != "available":
            errors.append("widget_smoke gui_runtime must be available")
        if widget_smoke.get("gui_validated") is not True:
            errors.append("widget_smoke gui_validated must be true")
        if not isinstance(widget_smoke.get("theme"), str) or not widget_smoke.get("theme"):
            errors.append("widget_smoke theme is required")
        else:
            _append_removed_legacy_theme_name_error(
                "widget_smoke theme",
                widget_smoke.get("theme"),
                errors,
            )
            environment_theme = (
                _json_object(environment.get("theme")) if environment is not None else None
            )
            environment_theme_name = (
                environment_theme.get("name") if environment_theme is not None else None
            )
            if (
                isinstance(environment_theme_name, str)
                and environment_theme_name
                and widget_smoke.get("theme") != environment_theme_name
            ):
                errors.append("widget_smoke theme must match environment theme")
        if widget_smoke.get("theme_ok") is not True:
            errors.append("widget_smoke theme_ok must be true")
        if widget_smoke.get("shell_created") is not True:
            errors.append("widget_smoke shell_created must be true")
        if widget_smoke.get("qt_widget_created") is not True:
            errors.append("widget_smoke qt_widget_created must be true")
        sprite_asset = widget_smoke.get("sprite_asset")
        if not isinstance(sprite_asset, str) or not sprite_asset:
            errors.append("widget_smoke sprite_asset is required")
        elif not Path(sprite_asset).is_absolute():
            errors.append("widget_smoke sprite_asset must be an absolute path")
        else:
            _append_removed_legacy_sprite_asset_error(
                "widget_smoke sprite_asset",
                sprite_asset,
                errors,
            )
        raw_available_actions = widget_smoke.get("available_actions")
        if not isinstance(raw_available_actions, list):
            errors.append("widget_smoke available_actions must be a list")
        else:
            available_actions = {str(action) for action in raw_available_actions}
            if not {"approve", "reject"}.issubset(available_actions):
                errors.append("widget_smoke available_actions must include approve and reject")
        presentation = _json_object(widget_smoke.get("presentation"))
        if presentation is None:
            errors.append("widget_smoke presentation must be an object")
        else:
            if presentation.get("mood") != "alert":
                errors.append("widget_smoke presentation.mood must be alert")
            if not isinstance(presentation.get("bubble_text"), str) or not presentation.get(
                "bubble_text"
            ):
                errors.append("widget_smoke presentation.bubble_text is required")
        action_surfaces = _json_object(widget_smoke.get("action_surfaces"))
        if action_surfaces is None:
            errors.append("widget_smoke action_surfaces must be an object")
        else:
            permission_surface = _json_object(action_surfaces.get("needs_permission"))
            if permission_surface is None:
                errors.append("widget_smoke action_surfaces.needs_permission is required")
            else:
                _append_widget_surface_sprite_errors(
                    label="needs_permission",
                    surface=permission_surface,
                    errors=errors,
                )
                _append_widget_surface_presentation_errors(
                    label="needs_permission",
                    surface=permission_surface,
                    errors=errors,
                )
                permission_actions = permission_surface.get("available_actions")
                if not isinstance(permission_actions, list) or not {
                    "approve",
                    "reject",
                }.issubset({str(action) for action in permission_actions}):
                    errors.append(
                        "widget_smoke action_surfaces.needs_permission "
                        "available_actions must include approve and reject"
                    )
            input_surface = _json_object(action_surfaces.get("needs_input"))
            if input_surface is None:
                errors.append("widget_smoke action_surfaces.needs_input is required")
            else:
                _append_widget_surface_sprite_errors(
                    label="needs_input",
                    surface=input_surface,
                    errors=errors,
                )
                input_actions = input_surface.get("available_actions")
                if not isinstance(input_actions, list) or "send_reply" not in {
                    str(action) for action in input_actions
                }:
                    errors.append(
                        "widget_smoke action_surfaces.needs_input "
                        "available_actions must include send_reply"
                    )
                reply_shortcuts = input_surface.get("reply_shortcuts")
                if not isinstance(reply_shortcuts, list) or not reply_shortcuts:
                    errors.append(
                        "widget_smoke action_surfaces.needs_input reply_shortcuts is required"
                    )
                _append_widget_surface_presentation_errors(
                    label="needs_input",
                    surface=input_surface,
                    errors=errors,
                )

    hook_event_smoke: dict[str, object] | None = None
    hook_event_smoke, hook_event_smoke_error = _read_json_object(hook_event_smoke_path)
    if hook_event_smoke_error is not None:
        errors.append(f"hook-event-smoke.json could not be read: {hook_event_smoke_error}")
    elif hook_event_smoke is not None:
        _append_evidence_report_identity_errors(
            "hook_event_smoke",
            hook_event_smoke,
            errors,
        )
        _append_target_report_profile_error("hook_event_smoke", hook_event_smoke, errors)
        if hook_event_smoke.get("required") is not True:
            errors.append("hook_event_smoke required must be true")
        if hook_event_smoke.get("ok") is not True:
            errors.append("hook_event_smoke ok must be true")
        if hook_event_smoke.get("skipped") is True:
            errors.append("hook_event_smoke must not be skipped")
        hook_errors = hook_event_smoke.get("errors")
        if not isinstance(hook_errors, list) or hook_errors:
            errors.append("hook_event_smoke errors must be empty")
        socket_path = hook_event_smoke.get("socket_path")
        if not isinstance(socket_path, str) or not socket_path:
            errors.append("hook_event_smoke socket_path is required")
        else:
            hook_socket_path = Path(socket_path)
            if not hook_socket_path.is_absolute():
                errors.append("hook_event_smoke socket_path must be an absolute path")
            else:
                if hook_socket_path.name != "coding-pet.sock":
                    errors.append("hook_event_smoke socket_path must point to coding-pet.sock")
                environment_paths = (
                    _json_object(environment.get("paths")) if environment is not None else None
                )
                runtime_dir = (
                    environment_paths.get("runtime_dir") if environment_paths is not None else None
                )
                if (
                    isinstance(runtime_dir, str)
                    and runtime_dir
                    and hook_socket_path.parent.resolve() != Path(runtime_dir).resolve()
                ):
                    errors.append(
                        "hook_event_smoke socket_path must be under environment runtime_dir"
                    )
        expected_hook_result_session_id: str | None = None
        event = _json_object(hook_event_smoke.get("event"))
        if event is None:
            errors.append("hook_event_smoke event must be an object")
        else:
            raw_event_agent = event.get("agent")
            if raw_event_agent not in {
                AgentKind.CLAUDE_CODE.value,
                AgentKind.OPENCODE.value,
            }:
                errors.append("hook_event_smoke event.agent must be claude_code or opencode")
            if event.get("event") != HOOK_EVENT_SMOKE_EVENT:
                errors.append(f"hook_event_smoke event.event must be {HOOK_EVENT_SMOKE_EVENT}")
            if not isinstance(event.get("session_id"), str) or not event.get("session_id"):
                errors.append("hook_event_smoke event.session_id is required")
            elif event.get("session_id") != HOOK_EVENT_SMOKE_SESSION_ID:
                errors.append(
                    f"hook_event_smoke event.session_id must be {HOOK_EVENT_SMOKE_SESSION_ID}"
                )
            elif raw_event_agent in {
                AgentKind.CLAUDE_CODE.value,
                AgentKind.OPENCODE.value,
            }:
                expected_hook_result_session_id = hook_session_id(
                    agent_kind=AgentKind(raw_event_agent),
                    raw_session_id=HOOK_EVENT_SMOKE_SESSION_ID,
                    workspace=str(event.get("workspace") or ""),
                )
            workspace = event.get("workspace")
            if not isinstance(workspace, str) or not workspace:
                errors.append("hook_event_smoke event.workspace is required")
            else:
                workspace_path = Path(workspace)
                if not workspace_path.is_absolute():
                    errors.append("hook_event_smoke event.workspace must be an absolute path")
                elif workspace_path.resolve() != evidence_dir.resolve():
                    errors.append("hook_event_smoke event.workspace must match evidence directory")
        hook_result_session_id: object = None
        hook_result = _json_object(hook_event_smoke.get("hook_result"))
        if hook_result is None:
            errors.append("hook_event_smoke hook_result must be an object")
        else:
            if hook_result.get("ok") is not True:
                errors.append("hook_event_smoke hook_result.ok must be true")
            if hook_result.get("state") != "running":
                errors.append("hook_event_smoke hook_result.state must be running")
            hook_result_session_id = hook_result.get("session_id")
            if not isinstance(hook_result_session_id, str) or not hook_result_session_id:
                errors.append("hook_event_smoke hook_result.session_id is required")
            elif (
                expected_hook_result_session_id is not None
                and hook_result_session_id != expected_hook_result_session_id
            ):
                errors.append(
                    "hook_event_smoke hook_result.session_id must match "
                    f"{expected_hook_result_session_id}"
                )
        transcript = _json_object(hook_event_smoke.get("transcript"))
        if transcript is None:
            errors.append("hook_event_smoke transcript must be an object")
        else:
            if transcript.get("enabled") is not True:
                errors.append("hook_event_smoke transcript.enabled must be true")
            if transcript.get("verified") is not True:
                errors.append("hook_event_smoke transcript.verified must be true")
            transcript_db_path = transcript.get("db_path")
            if not isinstance(transcript_db_path, str) or not transcript_db_path:
                errors.append("hook_event_smoke transcript.db_path is required")
            else:
                transcript_db = Path(transcript_db_path)
                if not transcript_db.is_absolute():
                    errors.append("hook_event_smoke transcript.db_path must be an absolute path")
                else:
                    environment_transcript = (
                        _json_object(environment.get("transcript"))
                        if environment is not None
                        else None
                    )
                    environment_db_path = (
                        environment_transcript.get("db_path")
                        if environment_transcript is not None
                        else None
                    )
                    if (
                        isinstance(environment_db_path, str)
                        and environment_db_path
                        and transcript_db.resolve() != Path(environment_db_path).resolve()
                    ):
                        errors.append(
                            "hook_event_smoke transcript.db_path must match "
                            "environment transcript.db_path"
                        )
            transcript_session_id = transcript.get("session_id")
            if not isinstance(transcript_session_id, str) or not transcript_session_id:
                errors.append("hook_event_smoke transcript.session_id is required")
            elif (
                isinstance(hook_result_session_id, str)
                and hook_result_session_id
                and transcript_session_id != hook_result_session_id
            ):
                errors.append(
                    "hook_event_smoke transcript.session_id must match hook_result.session_id"
                )
            event_count = transcript.get("events")
            if not _is_plain_int(event_count) or event_count <= 0:
                errors.append("hook_event_smoke transcript.events must be positive")
        cleanup_result = _json_object(hook_event_smoke.get("cleanup_result"))
        if cleanup_result is None:
            errors.append("hook_event_smoke cleanup_result must be an object")
        else:
            if cleanup_result.get("ok") is not True:
                errors.append("hook_event_smoke cleanup_result.ok must be true")
            if cleanup_result.get("outcome") != ActionOutcome.LOCAL_UPDATED.value:
                errors.append(
                    "hook_event_smoke cleanup_result.outcome must be "
                    f"{ActionOutcome.LOCAL_UPDATED.value}"
                )
            if cleanup_result.get("action") != "hide_pet":
                errors.append("hook_event_smoke cleanup_result.action must be hide_pet")
            if cleanup_result.get("reason") != "hidden":
                errors.append("hook_event_smoke cleanup_result.reason must be hidden")
            cleanup_detail = cleanup_result.get("detail")
            if not isinstance(cleanup_detail, str) or not cleanup_detail:
                errors.append("hook_event_smoke cleanup_result.detail is required")
            cleanup_session_id = cleanup_result.get("session_id")
            if not isinstance(cleanup_session_id, str) or not cleanup_session_id:
                errors.append("hook_event_smoke cleanup_result.session_id is required")
            elif (
                isinstance(hook_result_session_id, str)
                and hook_result_session_id
                and cleanup_session_id != hook_result_session_id
            ):
                errors.append(
                    "hook_event_smoke cleanup_result.session_id must match hook_result.session_id"
                )

    wheelhouse: dict[str, object] | None = None
    wheelhouse, wheelhouse_error = _read_json_object(wheelhouse_path)
    if wheelhouse_error is not None:
        errors.append(f"wheelhouse.json could not be read: {wheelhouse_error}")
    elif wheelhouse is not None:
        _append_target_report_status_errors(
            "wheelhouse",
            wheelhouse,
            errors,
            require_skipped=True,
        )
        if wheelhouse.get("required") is True:
            if wheelhouse.get("ok") is not True:
                errors.append("wheelhouse ok must be true")
            if wheelhouse.get("skipped") is True:
                errors.append("wheelhouse must not be skipped")
            _append_target_wheelhouse_errors(wheelhouse, errors)

    pet_packages: dict[str, object] | None = None
    pet_packages, pet_packages_error = _read_json_object(pet_packages_path)
    if pet_packages_error is not None:
        errors.append(f"pet-packages.json could not be read: {pet_packages_error}")
    elif pet_packages is not None:
        _append_target_report_status_errors(
            "pet_packages",
            pet_packages,
            errors,
            require_skipped=True,
        )
        if pet_packages.get("required") is True:
            if pet_packages.get("ok") is not True:
                errors.append("pet_packages ok must be true")
            if pet_packages.get("skipped") is True:
                errors.append("pet_packages must not be skipped")
            _append_target_pet_package_errors(pet_packages, errors)

    agent_hooks: dict[str, object] | None = None
    agent_hooks, agent_hooks_error = _read_json_object(agent_hooks_path)
    if agent_hooks_error is not None:
        errors.append(f"agent-hooks.json could not be read: {agent_hooks_error}")
    elif agent_hooks is not None:
        _append_target_report_status_errors(
            "agent_hooks",
            agent_hooks,
            errors,
            require_checks=True,
        )
        if agent_hooks.get("required") is True:
            if agent_hooks.get("ok") is not True:
                errors.append("agent_hooks ok must be true")
            _append_target_agent_hooks_errors(agent_hooks, errors)

    backend_summary: dict[str, object] | None = None
    backend_summary_reports: dict[tuple[str, str], dict[str, object]] = {}
    if not backend_summary_path.exists():
        errors.append(f"missing backend evidence summary: {BACKEND_EVIDENCE_SUMMARY_FILENAME}")
    else:
        backend_summary, backend_summary_error = _read_json_object(backend_summary_path)
        if backend_summary_error is not None:
            errors.append(
                f"{BACKEND_EVIDENCE_SUMMARY_FILENAME} could not be read: {backend_summary_error}"
            )
        elif backend_summary is not None:
            backend_summary_reports = _append_target_backend_summary_errors(
                backend_summary,
                errors,
                evidence_dir=evidence_dir,
            )

    backend_control_messages = _target_backend_control_messages(environment)
    backend_reports: list[dict[str, object]] = []
    backend_evidence_hash_pairs: dict[tuple[str, str], str] = {}
    for agent, action in TARGET_BACKEND_EVIDENCE_REQUIREMENTS:
        report_name = _target_backend_report_name(agent, action)
        report_path = evidence_dir / report_name
        artifacts[f"backend_{agent.value}_{action}"] = str(report_path)
        if not report_path.exists():
            errors.append(f"missing backend evidence: {report_name}")
            continue
        backend_check = _backend_evidence_check_report(
            report_path,
            expected_agent=agent,
            expected_action=action,
        )
        backend_reports.append(backend_check)
        backend_errors = backend_check.get("errors")
        if isinstance(backend_errors, list):
            for error in backend_errors:
                errors.append(f"{report_name}: {error}")
        backend_evidence = _json_object(backend_check.get("evidence"))
        if backend_evidence is not None:
            before_hash = backend_evidence.get("before_hash")
            after_hash = backend_evidence.get("after_hash")
            if _is_sha256_hex(before_hash) and _is_sha256_hex(after_hash):
                hash_pair = (str(before_hash), str(after_hash))
                first_report_name = backend_evidence_hash_pairs.get(hash_pair)
                if first_report_name is not None:
                    errors.append(
                        f"{report_name}: backend evidence hash pair must be "
                        "unique across target bundle"
                    )
                else:
                    backend_evidence_hash_pairs[hash_pair] = report_name
        summary_report = backend_summary_reports.get((agent.value, action))
        expected_delivered_text = None
        if summary_report is not None:
            summary_pane = summary_report.get("pane")
            report_pane = backend_check.get("pane")
            if (
                isinstance(summary_pane, str)
                and summary_pane
                and isinstance(report_pane, str)
                and report_pane
                and summary_pane != report_pane
            ):
                errors.append(f"{report_name}: pane must match backend_summary pane")
            summary_expected_regex = summary_report.get("expected_regex")
            report_expected_regex = (
                backend_evidence.get("expected_regex") if backend_evidence is not None else None
            )
            if (
                isinstance(summary_expected_regex, str)
                and summary_expected_regex
                and report_expected_regex != summary_expected_regex
            ):
                errors.append(
                    f"{report_name}: expected_regex must match backend_summary expected_regex"
                )
            raw_expected_delivered_text = summary_report.get("expected_delivered_text")
            if not isinstance(raw_expected_delivered_text, str) or not raw_expected_delivered_text:
                errors.append(
                    f"backend_summary missing expected_delivered_text for {agent.value}:{action}"
                )
            else:
                expected_delivered_text = raw_expected_delivered_text
            summary_capability = _json_object(summary_report.get("capability"))
            report_capability = _json_object(backend_check.get("capability"))
            if (
                summary_capability is not None
                and report_capability is not None
                and report_capability != summary_capability
            ):
                errors.append(f"{report_name}: capability must match backend_summary capability")
        action_result = _json_object(backend_check.get("action_result"))
        delivered_text = action_result.get("delivered_text") if action_result is not None else None
        if action_result is not None:
            summary_expected_outcome = (
                summary_report.get("expected_outcome") if summary_report is not None else None
            )
            if (
                isinstance(summary_expected_outcome, str)
                and action_result.get("outcome") != summary_expected_outcome
            ):
                errors.append(
                    f"{report_name}: action_result.outcome must match "
                    "backend_summary expected_outcome"
                )
            if action_result.get("action") != action:
                errors.append(f"{report_name}: action_result.action must be {action}")
            action_session_id = action_result.get("session_id")
            if not isinstance(action_session_id, str) or not action_session_id:
                errors.append(f"{report_name}: action_result.session_id is required")
            elif isinstance(report_pane, str) and report_pane:
                expected_session_id = f"tmux-{report_pane}"
                if action_session_id != expected_session_id:
                    errors.append(
                        f"{report_name}: action_result.session_id must match tmux pane session id"
                    )
        if isinstance(expected_delivered_text, str) and delivered_text != expected_delivered_text:
            errors.append(
                f"{report_name}: delivered_text must match backend_summary expected_delivered_text"
            )
        if action in {"approve", "reject"}:
            expected_message = backend_control_messages.get(agent.value, {}).get(action)
            if isinstance(expected_message, str) and delivered_text != expected_message:
                errors.append(
                    f"{report_name}: delivered_text must match environment "
                    f"{agent.value} {action} control message"
                )

    return {
        "ok": not errors,
        "evidence_dir": str(evidence_dir),
        "errors": errors,
        "artifacts": artifacts,
        "agent_hooks": agent_hooks,
        "hook_event_smoke": hook_event_smoke,
        "systemd_runtime": systemd_runtime,
        "widget_smoke": widget_smoke,
        "wheelhouse": wheelhouse,
        "pet_packages": pet_packages,
        "backend_summary": backend_summary,
        "backend_reports": backend_reports,
    }


def _evidence_bundle_summary(
    *,
    profile: str,
    output_dir: Path,
    acceptance: dict[str, object],
    environment_path: Path,
    acceptance_path: Path,
    tmux_control_path: Path,
    tmux_control: dict[str, object],
    systemd_units_path: Path,
    systemd_units: dict[str, object],
    systemd_runtime_path: Path,
    systemd_runtime: dict[str, object],
    widget_smoke_path: Path,
    widget_smoke: dict[str, object],
    wheelhouse_path: Path,
    wheelhouse: dict[str, object],
    pet_packages_path: Path,
    pet_packages: dict[str, object],
    agent_hooks_path: Path,
    agent_hooks: dict[str, object],
    hook_event_smoke_path: Path,
    hook_event_smoke: dict[str, object],
) -> dict[str, object]:
    raw_failed_required = acceptance.get("failed_required", [])
    failed_required = (
        [str(item) for item in raw_failed_required] if isinstance(raw_failed_required, list) else []
    )
    if tmux_control.get("required") is True and tmux_control.get("ok") is not True:
        failed_required.append("tmux_control")
    if systemd_units.get("required") is True and systemd_units.get("ok") is not True:
        failed_required.append("systemd_units")
    if systemd_runtime.get("required") is True and systemd_runtime.get("ok") is not True:
        failed_required.append("systemd_runtime")
    if widget_smoke.get("required") is True and widget_smoke.get("ok") is not True:
        failed_required.append("widget_smoke")
    if wheelhouse.get("required") is True and wheelhouse.get("ok") is not True:
        failed_required.append("wheelhouse")
    if pet_packages.get("required") is True and pet_packages.get("ok") is not True:
        failed_required.append("pet_packages")
    if agent_hooks.get("required") is True and agent_hooks.get("ok") is not True:
        failed_required.append("agent_hooks")
    if hook_event_smoke.get("required") is True and hook_event_smoke.get("ok") is not True:
        failed_required.append("hook_event_smoke")
    artifacts = {
        "environment": str(environment_path),
        "acceptance": str(acceptance_path),
        "tmux_control": str(tmux_control_path),
        "systemd_units": str(systemd_units_path),
        "systemd_runtime": str(systemd_runtime_path),
        "widget_smoke": str(widget_smoke_path),
        "wheelhouse": str(wheelhouse_path),
        "pet_packages": str(pet_packages_path),
        "agent_hooks": str(agent_hooks_path),
        "hook_event_smoke": str(hook_event_smoke_path),
    }
    if profile == "target":
        artifacts.update(_target_backend_artifact_paths(output_dir))
    return {
        "schema_version": EVIDENCE_BUNDLE_SCHEMA_VERSION,
        "ok": not failed_required,
        "profile": profile,
        "output_dir": str(output_dir),
        "generated_at": datetime.now(UTC).isoformat(),
        "failed_required": failed_required,
        "artifacts": artifacts,
    }


def _pet_validation_report(pet: object) -> dict[str, object]:
    from coding_pet.gui.theme import CodexPetPackage

    if not isinstance(pet, CodexPetPackage):
        return {"ok": False, "error": "invalid pet validation object"}
    sheet = pet.manifest.spritesheet
    atlas = pet.atlas_validation
    return {
        "ok": True,
        "theme_id": pet.theme_id,
        "display_name": pet.display_name,
        "theme_format": "codex_pet",
        "package_root": str(pet.package_root),
        "manifest": str(pet.manifest_path),
        "spritesheet": pet.spritesheet_path.as_posix(),
        "atlas_size": {
            "width": pet.image_size[0],
            "height": pet.image_size[1],
        },
        "atlas_grid": None
        if sheet is None
        else {
            "columns": sheet.columns,
            "rows": sheet.rows,
        },
        "frame_size": None
        if sheet is None
        else {
            "width": sheet.frame_width,
            "height": sheet.frame_height,
        },
        "frame_counts_by_row": {}
        if sheet is None
        else {str(row): count for row, count in sorted(sheet.frame_count_by_row.items())},
        "frame_durations_by_row": {}
        if sheet is None
        else {
            str(row): list(durations)
            for row, durations in sorted(sheet.frame_duration_by_row.items())
        },
        "mood_rows": {}
        if sheet is None
        else {
            mood.value: row
            for mood, row in sorted(sheet.row_by_mood.items(), key=lambda item: item[0].value)
        },
        "atlas_cells": None
        if atlas is None
        else {
            "ok": atlas.ok,
            "errors": list(atlas.errors),
            "warnings": list(atlas.warnings),
            "transparent_rgb_residue_pixels": atlas.transparent_rgb_residue_pixels,
        },
    }


def _download_url_bytes(url: str, *, timeout_s: float) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": PETDEX_USER_AGENT},
    )
    with urllib.request.urlopen(request, timeout=timeout_s) as response:
        payload = response.read()
    if isinstance(payload, bytes):
        return payload
    return bytes(payload)


def _download_url_json_object(url: str, *, timeout_s: float) -> dict[str, object]:
    raw = json.loads(_download_url_bytes(url, timeout_s=timeout_s).decode("utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Petdex manifest must be a JSON object")
    return {str(key): value for key, value in raw.items()}


def _safe_petdex_slug(value: str) -> str:
    slug = value.strip()
    if not SAFE_PETDEX_SLUG.fullmatch(slug):
        raise ValueError(f"Petdex slug must be a safe file name: {value}")
    return slug


def _petdex_manifest_pets(manifest: dict[str, object]) -> list[dict[str, object]]:
    pets = manifest.get("pets")
    if not isinstance(pets, list):
        raise ValueError("Petdex manifest must contain a pets list")
    normalized: list[dict[str, object]] = []
    for entry in pets:
        if isinstance(entry, dict):
            normalized.append({str(key): value for key, value in entry.items()})
    return normalized


def _find_petdex_manifest_entry(
    manifest: dict[str, object],
    *,
    slug: str,
) -> dict[str, object]:
    for entry in _petdex_manifest_pets(manifest):
        if str(entry.get("slug") or "") == slug:
            return entry
    raise ValueError(f"Petdex pet slug not found: {slug}")


def _optional_url_field(entry: dict[str, object], field: str) -> str | None:
    value = entry.get(field)
    if isinstance(value, str) and value.strip():
        return value
    return None


def _download_petdex_report(
    *,
    slug: str,
    output_dir: Path,
    manifest_url: str,
    replace: bool,
    timeout_s: float,
) -> dict[str, object]:
    safe_slug = _safe_petdex_slug(slug)
    manifest = _download_url_json_object(manifest_url, timeout_s=timeout_s)
    entry = _find_petdex_manifest_entry(manifest, slug=safe_slug)
    zip_url = _optional_url_field(entry, "zipUrl")
    if zip_url is None:
        raise ValueError(f"Petdex pet has no zipUrl: {safe_slug}")
    output_dir.mkdir(parents=True, exist_ok=True)
    archive_path = output_dir / f"{safe_slug}.zip"
    metadata_path = output_dir / f"{safe_slug}.petdex.json"
    if archive_path.exists() and not replace:
        raise FileExistsError(f"download target already exists: {archive_path}")

    archive_bytes = _download_url_bytes(zip_url, timeout_s=timeout_s)
    temporary_path = output_dir / f".{safe_slug}.{uuid.uuid4().hex}.zip.tmp"
    try:
        temporary_path.write_bytes(archive_bytes)
        temporary_path.replace(archive_path)
    finally:
        temporary_path.unlink(missing_ok=True)

    with codex_pet_package_source(archive_path) as package_root:
        pet = validate_codex_pet_package(package_root)
    validation = _pet_validation_report(pet)
    validation["source_package"] = str(archive_path)
    report = {
        "schema_version": 1,
        "ok": True,
        "source": "petdex",
        "manifest_url": manifest_url,
        "downloaded_at": datetime.now(UTC).isoformat(),
        "slug": safe_slug,
        "display_name": str(entry.get("displayName") or pet.display_name),
        "kind": str(entry.get("kind") or ""),
        "zip_url": zip_url,
        "pet_json_url": _optional_url_field(entry, "petJsonUrl"),
        "spritesheet_url": _optional_url_field(entry, "spritesheetUrl"),
        "archive": str(archive_path),
        "metadata": str(metadata_path),
        "archive_sha256": _file_sha256(archive_path),
        "archive_size_bytes": archive_path.stat().st_size,
        "validation": validation,
    }
    _write_json_report(metadata_path, report)
    return report


def _petdex_sidecar_path(package: Path) -> Path | None:
    path = package.expanduser()
    candidates: list[Path] = []
    if path.is_file():
        candidates.append(path.with_suffix(".petdex.json"))
    elif path.is_dir():
        candidates.append(path.with_name(f"{path.name}.petdex.json"))
        candidates.append(path / f"{path.name}.petdex.json")
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    return None


def _petdex_sidecar_metadata_report(
    package: Path,
    transfer: dict[str, object],
) -> dict[str, object] | None:
    sidecar = _petdex_sidecar_path(package)
    if sidecar is None:
        return None
    raw = json.loads(sidecar.read_text("utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Petdex sidecar must be a JSON object: {sidecar}")
    metadata = {str(key): value for key, value in raw.items()}
    archive_sha256 = metadata.get("archive_sha256")
    if not _is_sha256_hex(archive_sha256):
        raise ValueError(f"Petdex sidecar archive_sha256 is invalid: {sidecar}")
    archive_size_bytes = metadata.get("archive_size_bytes")
    if not _is_plain_int(archive_size_bytes) or archive_size_bytes <= 0:
        raise ValueError(f"Petdex sidecar archive_size_bytes is invalid: {sidecar}")
    if transfer.get("kind") == "file":
        if archive_sha256 != transfer.get("sha256"):
            raise ValueError("Petdex sidecar archive_sha256 does not match package")
        if archive_size_bytes != transfer.get("size_bytes"):
            raise ValueError("Petdex sidecar archive_size_bytes does not match package")
    slug = metadata.get("slug")
    zip_url = metadata.get("zip_url")
    source = metadata.get("source")
    if source != "petdex":
        raise ValueError(f"Petdex sidecar source must be petdex: {sidecar}")
    if not isinstance(slug, str) or not slug:
        raise ValueError(f"Petdex sidecar slug is required: {sidecar}")
    if not isinstance(zip_url, str) or not zip_url:
        raise ValueError(f"Petdex sidecar zip_url is required: {sidecar}")
    return {
        "path": str(sidecar),
        "sha256": _file_sha256(sidecar),
        "size_bytes": sidecar.stat().st_size,
        "schema_version": metadata.get("schema_version"),
        "source": source,
        "slug": slug,
        "display_name": str(metadata.get("display_name") or ""),
        "zip_url": zip_url,
        "archive_sha256": archive_sha256,
        "archive_size_bytes": archive_size_bytes,
    }


def _directory_transfer_manifest(path: Path) -> dict[str, object]:
    digest = hashlib.sha256()
    file_count = 0
    size_bytes = 0
    for file_path in sorted(
        (item for item in path.rglob("*") if item.is_file()),
        key=lambda item: item.relative_to(path).as_posix(),
    ):
        relative = file_path.relative_to(path).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        with file_path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        file_count += 1
        size_bytes += file_path.stat().st_size
    return {
        "kind": "directory",
        "sha256": digest.hexdigest(),
        "size_bytes": size_bytes,
        "file_count": file_count,
    }


def _package_transfer_manifest(path: Path) -> dict[str, object]:
    if path.is_dir():
        return _directory_transfer_manifest(path)
    if path.is_file():
        return {
            "kind": "file",
            "sha256": _file_sha256(path),
            "size_bytes": path.stat().st_size,
            "file_count": 1,
        }
    return {
        "kind": "missing",
        "sha256": None,
        "size_bytes": 0,
        "file_count": 0,
    }


def _discover_pet_batch_sources(source: Path) -> list[Path]:
    path = source.expanduser()
    if path.is_file() or not path.exists():
        return [path]
    if any((path / filename).exists() for filename in CODEX_PET_MANIFEST_FILENAMES):
        return [path]
    candidates: list[Path] = []
    for child in sorted(path.iterdir(), key=lambda item: item.name.lower()):
        if child.is_symlink():
            continue
        if child.is_file() and (
            child.suffix.lower() == ".zip" or child.name in CODEX_PET_MANIFEST_FILENAMES
        ):
            candidates.append(child)
        elif child.is_dir() and any(
            (child / filename).exists() for filename in CODEX_PET_MANIFEST_FILENAMES
        ):
            candidates.append(child)
    return candidates


def _pet_batch_entry_report(package: Path) -> dict[str, object]:
    transfer = _package_transfer_manifest(package)
    try:
        with codex_pet_package_source(package) as package_root:
            pet = validate_codex_pet_package(package_root)
        petdex_metadata = _petdex_sidecar_metadata_report(package, transfer)
    except Exception as exc:
        return {
            "ok": False,
            "package": str(package),
            "transfer": transfer,
            "error": str(exc),
        }
    report = _pet_validation_report(pet)
    report["source_package"] = str(package)
    report["transfer"] = transfer
    if petdex_metadata is not None:
        report["petdex_metadata"] = petdex_metadata
    return report


def _pet_batch_report(source: Path) -> dict[str, object]:
    packages = _discover_pet_batch_sources(source)
    entries = [_pet_batch_entry_report(package) for package in packages]
    failed = sum(1 for entry in entries if entry.get("ok") is not True)
    errors: list[str] = []
    if not packages:
        errors.append("no pet packages found")
    return {
        "ok": bool(packages) and failed == 0,
        "source": str(source),
        "total": len(entries),
        "passed": len(entries) - failed,
        "failed": failed,
        "errors": errors,
        "pets": entries,
    }


def _pet_package_evidence_report(*, source: Path | None, required: bool) -> dict[str, object]:
    if source is None:
        return _versioned_evidence_report(
            {
                "ok": False,
                "required": required,
                "skipped": True,
                "detail": "pet source not provided",
            }
        )
    report = _pet_batch_report(source)
    report["required"] = required
    report["skipped"] = False
    return _versioned_evidence_report(report)


def _pet_batch_import_report(
    source: Path,
    *,
    pets_root: Path | None,
    replace: bool,
) -> dict[str, object]:
    validation = _pet_batch_report(source)
    root = (pets_root or default_codex_pets_root()).expanduser().resolve()
    validation_errors_raw = validation.get("errors", [])
    validation_errors = (
        [str(error) for error in validation_errors_raw]
        if isinstance(validation_errors_raw, list)
        else []
    )
    validation_pets_raw = validation.get("pets", [])
    validation_pets = validation_pets_raw if isinstance(validation_pets_raw, list) else []
    if validation["ok"] is not True:
        return {
            "ok": False,
            "source": str(source),
            "pets_root": str(root),
            "replace": replace,
            "total": validation["total"],
            "validated": validation["passed"],
            "imported": 0,
            "failed": validation["failed"],
            "errors": ["validation failed", *validation_errors],
            "pets": validation_pets,
            "imports": [],
        }

    pets = [pet for pet in validation_pets if isinstance(pet, dict)]
    preflight_errors: list[str] = []
    imports: list[dict[str, object]] = []
    seen_theme_ids: set[str] = set()
    duplicate_theme_ids: set[str] = set()
    for pet in pets:
        theme_id = str(pet.get("theme_id") or "")
        if not theme_id:
            preflight_errors.append(f"missing theme_id for {pet.get('source_package')}")
            continue
        if theme_id in seen_theme_ids:
            duplicate_theme_ids.add(theme_id)
        seen_theme_ids.add(theme_id)
        target = (root / theme_id).resolve()
        source_package = str(pet.get("source_package") or pet.get("package") or "")
        if root != target.parent:
            preflight_errors.append(f"pet target must stay inside pets root: {target}")
        if target.exists() and not replace:
            imports.append(
                {
                    "ok": False,
                    "theme_id": theme_id,
                    "source_package": source_package,
                    "target": str(target),
                    "error": f"pet package already exists: {target}",
                }
            )

    for theme_id in sorted(duplicate_theme_ids):
        preflight_errors.append(f"duplicate pet id in batch: {theme_id}")

    if preflight_errors or any(entry.get("ok") is False for entry in imports):
        return {
            "ok": False,
            "source": str(source),
            "pets_root": str(root),
            "replace": replace,
            "total": validation["total"],
            "validated": validation["passed"],
            "imported": 0,
            "failed": len(preflight_errors)
            + sum(1 for entry in imports if entry.get("ok") is False),
            "errors": preflight_errors,
            "pets": validation_pets,
            "imports": imports,
        }

    imported: list[dict[str, object]] = []
    for pet in pets:
        source_path = Path(str(pet.get("source_package") or pet.get("package")))
        try:
            imported_pet = import_codex_pet_package(
                source_path,
                pets_root=root,
                replace=replace,
            )
        except Exception as exc:
            imported.append(
                {
                    "ok": False,
                    "theme_id": pet.get("theme_id"),
                    "source_package": str(source_path),
                    "error": str(exc),
                }
            )
            continue
        imported.append(
            {
                "ok": True,
                "theme_id": imported_pet.theme_id,
                "display_name": imported_pet.display_name,
                "source_package": str(source_path),
                "target": str(imported_pet.package_root),
                "atlas_warnings": len(imported_pet.atlas_validation.warnings)
                if imported_pet.atlas_validation is not None
                else 0,
            }
        )

    failed = sum(1 for entry in imported if entry.get("ok") is not True)
    return {
        "ok": failed == 0,
        "source": str(source),
        "pets_root": str(root),
        "replace": replace,
        "total": validation["total"],
        "validated": validation["passed"],
        "imported": len(imported) - failed,
        "failed": failed,
        "errors": [],
        "pets": validation_pets,
        "imports": imported,
    }


def _pet_qa_failure_report(package: Path, error: str) -> dict[str, object]:
    return {
        "ok": False,
        "package": str(package),
        "error": error,
    }


def _pet_qa_run_summary(
    *,
    ok: bool,
    package: Path,
    output_dir: Path,
    theme_id: str | None = None,
    artifacts: dict[str, object] | None = None,
    error: str | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "ok": ok,
        "package": str(package),
        "output_dir": str(output_dir),
        "generated_at": datetime.now(UTC).isoformat(),
    }
    if theme_id is not None:
        payload["theme_id"] = theme_id
    if artifacts is not None:
        payload["artifacts"] = artifacts
    if error is not None:
        payload["error"] = error
    return payload


@admin_app.command("acceptance-check")
def admin_acceptance_check(
    profile: str = ACCEPTANCE_PROFILE_OPTION,
    json_out: Path | None = JSON_OUT_OPTION,
) -> None:
    """Run current-host or target RHEL acceptance checks."""
    try:
        normalized, checks = _build_acceptance_checks(profile)
    except ValueError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=2) from exc

    typer.echo(f"profile={normalized}")
    failed_required = [check for check in checks if check.required and not check.ok]
    for check in checks:
        typer.echo(
            f"check={check.name} "
            f"ok={_bool_text(check.ok)} "
            f"required={_bool_text(check.required)} "
            f"detail={check.detail}"
        )
    typer.echo(f"overall={'failed' if failed_required else 'ok'}")
    if json_out is not None:
        _write_json_report(json_out, _acceptance_report(normalized, checks))
    if failed_required:
        raise typer.Exit(code=1)


@admin_app.command("tmux-control-check")
def admin_tmux_control_check(
    text: str = TMUX_CONTROL_CHECK_TEXT_OPTION,
    timeout_s: float = TMUX_CONTROL_CHECK_TIMEOUT_OPTION,
    json_out: Path | None = JSON_OUT_OPTION,
) -> None:
    """Run a disposable tmux paste probe for raw action transport."""
    try:
        result = run_tmux_control_check(text=text, timeout_s=timeout_s)
    except Exception as exc:
        report: dict[str, object] = _versioned_evidence_report({"ok": False, "error": str(exc)})
        if json_out is not None:
            _write_json_report(json_out, report)
        typer.echo("tmux_control_check=failed")
        typer.echo(f"detail={exc}")
        raise typer.Exit(code=1) from exc

    if json_out is not None:
        _write_json_report(json_out, _versioned_evidence_report(result.as_report()))
    typer.echo(f"tmux_control_check={'ok' if result.ok else 'failed'}")
    typer.echo(f"session={result.session_name}")
    typer.echo(f"pane={result.pane_id or '-'}")
    typer.echo(f"expected_bytes={len(result.expected_text.encode('utf-8'))}")
    observed = result.observed_text
    if observed is not None:
        typer.echo(f"observed_bytes={len(observed.encode('utf-8'))}")
    typer.echo(f"detail={result.detail}")
    if not result.ok:
        raise typer.Exit(code=1)


@admin_app.command("widget-smoke-check")
def admin_widget_smoke_check(
    required: bool = WIDGET_SMOKE_REQUIRED_OPTION,
    json_out: Path | None = JSON_OUT_OPTION,
) -> None:
    """Check that the selected pet theme can create a widget shell."""
    report = _widget_smoke_evidence_report(required=required)
    if json_out is not None:
        _write_json_report(json_out, report)

    typer.echo(f"widget_smoke={'ok' if report['ok'] is True else 'failed'}")
    typer.echo(f"required={_bool_text(report['required'] is True)}")
    typer.echo(f"gui_runtime={report['gui_runtime']}")
    typer.echo(f"gui_validated={_bool_text(report['gui_validated'] is True)}")
    typer.echo(f"theme={report['theme']}")
    typer.echo(f"sprite_asset={report.get('sprite_asset') or '-'}")
    errors = report.get("errors")
    if isinstance(errors, list):
        for error in errors:
            typer.echo(f"error={error}")
    if report["ok"] is not True:
        raise typer.Exit(code=1)


@admin_app.command("hook-event-smoke-check")
def admin_hook_event_smoke_check(
    socket: Path | None = SOCKET_OPTION,
    workspace: Path | None = OPTIONAL_WORKSPACE_OPTION,
    timeout_s: float = TMUX_CONTROL_CHECK_TIMEOUT_OPTION,
    json_out: Path | None = JSON_OUT_OPTION,
) -> None:
    """Verify one hook event reaches the daemon and transcript store."""
    config = load_config()
    socket_path = socket or default_socket_path(config.runtime_dir)
    workspace_path = workspace or (Path(tempfile.gettempdir()) / "coding-pet-hook-smoke")
    report = _hook_event_smoke_evidence_report(
        required=True,
        socket_path=socket_path,
        workspace=workspace_path,
        timeout_s=timeout_s,
    )
    if json_out is not None:
        _write_json_report(json_out, report)

    typer.echo(f"hook_event_smoke={'ok' if report['ok'] is True else 'failed'}")
    typer.echo(f"socket_path={report['socket_path']}")
    hook_result = _json_object(report.get("hook_result"))
    if hook_result is not None and hook_result.get("session_id") is not None:
        typer.echo(f"session_id={hook_result['session_id']}")
    transcript = _json_object(report.get("transcript"))
    if transcript is not None:
        typer.echo(f"transcript_verified={_bool_text(transcript.get('verified') is True)}")
        typer.echo(f"transcript_events={transcript.get('events', 0)}")
    cleanup_result = _json_object(report.get("cleanup_result"))
    if cleanup_result is not None:
        typer.echo(f"cleanup_ok={_bool_text(cleanup_result.get('ok') is True)}")
    errors = report.get("errors")
    if isinstance(errors, list):
        for error in errors:
            typer.echo(f"error={error}")
    if report["ok"] is not True:
        raise typer.Exit(code=1)


@admin_app.command("evidence-bundle")
def admin_evidence_bundle(
    output_dir: Path = OUTPUT_DIR_OPTION,
    profile: str = ACCEPTANCE_PROFILE_OPTION,
    skip_tmux_control: bool = SKIP_TMUX_CONTROL_OPTION,
    skip_systemd_verify: bool = SKIP_SYSTEMD_VERIFY_OPTION,
    wheelhouse: Path | None = WHEELHOUSE_OPTION,
    require_wheelhouse: bool = REQUIRE_WHEELHOUSE_OPTION,
    pet_source: Path | None = PET_SOURCE_OPTION,
    require_pet_packages: bool = REQUIRE_PET_PACKAGES_OPTION,
    skip_install_smoke: bool = SKIP_INSTALL_SMOKE_OPTION,
    install_target: str = INSTALL_TARGET_OPTION,
    timeout_s: float = TMUX_CONTROL_CHECK_TIMEOUT_OPTION,
    hooks_dir: Path | None = HOOKS_DIR_OPTION,
    claude_settings: Path | None = CLAUDE_SETTINGS_OPTION,
    opencode_plugin: Path | None = OPENCODE_PLUGIN_OPTION,
    skip_claude: bool = SKIP_CLAUDE_OPTION,
    skip_opencode: bool = SKIP_OPENCODE_OPTION,
    require_agent_hooks: bool = REQUIRE_AGENT_HOOKS_OPTION,
) -> None:
    """Write target bring-up evidence JSON files into one directory."""
    try:
        normalized, checks = _build_acceptance_checks(profile)
    except ValueError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=2) from exc

    output_dir.mkdir(parents=True, exist_ok=True)
    environment_path = output_dir / "environment.json"
    acceptance_path = output_dir / f"acceptance-{normalized}.json"
    tmux_control_path = output_dir / "tmux-control.json"
    systemd_units_path = output_dir / "systemd-units.json"
    systemd_runtime_path = output_dir / "systemd-runtime.json"
    widget_smoke_path = output_dir / "widget-smoke.json"
    wheelhouse_path = output_dir / "wheelhouse.json"
    pet_packages_path = output_dir / "pet-packages.json"
    agent_hooks_path = output_dir / "agent-hooks.json"
    hook_event_smoke_path = output_dir / "hook-event-smoke.json"
    summary_path = output_dir / "summary.json"

    config = load_config()
    environment = _environment_evidence_report(normalized)
    acceptance = _acceptance_report(normalized, checks)
    tmux_control = _tmux_control_evidence_report(
        required=normalized == "target",
        skip=skip_tmux_control,
        timeout_s=timeout_s,
    )
    systemd_units = _systemd_unit_evidence_report(
        required=normalized == "target",
        skip=skip_systemd_verify,
        timeout_s=timeout_s,
    )
    systemd_runtime = _systemd_runtime_evidence_report(
        required=normalized == "target",
        timeout_s=timeout_s,
    )
    widget_smoke = _widget_smoke_evidence_report(required=normalized == "target")
    wheelhouse_report = _wheelhouse_evidence_report(
        wheelhouse=wheelhouse,
        required=require_wheelhouse,
        install_target=install_target,
        skip_install_smoke=skip_install_smoke,
        timeout_s=timeout_s,
    )
    pet_packages = _pet_package_evidence_report(
        source=pet_source,
        required=require_pet_packages,
    )
    agent_hooks = _agent_hooks_evidence_report(
        hooks_dir=hooks_dir or _default_agent_hooks_dir(),
        claude_settings=claude_settings or _default_claude_settings_path(),
        opencode_plugin=opencode_plugin or _default_opencode_plugin_path(),
        skip_claude=skip_claude,
        skip_opencode=skip_opencode,
        required=require_agent_hooks,
    )
    hook_event_smoke = _hook_event_smoke_evidence_report(
        required=normalized == "target",
        socket_path=default_socket_path(config.runtime_dir),
        workspace=output_dir,
        timeout_s=timeout_s,
    )
    for report in (
        tmux_control,
        systemd_units,
        systemd_runtime,
        widget_smoke,
        wheelhouse_report,
        pet_packages,
        agent_hooks,
        hook_event_smoke,
    ):
        _stamp_evidence_profile(report, normalized)
    summary = _evidence_bundle_summary(
        profile=normalized,
        output_dir=output_dir,
        acceptance=acceptance,
        environment_path=environment_path,
        acceptance_path=acceptance_path,
        tmux_control_path=tmux_control_path,
        tmux_control=tmux_control,
        systemd_units_path=systemd_units_path,
        systemd_units=systemd_units,
        systemd_runtime_path=systemd_runtime_path,
        systemd_runtime=systemd_runtime,
        widget_smoke_path=widget_smoke_path,
        widget_smoke=widget_smoke,
        wheelhouse_path=wheelhouse_path,
        wheelhouse=wheelhouse_report,
        pet_packages_path=pet_packages_path,
        pet_packages=pet_packages,
        agent_hooks_path=agent_hooks_path,
        agent_hooks=agent_hooks,
        hook_event_smoke_path=hook_event_smoke_path,
        hook_event_smoke=hook_event_smoke,
    )

    _write_json_report(environment_path, environment)
    _write_json_report(acceptance_path, acceptance)
    _write_json_report(tmux_control_path, tmux_control)
    _write_json_report(systemd_units_path, systemd_units)
    _write_json_report(systemd_runtime_path, systemd_runtime)
    _write_json_report(widget_smoke_path, widget_smoke)
    _write_json_report(wheelhouse_path, wheelhouse_report)
    _write_json_report(pet_packages_path, pet_packages)
    _write_json_report(agent_hooks_path, agent_hooks)
    _write_json_report(hook_event_smoke_path, hook_event_smoke)
    _write_json_report(summary_path, summary)

    typer.echo(f"evidence_bundle={output_dir}")
    typer.echo(f"profile={normalized}")
    typer.echo(f"environment={environment_path}")
    typer.echo(f"acceptance={acceptance_path}")
    typer.echo(f"tmux_control={tmux_control_path}")
    typer.echo(f"systemd_units={systemd_units_path}")
    typer.echo(f"systemd_runtime={systemd_runtime_path}")
    typer.echo(f"widget_smoke={widget_smoke_path}")
    typer.echo(f"wheelhouse={wheelhouse_path}")
    typer.echo(f"pet_packages={pet_packages_path}")
    typer.echo(f"agent_hooks={agent_hooks_path}")
    typer.echo(f"hook_event_smoke={hook_event_smoke_path}")
    typer.echo(f"summary={summary_path}")
    typer.echo(f"overall={'ok' if summary['ok'] is True else 'failed'}")
    if summary["ok"] is not True:
        raise typer.Exit(code=1)


@admin_app.command("systemd-unit-check")
def admin_systemd_unit_check(
    timeout_s: float = TMUX_CONTROL_CHECK_TIMEOUT_OPTION,
    json_out: Path | None = JSON_OUT_OPTION,
) -> None:
    """Verify packaged systemd user unit syntax."""
    report = _systemd_unit_evidence_report(required=True, skip=False, timeout_s=timeout_s)
    if json_out is not None:
        _write_json_report(json_out, report)
    typer.echo(f"systemd_units={'ok' if report['ok'] is True else 'failed'}")
    typer.echo(f"required={_bool_text(report['required'] is True)}")
    typer.echo(f"skipped={_bool_text(report['skipped'] is True)}")
    typer.echo(f"detail={report['detail']}")
    units = report.get("units")
    if isinstance(units, list):
        for unit in units:
            typer.echo(f"unit={unit}")
    if report["ok"] is not True:
        raise typer.Exit(code=1)


@admin_app.command("wheelhouse-check")
def admin_wheelhouse_check(
    wheelhouse: Path = WHEELHOUSE_ARGUMENT,
    install_target: str = INSTALL_TARGET_OPTION,
    skip_install_smoke: bool = SKIP_INSTALL_SMOKE_OPTION,
    timeout_s: float = TMUX_CONTROL_CHECK_TIMEOUT_OPTION,
    json_out: Path | None = JSON_OUT_OPTION,
) -> None:
    """Validate an intranet/offline RHEL wheelhouse."""
    report = _wheelhouse_check_report(
        wheelhouse=wheelhouse,
        install_target=install_target,
        skip_install_smoke=skip_install_smoke,
        timeout_s=timeout_s,
    )
    if json_out is not None:
        _write_json_report(json_out, report)
    typer.echo(f"wheelhouse={wheelhouse}")
    typer.echo(f"wheelhouse_check={'ok' if report['ok'] is True else 'failed'}")
    missing = report.get("missing_distributions")
    if isinstance(missing, list):
        typer.echo(
            "missing_distributions="
            f"{'none' if not missing else ','.join(str(item) for item in missing)}"
        )
    incompatible = report.get("incompatible_platform_wheels")
    if isinstance(incompatible, list):
        typer.echo(
            "incompatible_platform_wheels="
            f"{'none' if not incompatible else ','.join(str(item) for item in incompatible)}"
        )
    incompatible_python = report.get("incompatible_python_wheels")
    if isinstance(incompatible_python, list):
        incompatible_python_summary = (
            "none"
            if not incompatible_python
            else ",".join(str(item) for item in incompatible_python)
        )
        typer.echo(f"incompatible_python_wheels={incompatible_python_summary}")
    install_smoke = report.get("install_smoke")
    if isinstance(install_smoke, dict):
        if install_smoke.get("skipped") is True:
            smoke_status = "skipped"
        else:
            smoke_status = "ok" if install_smoke.get("ok") is True else "failed"
        typer.echo(f"install_smoke={smoke_status}")
        detail = install_smoke.get("detail")
        if isinstance(detail, str):
            typer.echo(f"detail={detail}")
    errors = report.get("errors")
    if isinstance(errors, list):
        for error in errors:
            typer.echo(f"error={error}")
    if report["ok"] is not True:
        raise typer.Exit(code=1)


@admin_app.command("backend-evidence-check")
def admin_backend_evidence_check(
    report: Path = REPORT_ARGUMENT,
    agent: AgentKind | None = OPTIONAL_AGENT_OPTION,
    action: str | None = OPTIONAL_ACTION_OPTION,
    allow_unchanged_output: bool = ALLOW_UNCHANGED_OUTPUT_OPTION,
    json_out: Path | None = JSON_OUT_OPTION,
) -> None:
    """Validate one verify-tmux-action JSON report as backend semantic evidence."""
    result = _backend_evidence_check_report(
        report,
        expected_agent=agent,
        expected_action=action,
        allow_unchanged_output=allow_unchanged_output,
    )
    if json_out is not None:
        _write_json_report(json_out, result)
    typer.echo(f"backend_evidence={'ok' if result['ok'] is True else 'failed'}")
    typer.echo(f"report={report}")
    if result.get("agent") is not None:
        typer.echo(f"agent={result['agent']}")
    if result.get("action") is not None:
        typer.echo(f"action={result['action']}")
    if result.get("pane") is not None:
        typer.echo(f"pane={result['pane']}")
    evidence = result.get("evidence")
    if isinstance(evidence, dict):
        typer.echo(f"matched_expected={_bool_text(evidence.get('matched_expected') is True)}")
        typer.echo(f"output_changed={_bool_text(evidence.get('output_changed') is True)}")
    errors = result.get("errors")
    if isinstance(errors, list):
        for error in errors:
            typer.echo(f"error={error}")
    if result["ok"] is not True:
        raise typer.Exit(code=1)


@admin_app.command("target-evidence-check")
def admin_target_evidence_check(
    evidence_dir: Path = EVIDENCE_DIR_ARGUMENT,
    json_out: Path | None = JSON_OUT_OPTION,
) -> None:
    """Validate a complete target-server evidence directory."""
    result = _target_evidence_check_report(evidence_dir)
    if json_out is not None:
        _write_json_report(json_out, result)
    typer.echo(f"target_evidence={'ok' if result['ok'] is True else 'failed'}")
    typer.echo(f"evidence_dir={evidence_dir}")
    backend_reports = result.get("backend_reports")
    if isinstance(backend_reports, list):
        typer.echo(f"backend_report_count={len(backend_reports)}")
    errors = result.get("errors")
    if isinstance(errors, list):
        for error in errors:
            typer.echo(f"error={error}")
    if result["ok"] is not True:
        raise typer.Exit(code=1)


@admin_app.command("collect-target-backend-evidence")
def admin_collect_target_backend_evidence(
    output_dir: Path = OUTPUT_DIR_OPTION,
    claude_pane: str = CLAUDE_PANE_OPTION,
    opencode_pane: str = OPENCODE_PANE_OPTION,
    reply_expect_regex: str = REPLY_EXPECT_REGEX_OPTION,
    approve_expect_regex: str = APPROVE_EXPECT_REGEX_OPTION,
    reject_expect_regex: str = REJECT_EXPECT_REGEX_OPTION,
    reply_text: str = TARGET_REPLY_TEXT_OPTION,
    claude_reply_pane: str | None = CLAUDE_REPLY_PANE_OPTION,
    claude_approve_pane: str | None = CLAUDE_APPROVE_PANE_OPTION,
    claude_reject_pane: str | None = CLAUDE_REJECT_PANE_OPTION,
    opencode_reply_pane: str | None = OPENCODE_REPLY_PANE_OPTION,
    opencode_approve_pane: str | None = OPENCODE_APPROVE_PANE_OPTION,
    opencode_reject_pane: str | None = OPENCODE_REJECT_PANE_OPTION,
    timeout_s: float = TMUX_CONTROL_CHECK_TIMEOUT_OPTION,
    capture_lines: int = CAPTURE_LINES_OPTION,
) -> None:
    """Collect the six disposable Claude/OpenCode backend evidence reports."""
    specs = _target_backend_evidence_specs(
        claude_pane=claude_pane,
        opencode_pane=opencode_pane,
        claude_reply_pane=claude_reply_pane,
        claude_approve_pane=claude_approve_pane,
        claude_reject_pane=claude_reject_pane,
        opencode_reply_pane=opencode_reply_pane,
        opencode_approve_pane=opencode_approve_pane,
        opencode_reject_pane=opencode_reject_pane,
        reply_text=reply_text,
        reply_expect_regex=reply_expect_regex,
        approve_expect_regex=approve_expect_regex,
        reject_expect_regex=reject_expect_regex,
    )
    summary = asyncio.run(
        _collect_target_backend_evidence(
            output_dir=output_dir,
            specs=specs,
            timeout_s=timeout_s,
            capture_lines=capture_lines,
        )
    )
    typer.echo(f"backend_evidence_collection={'ok' if summary['ok'] is True else 'failed'}")
    typer.echo(f"output_dir={output_dir}")
    typer.echo(f"summary={output_dir / BACKEND_EVIDENCE_SUMMARY_FILENAME}")
    reports = summary.get("reports")
    if isinstance(reports, list):
        for report in reports:
            if not isinstance(report, dict):
                continue
            typer.echo(
                "report="
                f"{Path(str(report.get('report'))).name} "
                f"agent={report.get('agent')} "
                f"action={report.get('action')} "
                f"ok={_bool_text(report.get('ok') is True)}"
            )
            errors = report.get("errors")
            if isinstance(errors, list):
                for error in errors:
                    typer.echo(f"error={Path(str(report.get('report'))).name}: {error}")
    if summary["ok"] is not True:
        raise typer.Exit(code=1)


@admin_app.command("write-agent-hooks")
def admin_write_agent_hooks(
    output_dir: Path = OUTPUT_DIR_OPTION,
) -> None:
    """Write offline-safe Claude/OpenCode hook script and config snippets."""
    files = _write_agent_hook_files(output_dir)

    typer.echo(f"hooks_dir={files.hooks_dir}")
    typer.echo(f"hook_script={files.hook_script}")
    typer.echo(f"claude_settings_snippet={files.claude_settings_snippet}")
    typer.echo(f"opencode_plugin={files.opencode_plugin_snippet}")


@admin_app.command("install-agent-hooks")
def admin_install_agent_hooks(
    hooks_dir: Path | None = HOOKS_DIR_OPTION,
    claude_settings: Path | None = CLAUDE_SETTINGS_OPTION,
    opencode_plugin: Path | None = OPENCODE_PLUGIN_OPTION,
    skip_claude: bool = SKIP_CLAUDE_OPTION,
    skip_opencode: bool = SKIP_OPENCODE_OPTION,
) -> None:
    """Install offline-safe Claude/OpenCode hooks into local agent config files."""
    resolved_hooks_dir = hooks_dir or _default_agent_hooks_dir()
    resolved_claude_settings = claude_settings or _default_claude_settings_path()
    resolved_opencode_plugin = opencode_plugin or _default_opencode_plugin_path()
    files = _write_agent_hook_files(resolved_hooks_dir)

    try:
        if not skip_claude:
            _install_claude_hooks(resolved_claude_settings, hook_script=files.hook_script)
        if not skip_opencode:
            _install_opencode_plugin(resolved_opencode_plugin, hook_script=files.hook_script)
    except Exception as exc:
        typer.echo("agent_hooks_install=failed")
        typer.echo(f"detail={exc}")
        raise typer.Exit(code=1) from exc

    typer.echo("agent_hooks_install=ok")
    typer.echo(f"hooks_dir={files.hooks_dir}")
    typer.echo(f"hook_script={files.hook_script}")
    if not skip_claude:
        typer.echo(f"claude_settings={resolved_claude_settings}")
    if not skip_opencode:
        typer.echo(f"opencode_plugin={resolved_opencode_plugin}")


@admin_app.command("agent-hooks-doctor")
def admin_agent_hooks_doctor(
    hooks_dir: Path | None = HOOKS_DIR_OPTION,
    claude_settings: Path | None = CLAUDE_SETTINGS_OPTION,
    opencode_plugin: Path | None = OPENCODE_PLUGIN_OPTION,
    skip_claude: bool = SKIP_CLAUDE_OPTION,
    skip_opencode: bool = SKIP_OPENCODE_OPTION,
    json_out: Path | None = JSON_OUT_OPTION,
) -> None:
    """Check that local Claude/OpenCode hook files are installed."""
    resolved_hooks_dir = hooks_dir or _default_agent_hooks_dir()
    resolved_claude_settings = claude_settings or _default_claude_settings_path()
    resolved_opencode_plugin = opencode_plugin or _default_opencode_plugin_path()
    report = _agent_hooks_doctor_report(
        hooks_dir=resolved_hooks_dir,
        claude_settings=resolved_claude_settings,
        opencode_plugin=resolved_opencode_plugin,
        skip_claude=skip_claude,
        skip_opencode=skip_opencode,
    )
    if json_out is not None:
        _write_json_report(json_out, report)

    typer.echo(f"agent_hooks={'ok' if report['ok'] is True else 'failed'}")
    checks = report.get("checks")
    if isinstance(checks, list):
        for check in checks:
            if not isinstance(check, dict):
                continue
            typer.echo(
                "check="
                f"{check.get('name')} "
                f"ok={_bool_text(check.get('ok') is True)} "
                f"required={_bool_text(check.get('required') is True)} "
                f"detail={check.get('detail')}"
            )
    if report["ok"] is not True:
        raise typer.Exit(code=1)


@admin_app.command("systemd-runtime-check")
def admin_systemd_runtime_check(
    timeout_s: float = TMUX_CONTROL_CHECK_TIMEOUT_OPTION,
    json_out: Path | None = JSON_OUT_OPTION,
) -> None:
    """Verify coding-pet systemd user services are active."""
    report = _systemd_runtime_evidence_report(required=True, timeout_s=timeout_s)
    if json_out is not None:
        _write_json_report(json_out, report)

    typer.echo(f"systemd_runtime={'ok' if report['ok'] is True else 'failed'}")
    typer.echo(f"systemctl={report.get('systemctl') or '-'}")
    target_enabled = _json_object(report.get("target_enabled"))
    if target_enabled is not None:
        typer.echo(
            "target_enabled="
            f"{target_enabled.get('state')} "
            f"ok={_bool_text(target_enabled.get('ok') is True)}"
        )
    units = report.get("units")
    if isinstance(units, list):
        for unit in units:
            if not isinstance(unit, dict):
                continue
            typer.echo(
                "unit="
                f"{unit.get('unit')} "
                f"state={unit.get('state')} "
                f"ok={_bool_text(unit.get('ok') is True)}"
            )
    errors = report.get("errors")
    if isinstance(errors, list):
        for error in errors:
            typer.echo(f"error={error}")
    if report["ok"] is not True:
        raise typer.Exit(code=1)


@admin_app.command("doctor")
def admin_doctor() -> None:
    """Run basic environment diagnostics."""
    config = load_config()
    typer.echo(f"config_dir={config.config_dir}")
    typer.echo(f"state_dir={config.state_dir}")
    typer.echo(f"runtime_dir={config.runtime_dir}")
    typer.echo(f"state_file={config.state_file}")
    typer.echo(f"log_dir={config.log_dir}")
    typer.echo(f"log_level={config.log_level}")
    typer.echo(f"show_completed_for_sec={config.ui.show_completed_for_sec}")
    typer.echo(f"process_stop_timeout_sec={config.process_stop_timeout_seconds}")
    typer.echo(f"python={shutil.which('python') or shutil.which('python3') or 'unavailable'}")
    typer.echo(f"notify_send={shutil.which('notify-send') or 'unavailable'}")
    typer.echo(f"tmux_binary={shutil.which('tmux') or 'unavailable'}")
    typer.echo(f"tmux_enabled={str(config.tmux.enabled).lower()}")
    typer.echo(f"tmux_capture_lines={config.tmux.capture_lines}")
    typer.echo(f"transcript_db={config.transcript.db_path}")
    typer.echo(f"transcript_enabled={str(config.transcript.enabled).lower()}")
    typer.echo(f"transcript_redact_secrets={str(config.transcript.redact_secrets).lower()}")
    typer.echo(
        f"transcript_custom_redaction_patterns={len(config.transcript.custom_redaction_patterns)}"
    )
    typer.echo(f"gui_runtime={_gui_runtime_status()}")
    assets_root = default_assets_root()
    typer.echo(f"assets_root={assets_root}")
    typer.echo(f"codex_pets_root={default_codex_pets_root()}")
    theme_name = configured_theme()
    typer.echo(f"configured_theme={theme_name}")
    try:
        manifest = load_manifest_for_theme(theme_name, assets_root=assets_root)
    except Exception as exc:
        typer.echo("theme=unavailable")
        typer.echo(f"theme_missing_assets=manifest_error:{exc}")
    else:
        theme_assets_root = manifest.asset_root or assets_root
        missing_assets = validate_theme_assets(manifest, theme_assets_root)
        missing_summary = (
            "none" if not missing_assets else ",".join(path.as_posix() for path in missing_assets)
        )
        typer.echo(f"theme={manifest.name}")
        typer.echo(
            f"theme_format={'codex_pet' if manifest.spritesheet is not None else 'coding_pet'}"
        )
        typer.echo(f"theme_assets_root={theme_assets_root}")
        typer.echo(f"theme_missing_assets={missing_summary}")
    try:
        registry_manifest = load_theme_registry(default_theme_registry_path(assets_root))
    except Exception as exc:
        typer.echo(f"theme_registry=unavailable:{exc}")
    else:
        spritecollab_count = sum(
            1 for entry in registry_manifest.themes if entry.theme.startswith("pmd-")
        )
        typer.echo(f"theme_registry_count={len(registry_manifest.themes)}")
        typer.echo(f"theme_spritecollab_count={spritecollab_count}")
    runtime_socket = default_socket_path(config.runtime_dir)
    typer.echo(f"runtime_socket={runtime_socket}")
    typer.echo(f"runtime_socket_exists={str(runtime_socket.exists()).lower()}")
    typer.echo(f"path_status_config_dir={_path_health(config.config_dir)}")
    typer.echo(f"path_status_state_dir={_path_health(config.state_dir)}")
    typer.echo(f"path_status_runtime_dir={_path_health(config.runtime_dir)}")
    typer.echo(f"path_status_log_dir={_path_health(config.log_dir)}")
    typer.echo(f"path_status_state_file={_path_health(config.state_file)}")
    registry = AgentBackendRegistry.default()
    for backend in registry.list_all():
        status = "available" if backend.available else "unavailable"
        typer.echo(f"backend_{backend.agent_kind.value}={status}:{backend.reason}")


@admin_app.command("list-pets")
def admin_list_pets() -> None:
    """List bundled and imported pet themes."""
    assets_root = default_assets_root()
    pets_root = default_codex_pets_root()
    registry = discover_theme_choices(assets_root, pets_root=pets_root)
    typer.echo(f"default_theme={registry.default_theme}")
    typer.echo(f"assets_root={assets_root}")
    typer.echo(f"codex_pets_root={pets_root}")
    for entry in registry.themes:
        theme_format = "codex_pet" if entry.source == "codex-pet-package" else "coding_pet"
        manifest = entry.manifest.as_posix() if entry.manifest is not None else "-"
        typer.echo(
            f"{entry.theme}\t{entry.display_name}\t{theme_format}\t{entry.source}\t{manifest}"
        )


@admin_app.command("download-petdex")
def admin_download_petdex(
    slug: str = typer.Argument(...),
    output_dir: Path = OUTPUT_DIR_OPTION,
    manifest_url: str = PETDEX_MANIFEST_URL_OPTION,
    replace: bool = REPLACE_OPTION,
    json_out: Path | None = JSON_OUT_OPTION,
    timeout_s: float = DOWNLOAD_TIMEOUT_OPTION,
) -> None:
    """Download one Petdex ZIP into an offline transfer staging directory."""
    try:
        report = _download_petdex_report(
            slug=slug,
            output_dir=output_dir,
            manifest_url=manifest_url,
            replace=replace,
            timeout_s=timeout_s,
        )
    except Exception as exc:
        if json_out is not None:
            _write_json_report(
                json_out,
                {
                    "ok": False,
                    "source": "petdex",
                    "slug": slug,
                    "manifest_url": manifest_url,
                    "error": str(exc),
                },
            )
        typer.echo("petdex_download=failed")
        typer.echo(f"error={exc}")
        raise typer.Exit(code=1) from exc
    if json_out is not None:
        _write_json_report(json_out, report)
    validation = report.get("validation")
    valid_pet = validation.get("theme_id") if isinstance(validation, dict) else report.get("slug")
    typer.echo("petdex_download=ok")
    typer.echo(f"slug={report['slug']}")
    typer.echo(f"display_name={report['display_name']}")
    typer.echo(f"archive={report['archive']}")
    typer.echo(f"metadata={report['metadata']}")
    typer.echo(f"archive_sha256={report['archive_sha256']}")
    typer.echo(f"valid_pet={valid_pet}")


@admin_app.command("validate-pet")
def admin_validate_pet(
    package: Path = PACKAGE_ARGUMENT,
    json_out: Path | None = JSON_OUT_OPTION,
) -> None:
    """Validate a copied Codex/Petdex pet package."""
    try:
        with codex_pet_package_source(package) as package_root:
            pet = validate_codex_pet_package(package_root)
    except Exception as exc:
        if json_out is not None:
            _write_json_report(
                json_out,
                {
                    "ok": False,
                    "package": str(package),
                    "error": str(exc),
                },
            )
        typer.echo(f"invalid pet package: {exc}")
        raise typer.Exit(code=1) from exc
    if json_out is not None:
        report = _pet_validation_report(pet)
        report["source_package"] = str(package)
        _write_json_report(json_out, report)
    typer.echo(f"valid_pet={pet.theme_id}")
    typer.echo(f"display_name={pet.display_name}")
    typer.echo("theme_format=codex_pet")
    typer.echo(f"package_root={pet.package_root}")
    typer.echo(f"manifest={pet.manifest_path}")
    typer.echo(f"spritesheet={pet.spritesheet_path.as_posix()}")
    typer.echo(f"atlas_size={pet.image_size[0]}x{pet.image_size[1]}")
    typer.echo("atlas_cells=ok")
    if pet.atlas_validation is not None:
        typer.echo(f"atlas_warnings={len(pet.atlas_validation.warnings)}")


@admin_app.command("validate-pet-batch")
def admin_validate_pet_batch(
    source: Path = PACKAGE_ARGUMENT,
    json_out: Path | None = JSON_OUT_OPTION,
) -> None:
    """Validate multiple copied Codex/Petdex pet packages from one directory."""
    report = _pet_batch_report(source)
    if json_out is not None:
        _write_json_report(json_out, report)
    typer.echo(f"pet_batch={'ok' if report['ok'] is True else 'failed'}")
    typer.echo(f"source={source}")
    typer.echo(f"total={report['total']}")
    typer.echo(f"passed={report['passed']}")
    typer.echo(f"failed={report['failed']}")
    errors = report.get("errors")
    if isinstance(errors, list):
        for error in errors:
            typer.echo(f"error={error}")
    pets = report.get("pets")
    if isinstance(pets, list):
        for pet in pets:
            if not isinstance(pet, dict):
                continue
            if pet.get("ok") is True:
                atlas_cells = pet.get("atlas_cells")
                warning_count = (
                    len(atlas_cells.get("warnings", [])) if isinstance(atlas_cells, dict) else 0
                )
                typer.echo(
                    "pet="
                    f"{pet.get('theme_id')} "
                    "ok=true "
                    f"warnings={warning_count} "
                    f"package={pet.get('source_package')}"
                )
            else:
                typer.echo(f"pet={pet.get('package')} ok=false error={pet.get('error')}")
    if report["ok"] is not True:
        raise typer.Exit(code=1)


@admin_app.command("import-pet-batch")
def admin_import_pet_batch(
    source: Path = PACKAGE_ARGUMENT,
    pets_root: Path | None = PETS_ROOT_OPTION,
    replace: bool = REPLACE_OPTION,
    json_out: Path | None = JSON_OUT_OPTION,
) -> None:
    """Validate and install multiple copied Codex/Petdex pet packages."""
    report = _pet_batch_import_report(source, pets_root=pets_root, replace=replace)
    if json_out is not None:
        _write_json_report(json_out, report)
    typer.echo(f"pet_batch_import={'ok' if report['ok'] is True else 'failed'}")
    typer.echo(f"source={source}")
    typer.echo(f"pets_root={report['pets_root']}")
    typer.echo(f"total={report['total']}")
    typer.echo(f"validated={report['validated']}")
    typer.echo(f"imported={report['imported']}")
    typer.echo(f"failed={report['failed']}")
    errors = report.get("errors")
    if isinstance(errors, list):
        for error in errors:
            typer.echo(f"error={error}")
    imports = report.get("imports")
    if isinstance(imports, list):
        for imported in imports:
            if not isinstance(imported, dict):
                continue
            if imported.get("ok") is True:
                typer.echo(
                    "imported_pet="
                    f"{imported.get('theme_id')} "
                    f"warnings={imported.get('atlas_warnings', 0)} "
                    f"target={imported.get('target')}"
                )
            else:
                typer.echo(
                    "imported_pet="
                    f"{imported.get('theme_id') or imported.get('source_package')} "
                    "ok=false "
                    f"error={imported.get('error')}"
                )
    if report["ok"] is not True:
        raise typer.Exit(code=1)


@admin_app.command("build-pet-qa")
def admin_build_pet_qa(
    package: Path = PACKAGE_ARGUMENT,
    output_dir: Path = OUTPUT_DIR_OPTION,
    cell_width: int = CELL_WIDTH_OPTION,
    size: int = PREVIEW_SIZE_OPTION,
) -> None:
    """Build a validation bundle for a copied Codex/Petdex pet package."""
    from coding_pet.gui.preview import (
        PreviewRenderError,
        render_pet_animation_previews,
        render_pet_contact_sheet,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    validation_path = output_dir / "validation.json"
    run_summary_path = output_dir / "run-summary.json"
    try:
        with codex_pet_package_source(package) as package_root:
            try:
                pet = validate_codex_pet_package(package_root)
            except Exception as exc:
                error = str(exc)
                _write_json_report(validation_path, _pet_qa_failure_report(package, error))
                _write_json_report(
                    run_summary_path,
                    _pet_qa_run_summary(
                        ok=False,
                        package=package,
                        output_dir=output_dir,
                        error=error,
                    ),
                )
                typer.echo(f"pet qa failed: {error}")
                raise typer.Exit(code=1) from exc

            validation_report = _pet_validation_report(pet)
            validation_report["source_package"] = str(package)
            _write_json_report(validation_path, validation_report)
            contact_sheet_path = output_dir / "contact-sheet.png"
            animation_dir = output_dir / "animation-previews"
            try:
                contact = render_pet_contact_sheet(
                    str(pet.package_root),
                    output_path=contact_sheet_path,
                    cell_width=cell_width,
                )
                animations = render_pet_animation_previews(
                    str(pet.package_root),
                    output_dir=animation_dir,
                    size=size,
                )
            except PreviewRenderError as exc:
                error = str(exc)
                _write_json_report(
                    run_summary_path,
                    _pet_qa_run_summary(
                        ok=False,
                        package=package,
                        output_dir=output_dir,
                        theme_id=pet.theme_id,
                        artifacts={"validation": str(validation_path)},
                        error=error,
                    ),
                )
                typer.echo(f"pet qa failed: {error}")
                raise typer.Exit(code=1) from exc

            artifacts: dict[str, object] = {
                "validation": str(validation_path),
                "run_summary": str(run_summary_path),
                "contact_sheet": str(contact.output_path),
                "animation_previews": [str(path) for path in animations.preview_paths],
            }
            _write_json_report(
                run_summary_path,
                _pet_qa_run_summary(
                    ok=True,
                    package=package,
                    output_dir=output_dir,
                    theme_id=pet.theme_id,
                    artifacts=artifacts,
                ),
            )
            typer.echo(f"qa_pet={pet.theme_id}")
            typer.echo(f"output_dir={output_dir}")
            typer.echo(f"validation={validation_path}")
            typer.echo(f"contact_sheet={contact.output_path}")
            typer.echo(f"animation_preview_count={len(animations.preview_paths)}")
            typer.echo(f"run_summary={run_summary_path}")
    except typer.Exit:
        raise
    except Exception as exc:
        error = str(exc)
        _write_json_report(validation_path, _pet_qa_failure_report(package, error))
        _write_json_report(
            run_summary_path,
            _pet_qa_run_summary(
                ok=False,
                package=package,
                output_dir=output_dir,
                error=error,
            ),
        )
        typer.echo(f"pet qa failed: {error}")
        raise typer.Exit(code=1) from exc


@admin_app.command("import-pet")
def admin_import_pet(
    package: Path = PACKAGE_ARGUMENT,
    pets_root: Path | None = PETS_ROOT_OPTION,
    replace: bool = REPLACE_OPTION,
) -> None:
    """Install a validated Codex/Petdex pet package into the local pets root."""
    try:
        pet = import_codex_pet_package(package, pets_root=pets_root, replace=replace)
    except Exception as exc:
        typer.echo(f"pet import failed: {exc}")
        raise typer.Exit(code=1) from exc
    typer.echo(f"imported_pet={pet.theme_id}")
    typer.echo(f"display_name={pet.display_name}")
    typer.echo("theme_format=codex_pet")
    typer.echo(f"target={pet.package_root}")
    typer.echo(f"manifest={pet.manifest_path}")
    typer.echo(f"atlas_size={pet.image_size[0]}x{pet.image_size[1]}")
    typer.echo("atlas_cells=ok")
    if pet.atlas_validation is not None:
        typer.echo(f"atlas_warnings={len(pet.atlas_validation.warnings)}")


@admin_app.command("set-pet")
def admin_set_pet(
    theme: str = THEME_ARGUMENT,
    service_env: Path | None = SERVICE_ENV_OPTION,
    pets_root: Path | None = PETS_ROOT_OPTION,
) -> None:
    """Persist the active pet theme for systemd user services."""
    config = load_config()
    env_path = service_env or (config.config_dir / "service.env")
    resolved_pets_root = pets_root or default_codex_pets_root()
    try:
        manifest = load_manifest_for_theme(theme, pets_root=resolved_pets_root)
        assets_root = manifest.asset_root or default_assets_root()
        missing = validate_theme_assets(manifest, assets_root)
        if missing:
            missing_summary = ",".join(path.as_posix() for path in missing)
            raise ValueError(f"theme missing assets: {missing_summary}")
        if manifest.spritesheet is not None and manifest.asset_root is not None:
            validate_codex_pet_package(manifest.asset_root)
    except Exception as exc:
        typer.echo(f"pet selection failed: {exc}")
        raise typer.Exit(code=1) from exc

    values = {"CODING_PET_THEME": manifest.name}
    if manifest.spritesheet is not None and manifest.asset_root is not None:
        values["CODING_PET_CODEX_PETS_DIR"] = str(resolved_pets_root)
    _upsert_service_env(env_path, values)
    typer.echo(f"selected_pet={manifest.name}")
    typer.echo(f"theme_format={'codex_pet' if manifest.spritesheet is not None else 'coding_pet'}")
    typer.echo(f"service_env={env_path}")


def _upsert_service_env(path: Path, values: dict[str, str]) -> None:
    existing_lines = path.read_text("utf-8").splitlines() if path.exists() else []
    seen: set[str] = set()
    updated_lines: list[str] = []
    for line in existing_lines:
        key = _env_assignment_key(line)
        if key is not None and key in values:
            updated_lines.append(f"{key}={values[key]}")
            seen.add(key)
        else:
            updated_lines.append(line)
    for key, value in values.items():
        if key not in seen:
            updated_lines.append(f"{key}={value}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(updated_lines).rstrip() + "\n", encoding="utf-8")


def _env_assignment_key(line: str) -> str | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or "=" not in stripped:
        return None
    key = stripped.split("=", 1)[0].strip()
    if not key or any(char.isspace() for char in key):
        return None
    return key


@admin_app.command("inspect-pet")
def admin_inspect_pet(
    theme: str = THEME_ARGUMENT,
    pets_root: Path | None = PETS_ROOT_OPTION,
) -> None:
    """Inspect a pet theme and print the frame plan used by the widget."""
    assets_root = default_assets_root()
    resolved_pets_root = pets_root or default_codex_pets_root()
    try:
        manifest = load_manifest_for_theme(
            theme,
            assets_root=assets_root,
            pets_root=resolved_pets_root,
        )
        asset_root = manifest.asset_root or assets_root
        missing = validate_theme_assets(manifest, asset_root)
        if missing:
            missing_summary = ",".join(path.as_posix() for path in missing)
            raise ValueError(f"theme missing assets: {missing_summary}")
    except Exception as exc:
        typer.echo(f"pet inspection failed: {exc}")
        raise typer.Exit(code=1) from exc

    typer.echo(f"pet={manifest.name}")
    typer.echo(f"theme_format={'codex_pet' if manifest.spritesheet is not None else 'coding_pet'}")
    typer.echo(f"assets_root={asset_root}")
    if manifest.spritesheet is not None:
        _print_codex_pet_inspection(manifest, asset_root)
    else:
        _print_coding_pet_inspection(manifest, asset_root)


def _print_codex_pet_inspection(manifest: object, asset_root: Path) -> None:
    from coding_pet.gui.theme import ThemeManifest

    typed_manifest = manifest
    if not isinstance(typed_manifest, ThemeManifest) or typed_manifest.spritesheet is None:
        return
    sheet = typed_manifest.spritesheet
    spritesheet_path = asset_root / sheet.path
    image_size = read_image_size(spritesheet_path)
    typer.echo(f"spritesheet={sheet.path.as_posix()}")
    typer.echo(f"atlas_size={image_size.width}x{image_size.height}")
    typer.echo(f"atlas_grid={sheet.columns}x{sheet.rows}")
    typer.echo(f"frame_size={sheet.frame_width}x{sheet.frame_height}")
    typer.echo(f"frame_duration_ms={sheet.frame_duration_ms}")
    for mood in WidgetMood:
        row = sheet.row_by_mood.get(mood, 0)
        frames = codex_pet_frame_count(sheet, mood)
        rect = codex_pet_frame_rect(sheet, mood, frame=0)
        durations = ",".join(
            str(codex_pet_frame_duration_ms(sheet, mood, frame=frame)) for frame in range(frames)
        )
        typer.echo(
            f"mood={mood.value} row={row} frames={frames} "
            f"first_rect={rect.x},{rect.y},{rect.width},{rect.height} "
            f"durations_ms={durations}"
        )


def _print_coding_pet_inspection(manifest: object, asset_root: Path) -> None:
    from coding_pet.gui.theme import ThemeManifest

    typed_manifest = manifest
    if not isinstance(typed_manifest, ThemeManifest):
        return
    for mood in WidgetMood:
        sprite = resolve_sprite_for_mood(typed_manifest, mood, assets_root=asset_root)
        typer.echo(
            f"mood={mood.value} asset={sprite.as_posix()} "
            f"exists={str((asset_root / sprite).exists()).lower()}"
        )


@admin_app.command("render-pet-frame")
def admin_render_pet_frame(
    theme: str = THEME_ARGUMENT,
    mood: WidgetMood = MOOD_OPTION,
    output: Path = OUTPUT_OPTION,
    pets_root: Path | None = PETS_ROOT_OPTION,
) -> None:
    """Render one pet frame to a PNG preview file."""
    from coding_pet.gui.preview import PreviewRenderError, render_pet_frame_preview

    try:
        preview = render_pet_frame_preview(
            theme,
            mood=mood,
            output_path=output,
            pets_root=pets_root,
        )
    except PreviewRenderError as exc:
        typer.echo(f"pet render failed: {exc}")
        raise typer.Exit(code=1) from exc
    typer.echo(f"rendered_pet={preview.theme}")
    typer.echo(f"mood={preview.mood.value}")
    typer.echo(f"output={preview.output_path}")
    typer.echo(f"output_size={preview.output_size[0]}x{preview.output_size[1]}")
    typer.echo(f"source={preview.source_path}")
    if preview.source_rect is not None:
        rect = preview.source_rect
        typer.echo(f"source_rect={rect.x},{rect.y},{rect.width},{rect.height}")


@admin_app.command("render-pet-contact-sheet")
def admin_render_pet_contact_sheet(
    theme: str = THEME_ARGUMENT,
    output: Path = OUTPUT_OPTION,
    pets_root: Path | None = PETS_ROOT_OPTION,
    cell_width: int = CELL_WIDTH_OPTION,
) -> None:
    """Render a Codex/Petdex pet atlas contact sheet to a PNG file."""
    from coding_pet.gui.preview import PreviewRenderError, render_pet_contact_sheet

    try:
        preview = render_pet_contact_sheet(
            theme,
            output_path=output,
            pets_root=pets_root,
            cell_width=cell_width,
        )
    except PreviewRenderError as exc:
        typer.echo(f"pet contact sheet failed: {exc}")
        raise typer.Exit(code=1) from exc
    typer.echo(f"rendered_pet={preview.theme}")
    typer.echo(f"output={preview.output_path}")
    typer.echo(f"output_size={preview.output_size[0]}x{preview.output_size[1]}")
    typer.echo(f"source={preview.source_path}")
    typer.echo(f"atlas_grid={preview.columns}x{preview.rows}")
    typer.echo(f"used_frames={preview.used_frames}")


@admin_app.command("render-pet-animation-previews")
def admin_render_pet_animation_previews(
    theme: str = THEME_ARGUMENT,
    output_dir: Path = OUTPUT_DIR_OPTION,
    pets_root: Path | None = PETS_ROOT_OPTION,
    size: int = PREVIEW_SIZE_OPTION,
) -> None:
    """Render one animated GIF preview per Codex/Petdex atlas row."""
    from coding_pet.gui.preview import PreviewRenderError, render_pet_animation_previews

    try:
        preview = render_pet_animation_previews(
            theme,
            output_dir=output_dir,
            pets_root=pets_root,
            size=size,
        )
    except PreviewRenderError as exc:
        typer.echo(f"pet animation previews failed: {exc}")
        raise typer.Exit(code=1) from exc
    typer.echo(f"rendered_pet={preview.theme}")
    typer.echo(f"output_dir={preview.output_dir}")
    typer.echo(f"source={preview.source_path}")
    typer.echo(f"atlas_grid={preview.columns}x{preview.rows}")
    typer.echo(f"preview_count={len(preview.preview_paths)}")
    for path in preview.preview_paths:
        typer.echo(f"preview={path}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
