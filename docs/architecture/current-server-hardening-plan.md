# Current Server Hardening Plan

## Goal

Make `coding-pet` reliable and deployable on the current server without requiring local Claude Code or OpenCode installations. The work on this server should harden the core daemon, IPC, widget, diagnostics, packaging, and docs so the system behaves correctly when agent backends are absent, partial, or optional.

## Constraints

- This plan is only for the current server environment.
- Assume this server does not have Claude Code or OpenCode installed.
- Assume this server does not have enough disk space to install them.
- Do not require those CLIs locally for development, testing, verification, or operations on this server.
- Agent-specific launch/control semantics can be validated later on a different server that actually has those backends installed.
- Keep the implementation practical: prefer capability detection, optional backend behavior, and generic abstractions over backend-coupled logic.

## Current Baseline

- The daemon runtime, persistence, and Unix-socket IPC path already exist.
- Widget live mode is already implemented.
- `action_result` feedback is already implemented.
- Restored sessions already behave as read-only until replaced by live state.
- Reconnect reset behavior is already implemented, with fresh snapshot state becoming authoritative again.
- Docs sync for the current implemented baseline is already in place.
- The remaining work on this server is not building those features; it is hardening and generalizing them.

## In Scope on This Server

- Harden backend discovery and optional-backend behavior.
- Replace hard backend assumptions with capability detection and optional dependencies.
- Ensure graceful degradation when adapters or backends are unavailable.
- Improve diagnostics, logging, and operator-facing failure messages.
- Strengthen tests using fakes/stubs so the suite does not require Claude Code or OpenCode.
- Tighten deployment packaging and service behavior for a constrained server.
- Update docs so operators know exactly what works on this server and what is deferred.

## Out of Scope on This Server

- Installing Claude Code locally.
- Installing OpenCode locally.
- Requiring extra disk allocation to support those CLIs.
- Validating real backend approval/reject/reply semantics against live Claude Code or OpenCode sessions.
- Shipping backend-specific behavior changes that can only be proven with those CLIs present.
- Treating missing local backends as a blocker for daemon/widget/core-runtime readiness.

## Workstreams

### Phase 1: Remove hard backend assumptions

- Add a backend capability layer so core code asks what is available instead of assuming `claude` or `opencode` exists.
- Keep backend registrations optional; unavailable backends should remain known to the system but marked unavailable with a reason.
- Replace direct adapter selection in `src/coding_pet/daemon/app.py` with a registry or capability lookup.
- Extend `src/coding_pet/agents/base.py` with explicit capability metadata such as launch support, control support, and availability reason.
- Add a small registry module such as `src/coding_pet/agents/registry.py` or `src/coding_pet/agents/capabilities.py`.
- Limit model changes in `src/coding_pet/models.py` to what is needed to represent unavailable or non-interactive backends cleanly.

### Phase 2: Graceful degradation in daemon, IPC, and widget

- Make `daemon monitor` fail fast with a clear, actionable error when a requested backend is unavailable instead of failing later during process launch.
- Ensure action routing returns deterministic `action_result` failures for unsupported, unavailable, dead, or read-only sessions.
- Keep restored sessions and unavailable-backend sessions visibly non-interactive in the widget.
- Preserve current read-only behavior while making the reason explicit to operators and tests.
- Touch points: `src/coding_pet/cli.py`, `src/coding_pet/daemon/manager.py`, `src/coding_pet/daemon/action_router.py`, `src/coding_pet/gui/app.py`, `src/coding_pet/gui/widget.py`.

### Phase 3: Diagnostics and observability

- Expand `admin doctor` to report backend capability detection, runtime prerequisites, writable paths, socket path, notification path, and GUI/runtime availability.
- Add structured logs for backend discovery, disabled features, action rejection reasons, and degraded-mode startup paths.
- Make degraded operation easy to diagnose from logs without needing the missing CLIs.
- Touch points: `src/coding_pet/cli.py`, `src/coding_pet/config.py` if needed, logging helpers, and daemon startup paths.

### Phase 4: Test strategy without Claude Code or OpenCode

- Add unit tests that monkeypatch backend discovery rather than invoking real CLIs.
- Add fake adapters and fake controllable processes for launch/control-path tests.
- Cover unavailable-backend flows, read-only flows, doctor output, and degraded widget behavior.
- Keep all CI and local verification on this server runnable without installing Claude Code or OpenCode.
- Touch points: new tests around backend capability detection plus updates to `tests/test_cli.py`, `tests/test_daemon_runtime.py`, `tests/test_widget_action_feedback.py`, and related widget/IPC coverage.

### Phase 5: Docs and operator guidance

- Update `README.md` to describe the constrained-server operating model and explicitly state that local Claude Code/OpenCode installation is not required on this server.
- Update `docs/operations/rhel8-setup.md` with degraded-mode expectations, troubleshooting, and what `admin doctor` should report when backends are absent.
- Update `docs/architecture/coding-pet.md` to document capability detection, optional backend behavior, and which semantics are deferred for validation on another server.
- Keep examples focused on commands that are valid on this server: daemon runtime, widget startup, doctor, tests, and service verification.

### Phase 6: Deployability hardening

- Verify user-service packaging does not assume backend binaries are present.
- Add smoke-level deploy checks for daemon startup, widget startup fallback, and systemd unit validation.
- Ensure startup remains useful on a server where backend discovery reports “unavailable” across the board.
- Touch points: `packaging/systemd/*.service`, `scripts/run_daemon.py`, `scripts/run_widget.py`, and operator docs.

## Verification

- Run the Python test suite with backend discovery mocked or stubbed: no test should require Claude Code or OpenCode on this server.
- Verify `coding-pet admin doctor` reports backend availability clearly and does not treat missing backends as an internal error.
- Verify `coding-pet daemon run` can start cleanly in this environment.
- Verify `coding-pet widget run` still reports live/degraded state cleanly and handles missing GUI/runtime pieces gracefully.
- Verify `systemd-analyze verify packaging/systemd/coding-pet-daemon.service packaging/systemd/coding-pet-widget.service packaging/systemd/coding-pet.target`.
- Treat live backend semantic validation as a separate follow-up on another server, not part of this server’s exit gate.

## Exit Criteria

- Core daemon, IPC, widget, doctor, and packaging flows work on this server without local Claude Code or OpenCode.
- Backend absence is handled through capability detection and optional behavior, not implicit assumptions.
- Unavailable adapters degrade gracefully with explicit operator-facing reasons.
- The automated test strategy on this server covers degraded and optional-backend paths without installing those CLIs.
- Docs clearly separate what is hardened and supported on this server from what must be validated later on a backend-capable server.
- Remaining backend-specific semantic validation is explicitly deferred, tracked, and no longer blocks core server robustness.
