# Next Implementation Plan

Last updated: 2026-05-20

Status: historical / superseded.

This file originally planned the transition from a monitored-session viewer into a live desktop control loop. That generic control-loop work has now been completed far enough for the constrained-server baseline: the daemon runtime exists, widget IPC can send action requests, action results are acknowledged, restored sessions are read-only, degraded paths return stable failure reasons, tmux discovery/capture/control exists, and transcript IPC refresh is implemented.

Use these newer documents as the current source of truth:

- `README.md` and `docs/architecture/coding-pet.md` for the current code contract.
- `docs/architecture/current-server-hardening-plan.md` for the locally verified constrained-server status.
- `docs/operations/company-server-handoff.md` for source-checkout, systemd, asset, wheel, and target-server validation steps.
- `docs/architecture/future-agent-enabled-server-plan.md` for real backend-native action semantics and backend-capable server work.

## Current Verified Baseline

Implemented today:

- `daemon run` boots `DaemonRuntime`, restores persisted sessions, starts `IpcServer`, and exposes a Unix socket.
- `widget run` loads persisted snapshots, connects to a live daemon socket when present, and falls back to demo/headless behavior when no daemon or GUI runtime is available.
- IPC supports `snapshot`, `session_updated`, `session_removed`, `action_request`, `action_result`, `transcript_request`, `transcript_snapshot`, `transcript_appended`, and `ping` flows.
- Panel actions cover `send_reply`, `approve`, and `reject` as daemon-routed intent, not widget-owned agent logic.
- Restored snapshot sessions are treated as read-only until a live daemon snapshot replaces them.
- Optional Claude Code/OpenCode backends remain registered, but missing binaries fail fast with explicit diagnostics.
- Tmux monitoring can discover already-running panes, capture bounded transcript rows, and deliver raw reply text via tmux buffers.
- The default sprite theme is the internal `company-pet` PNG theme, with the classic text theme retained as fallback.
- Systemd user units and wheel shared-data packaging are locally verified.

Latest local verification result:

```text
pytest: 154 passed
ruff: All checks passed!
mypy: no issues found in 80 source files
compileall: passed
systemd-analyze verify: passed
pip wheel: passed, including company-pet assets and systemd shared-data files
```

## What Remains

The remaining work is no longer the generic live-control-loop implementation from this historical plan. It is target/backend validation work:

- Validate real PySide6 GUI behavior on the actual company desktop session.
- Validate user-systemd startup on the target host with real `DISPLAY`/`WAYLAND_DISPLAY`/`XDG_RUNTIME_DIR` values.
- Validate Claude Code/OpenCode reply, approve, and reject semantics against real installed backends in disposable workspaces.
- Add any approved internal/company backend through the daemon adapter/registry boundary, not in widget code.
- Decide final company asset/brand policy if the internal `company-pet` pilot art is not sufficient.

## Closed Historical Phases

The old Phase 1-4 plan is considered closed for the current constrained baseline:

1. Daemon action routing: implemented.
2. Live control-channel plumbing: implemented at the generic adapter/stdin-control and tmux-control boundaries, with real backend-native semantics deferred.
3. Widget acknowledgement/feedback/transcript loop: implemented for current action-result and transcript-refresh behavior.
4. Operations documentation: superseded by the current hardening and company handoff docs.

Do not use this file to pick the next task. Use `future-agent-enabled-server-plan.md` for backend-rich work and `company-server-handoff.md` for target-server bring-up.
