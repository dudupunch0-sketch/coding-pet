from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from coding_pet.models import (
    INACTIVE_SESSION_ACTIONS,
    AgentKind,
    AttentionState,
    SessionStatus,
    action_capabilities_for,
    attention_priority,
)

CLAUDE_HOOK_EVENTS = (
    "PreToolUse",
    "PostToolUse",
    "PostToolUseFailure",
    "PermissionRequest",
    "Stop",
    "StopFailure",
    "SessionEnd",
)

HOOK_EVENT_STATE_MAP: dict[str, AttentionState] = {
    "pretooluse": AttentionState.RUNNING,
    "toolbefore": AttentionState.RUNNING,
    "toolexecutebefore": AttentionState.RUNNING,
    "posttooluse": AttentionState.IDLE,
    "toolafter": AttentionState.IDLE,
    "toolexecuteafter": AttentionState.IDLE,
    "posttoolusefailure": AttentionState.FAILED,
    "permissionrequest": AttentionState.NEEDS_PERMISSION,
    "permissionasked": AttentionState.NEEDS_PERMISSION,
    "stop": AttentionState.COMPLETED,
    "sessionend": AttentionState.COMPLETED,
    "sessionidle": AttentionState.COMPLETED,
    "stopfailure": AttentionState.FAILED,
    "sessionerror": AttentionState.FAILED,
}

ATTENTION_HOOK_STATES = {
    AttentionState.NEEDS_PERMISSION,
    AttentionState.NEEDS_CHOICE,
    AttentionState.NEEDS_INPUT,
    AttentionState.REVIEW_NEEDED,
    AttentionState.STALLED,
    AttentionState.COMPLETED,
    AttentionState.FAILED,
}


@dataclass(frozen=True, slots=True)
class HookEvent:
    agent_kind: AgentKind
    event_name: str
    session_id: str
    workspace: str
    title: str
    state: AttentionState
    summary: str


def normalize_hook_event_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def state_for_hook_event(value: str) -> AttentionState:
    normalized = normalize_hook_event_name(value)
    try:
        return HOOK_EVENT_STATE_MAP[normalized]
    except KeyError as exc:
        raise ValueError(f"unsupported hook event: {value!r}") from exc


def hook_session_id(
    *,
    agent_kind: AgentKind,
    raw_session_id: str | None,
    workspace: str,
) -> str:
    session = (raw_session_id or "").strip()
    if session:
        return f"hook-{agent_kind.value}-{session}"
    digest = hashlib.sha256(workspace.encode("utf-8")).hexdigest()[:12]
    return f"hook-{agent_kind.value}-{digest}"


def hook_event_from_message(message: dict[str, object]) -> HookEvent:
    agent = message.get("agent")
    if not isinstance(agent, str):
        raise ValueError("hook_event requires agent")
    try:
        agent_kind = AgentKind(agent)
    except ValueError as exc:
        raise ValueError(f"unsupported hook agent: {agent!r}") from exc

    event = message.get("event")
    if not isinstance(event, str) or not event.strip():
        raise ValueError("hook_event requires event")

    workspace_value = message.get("workspace")
    workspace = str(workspace_value).strip() if workspace_value is not None else ""
    if not workspace:
        workspace = str(Path.cwd())

    raw_session = message.get("session_id")
    session_id = hook_session_id(
        agent_kind=agent_kind,
        raw_session_id=raw_session if isinstance(raw_session, str) else None,
        workspace=workspace,
    )

    title_value = message.get("title")
    title = str(title_value).strip() if title_value is not None else ""
    if not title:
        title = f"{agent_kind.value} hook session"

    state = state_for_hook_event(event)
    summary_value = message.get("summary")
    summary = str(summary_value).strip() if summary_value is not None else ""
    if not summary:
        summary = f"{agent_kind.value} {event} -> {state.value}"

    return HookEvent(
        agent_kind=agent_kind,
        event_name=event,
        session_id=session_id,
        workspace=workspace,
        title=title,
        state=state,
        summary=summary,
    )


def status_for_hook_event(
    event: HookEvent,
    *,
    existing: SessionStatus | None = None,
) -> SessionStatus:
    now = datetime.now(UTC)
    return SessionStatus(
        session_id=event.session_id,
        agent_kind=event.agent_kind,
        title=event.title or (existing.title if existing is not None else event.session_id),
        workspace=event.workspace
        or (existing.workspace if existing is not None else str(Path.cwd())),
        state=event.state,
        summary=event.summary,
        last_event_at=now,
        attention_score=attention_priority(event.state),
        unread=event.state in ATTENTION_HOOK_STATES,
        live=existing.live if existing is not None else False,
        source_kind=existing.source_kind if existing is not None else "hook",
        tmux_pane_id=existing.tmux_pane_id if existing is not None else None,
        tmux_session_name=existing.tmux_session_name if existing is not None else None,
        tmux_window_pane=existing.tmux_window_pane if existing is not None else None,
        tmux_current_command=existing.tmux_current_command if existing is not None else None,
        last_input_at=existing.last_input_at if existing is not None else None,
        last_output_at=existing.last_output_at if existing is not None else None,
        last_dashboard_input=existing.last_dashboard_input if existing is not None else None,
        estimated_current_request=(
            existing.estimated_current_request if existing is not None else None
        ),
        agent_waiting_message=existing.agent_waiting_message if existing is not None else None,
        last_activity_at=now,
        state_reason=f"hook:{event.event_name}",
        output_hash=existing.output_hash if existing is not None else None,
        supported_actions=(
            existing.supported_actions
            if existing is not None
            else list(INACTIVE_SESSION_ACTIONS)
        ),
        action_capabilities=(
            existing.action_capabilities
            if existing is not None
            else action_capabilities_for(INACTIVE_SESSION_ACTIONS, source_kind="hook")
        ),
    )


def claude_settings_snippet(*, hook_script: Path) -> dict[str, object]:
    command = str(hook_script)

    def handler(event: str) -> dict[str, object]:
        return {
            "type": "command",
            "command": command,
            "args": ["claude_code", event],
            "async": True,
        }

    return {
        "hooks": {
            "PreToolUse": [{"matcher": "*", "hooks": [handler("PreToolUse")]}],
            "PostToolUse": [{"matcher": "*", "hooks": [handler("PostToolUse")]}],
            "PostToolUseFailure": [{"matcher": "*", "hooks": [handler("PostToolUseFailure")]}],
            "PermissionRequest": [{"matcher": "*", "hooks": [handler("PermissionRequest")]}],
            "Stop": [{"hooks": [handler("Stop")]}],
            "StopFailure": [{"matcher": "*", "hooks": [handler("StopFailure")]}],
            "SessionEnd": [{"matcher": "*", "hooks": [handler("SessionEnd")]}],
        }
    }


def merge_claude_settings(existing: dict[str, Any], *, hook_script: Path) -> dict[str, Any]:
    merged = dict(existing)
    raw_hooks = merged.get("hooks")
    hooks = dict(raw_hooks) if isinstance(raw_hooks, dict) else {}
    snippet_hooks = claude_settings_snippet(hook_script=hook_script)["hooks"]
    if not isinstance(snippet_hooks, dict):
        return merged
    for event in CLAUDE_HOOK_EVENTS:
        existing_entries = hooks.get(event)
        entries = list(existing_entries) if isinstance(existing_entries, list) else []
        snippet_entries = snippet_hooks.get(event)
        if not isinstance(snippet_entries, list):
            continue
        for snippet_entry in snippet_entries:
            if _claude_entry_installed(entries, event=event, hook_script=hook_script):
                continue
            entries.append(snippet_entry)
        hooks[event] = entries
    merged["hooks"] = hooks
    return merged


def claude_settings_has_hooks(settings: dict[str, Any], *, hook_script: Path) -> bool:
    raw_hooks = settings.get("hooks")
    if not isinstance(raw_hooks, dict):
        return False
    for event in CLAUDE_HOOK_EVENTS:
        entries = raw_hooks.get(event)
        if not isinstance(entries, list):
            return False
        if not _claude_entry_installed(entries, event=event, hook_script=hook_script):
            return False
    return True


def _claude_entry_installed(entries: list[object], *, event: str, hook_script: Path) -> bool:
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        handlers = entry.get("hooks")
        if not isinstance(handlers, list):
            continue
        for handler in handlers:
            if not isinstance(handler, dict):
                continue
            if handler.get("command") != str(hook_script):
                continue
            if handler.get("args") == ["claude_code", event]:
                return True
    return False


def opencode_plugin_source(*, hook_script: Path) -> str:
    script = json.dumps(str(hook_script))
    return f"""export const CodingPetPlugin = async ({{ $ }}) => {{
  const hookScript = {script};
  const runHook = async (event) => {{
    await $`${{hookScript}} opencode ${{event}}`;
  }};

  return {{
    "tool.execute.before": async () => await runHook("tool.execute.before"),
    "tool.execute.after": async () => await runHook("tool.execute.after"),
    event: async ({{ event }}) => {{
      if (event.type === "permission.asked") await runHook("permission.asked");
      if (event.type === "session.error") await runHook("session.error");
      if (event.type === "session.idle") await runHook("session.idle");
    }},
  }};
}};
"""


def opencode_plugin_has_hooks(source: str, *, hook_script: Path) -> bool:
    return (
        str(hook_script) in source
        and "tool.execute.before" in source
        and "tool.execute.after" in source
        and "permission.asked" in source
        and "session.error" in source
        and "session.idle" in source
    )


def hook_script_source() -> str:
    return """#!/usr/bin/env bash
set -u

AGENT="${1:-}"
EVENT="${2:-}"
if [ -z "$AGENT" ] || [ -z "$EVENT" ]; then
  exit 0
fi

HOOK_INPUT=""
if [ ! -t 0 ]; then
  HOOK_INPUT="$(cat 2>/dev/null || true)"
fi

json_first_field() {
  if [ -z "$HOOK_INPUT" ]; then
    return 0
  fi
  HOOK_INPUT="$HOOK_INPUT" "${PYTHON:-python3}" - "$@" 2>/dev/null <<'PY'
import json
import os
import sys

try:
    payload = json.loads(os.environ.get("HOOK_INPUT", "") or "{}")
except Exception:
    sys.exit(0)

def value_at_path(value, path):
    current = value
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current

for path in sys.argv[1:]:
    value = value_at_path(payload, path)
    if value is None or isinstance(value, (dict, list)):
        continue
    text = str(value).strip()
    if text:
        print(text)
        sys.exit(0)
PY
}

INPUT_SESSION_ID="$(
  json_first_field \
    session_id sessionId session.id conversation_id conversationId \
    thread_id threadId run_id runId || true
)"
INPUT_WORKSPACE="$(
  json_first_field \
    workspace.path workspace workspace_dir workspaceDir project_dir projectDir \
    cwd current_working_directory || true
)"
INPUT_TITLE="$(
  json_first_field \
    title session_title sessionTitle project_name projectName workspace.name || true
)"
INPUT_SUMMARY="$(
  json_first_field \
    summary message event.summary tool_name toolName name || true
)"

SESSION_ID="${CODING_PET_HOOK_SESSION_ID:-${CLAUDE_SESSION_ID:-${OPENCODE_SESSION_ID:-${INPUT_SESSION_ID}}}}"
WORKSPACE="${CODING_PET_HOOK_WORKSPACE:-${CLAUDE_PROJECT_DIR:-${INPUT_WORKSPACE:-${PWD}}}}"
TITLE="${CODING_PET_HOOK_TITLE:-${INPUT_TITLE:-${AGENT} hook session}}"
SUMMARY="${CODING_PET_HOOK_SUMMARY:-${INPUT_SUMMARY:-${EVENT}}}"

if [ -z "${CODING_PET_BIN:-}" ]; then
  if command -v coding-pet >/dev/null 2>&1; then
    CODING_PET_BIN="coding-pet"
  else
    CODING_PET_BIN="${PYTHON:-python3} -m coding_pet.cli"
  fi
fi

exec ${CODING_PET_BIN} daemon hook-event \\
  --agent "$AGENT" \\
  --event "$EVENT" \\
  --session-id "$SESSION_ID" \\
  --workspace "$WORKSPACE" \\
  --title "$TITLE" \\
  --summary "$SUMMARY" >/dev/null 2>&1 || true
"""
