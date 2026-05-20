# Current Server Hardening Status

Last verified: 2026-05-20

## Goal

Make `coding-pet` dependable on the current disk-constrained server without requiring local Claude Code or OpenCode installs. The current server remains a constrained/degraded-mode environment: the application must be testable, diagnosable, and operable even when no real local agent backends are installed.

## Constraints

- The current server has no Claude Code installed.
- The current server has no OpenCode installed.
- The current server does not have enough disk space to add those tools.
- Current-server work must remain useful and verifiable with zero real agent backends available.
- Anything that mainly depends on real backend behavior belongs in `docs/architecture/future-agent-enabled-server-plan.md`.

## Completion Status

Current-server hardening is complete for the constrained-server baseline.

Completed hardening:

- Backend availability detection exists through `AgentBackendRegistry`.
- `admin doctor` reports backend availability and degraded-mode environment diagnostics.
- `daemon monitor` fails fast with a clear unavailable-backend diagnostic when a requested backend binary is missing.
- `DaemonApp` resolves adapters through the backend registry instead of hardcoded daemon-side selection.
- Daemon action failures use stable reason strings for degraded paths.
- Widget action feedback preserves real session summaries and treats restored sessions as read-only.
- Tmux discovery/capture/control exists for already-running Claude Code/OpenCode panes without installing those CLIs on this server.
- SQLite transcripts, IPC transcript snapshots, and `transcript_appended` broadcasts support detail-popup transcript refresh.
- Backend-less tests cover unavailable backends, degraded action handling, restored/read-only sessions, and widget feedback behavior.
- Docs and smoke checks explicitly describe the constrained-server behavior.
- Company-safe PNG sprite assets are the default theme, with classic text sprites retained as fallback.
- Source-checkout systemd units can be configured through `~/.config/coding-pet/service.env` instead of hardcoding one checkout path.

## Verified Current-Server Checks

Run from a source checkout with `PYTHONPATH=src`.

Automated validation:

```bash
PYTHONPATH=src python -m pytest -q
PYTHONPATH=src python -m ruff check src tests scripts
PYTHONPATH=src python -m mypy src tests
PYTHONPATH=src python -m compileall -q src
python -m pip wheel . --no-deps -w /tmp/coding_pet_wheel
systemd-analyze verify \
  packaging/systemd/coding-pet-daemon.service \
  packaging/systemd/coding-pet-widget.service \
  packaging/systemd/coding-pet.target
```

2026-05-20 result:

- `154 passed`
- `ruff`: all checks passed
- `mypy`: no issues found in 80 source files
- `compileall`: passed
- `pip wheel`: passed; wheel includes seven `company-pet` PNGs, the theme manifest, and systemd shared-data files under `share/coding-pet/`
- `systemd-analyze verify`: passed

Runtime smoke checks:

```bash
PYTHONPATH=src python -m coding_pet.cli admin doctor
CODING_PET_DAEMON_ONESHOT=1 PYTHONPATH=src python -m coding_pet.cli daemon run
PYTHONPATH=src python -m coding_pet.cli widget run
PYTHONPATH=src python -m coding_pet.cli daemon discover-tmux
PYTHONPATH=src python -m coding_pet.cli daemon monitor \
  --agent claude_code \
  --cmd "claude code 'summarize'" \
  --workspace /tmp
```

Expected constrained-server signals:

- `backend_claude_code=unavailable:not installed (missing 'claude')`
- `backend_opencode=unavailable:not installed (missing 'opencode')`
- `gui_runtime=unavailable:no_display` on this headless host; `gui_runtime=unavailable` covers missing Qt/PySide6 runtime libraries.
- `theme=company-pet` and `theme_missing_assets=none`.
- `daemon run` in oneshot mode prints `coding-pet daemon ready ...` and exits cleanly.
- `widget run` prints runtime/state information and gracefully reports unavailable GUI runtime when Qt cannot start or no graphical display is present.
- `discover-tmux` lists current panes and marks non-agent panes as ignored when no matching Claude/OpenCode rules apply.
- `daemon monitor` exits non-zero before launch with an unavailable-backend diagnostic.

## Remaining Work on This Server

Only maintenance and packaging polish should remain here:

- Re-run the smoke checks after environment, packaging, or dependency changes.
- Keep README and operations docs synchronized with actual CLI output.
- Validate user-service startup on the final target GUI session when systemd user services and desktop session variables are available.
- Do not add large backend-specific behavior on this server unless a real backend becomes available.

## Deferred to Future Backend-Enabled Server

The following are intentionally out of scope for the current constrained server and should be handled through `docs/architecture/future-agent-enabled-server-plan.md`:

- Rich per-session capability negotiation beyond simple availability/support checks.
- Backend-native reply, approve, and reject semantics validated against real installed backends.
- Backend-native transcript/process integration beyond the current tmux SQLite transcript path and IPC snapshot/appended-event contract.
- Internal/company backend support, including endpoint and credential handling.
- Real-backend integration testing, mixed-backend validation, and backend-specific operator workflows.

## Exit Criteria

The constrained-server track is considered complete when:

- The daemon no longer hardcodes adapter selection.
- Unavailable, unsupported, read-only, and dead-session flows produce deterministic failure reasons.
- Backend-less tests cover degraded cases and pass without real backend binaries.
- Current-server smoke checks pass without installing Claude Code or OpenCode.
- Default sprite assets are company-safe, complete for all production moods, and diagnosable through `admin doctor`.
- Remaining backend-rich work is explicitly deferred to the future server plan.

All of these criteria are met as of the verification above.
