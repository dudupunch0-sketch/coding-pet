# Next Implementation Plan

Last updated: 2026-06-02

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
- IPC supports `snapshot`, `session_updated`, `session_removed`, `action_request`, normalized-outcome `action_result`, `transcript_request`, `transcript_snapshot`, `transcript_appended`, and `ping` flows.
- Panel actions cover `send_reply`, `approve`, and `reject` as daemon-routed intent, not widget-owned agent logic.
- Restored snapshot sessions are treated as read-only until a live daemon snapshot replaces them.
- Claude Code/OpenCode backends remain registered, and missing binaries fail fast with explicit diagnostics. Codex is optional for local development only.
- Tmux monitoring can discover already-running panes, capture bounded transcript rows, and deliver raw reply text plus adapter-defined approve/reject control text via tmux buffers.
- The default sprite theme is the internal `codex-default` PNG theme, with the classic text theme retained as fallback and 20 PMD SpriteCollab sample character themes registered as optional choices.
- Systemd user units plus wheel shared-data packaging for assets, docs, requirements, and systemd files are locally verified.

Current WSL/Linux verification result:

```text
pytest: 465 passed
ruff: All checks passed!
mypy: no issues found in 86 source files
compileall: passed with Python 3.12.3
```

Previous full local verification result:

```text
compileall: passed
systemd-analyze --user verify: passed
pip wheel: passed, including Python modules, codex-default assets, classic fallback, 20 PMD SpriteCollab sample themes, theme registry, operations docs, RHEL requirements, and systemd shared-data files
```

## What Remains

The remaining work is no longer the generic live-control-loop implementation from this historical plan. It is target/backend validation work:

- Validate real PySide6 GUI behavior on the actual company desktop session.
- Validate user-systemd startup on the target host with real `DISPLAY`/`WAYLAND_DISPLAY`/`XDG_RUNTIME_DIR` values.
- Validate Claude Code/OpenCode reply, approve, and reject semantics against real installed backends in disposable workspaces.
- Add any approved internal/company backend through the daemon adapter/registry boundary, not in widget code.
- Decide final company asset/brand policy if the generated `codex-default` fallback and CC BY-NC PMD sample themes are not sufficient.

## Closed Historical Phases

The old Phase 1-4 plan is considered closed for the current constrained baseline:

1. Daemon action routing: implemented.
2. Live control-channel plumbing: implemented at the generic adapter/stdin-control and tmux-control boundaries, including tmux approve/reject transport, with real backend-native semantics deferred.
3. Widget acknowledgement/feedback/transcript loop: implemented for current action-result and transcript-refresh behavior.
4. Operations documentation: superseded by the current hardening and company handoff docs.

Do not use this file to pick the next task. Use `future-agent-enabled-server-plan.md` for backend-rich work and `company-server-handoff.md` for target-server bring-up.
