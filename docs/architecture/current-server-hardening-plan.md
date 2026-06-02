# Current Server Hardening Status

Last verified: 2026-06-02

## Goal

Make `coding-pet` dependable on the current disk-constrained server without requiring local Claude Code or OpenCode installs. The current server remains a constrained/degraded-mode environment: the application must be testable, diagnosable, and operable even when no real local agent backends are installed.

## Constraints

- The current server has no Claude Code installed.
- The current server has no OpenCode installed.
- The current server does not require Codex; Codex remains an optional local-development adapter.
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
- Tmux discovery/capture/control exists for already-running Claude Code/OpenCode panes without installing those CLIs on this server, including raw replies plus adapter-defined approve/reject control text.
- Sessions expose structured `action_capabilities` with legacy
  `supported_actions` compatibility, and the daemon rejects actions outside
  that per-session capability contract before live dispatch.
- Action results expose normalized `outcome` values while preserving legacy
  `ok` compatibility, so future backend-native results can cross daemon and
  widget boundaries without losing meaning.
- Optional Codex tmux detection exists for local development, but is not part of the company-server target.
- SQLite transcripts, IPC transcript snapshots, and `transcript_appended`
  broadcasts support detail-popup transcript refresh, with default redaction for
  common token/password/API key patterns before persistence.
- Malformed IPC JSON and non-object socket payloads return structured errors
  without dropping the client connection.
- Detail-popup send, send-without-enter, and attach controls route daemon action requests over IPC in the same headless-tested path the widget uses.
- Backend-less tests cover unavailable backends, degraded action handling, restored/read-only sessions, and widget feedback behavior.
- Docs and smoke checks explicitly describe the constrained-server behavior.
- Offline-safe generated `codex-default` PNG sprite assets are the default theme, classic text sprites are retained as fallback, and PMD SpriteCollab sample character themes are registered as optional non-commercial choices.
- Source-checkout systemd units can be configured through `~/.config/coding-pet/service.env` instead of hardcoding one checkout path.
- Inactive completed sessions keep their pet visible briefly, then the daemon
  removes them according to `CODING_PET_SHOW_COMPLETED_FOR_SEC`; live completed
  sessions are not removed by this timer.
- Restored inactive completed sessions are pruned if their retention window
  already elapsed before daemon restart.
- State snapshot persistence uses atomic replacement to avoid corrupting the
  previous `state.json` on interrupted writes.
- Corrupt or schema-invalid snapshots are quarantined as `state.json.invalid.*`
  instead of crashing daemon/widget restore.
- Disappeared tmux panes become inactive completed sessions unless the session
  was already failed, in which case the failed state remains visible for review.
- Daemon-owned process monitors do not leave stale live sessions on shutdown;
  cancellation best-effort terminates the owned process and persists an
  inactive snapshot, with a configurable kill fallback after
  `CODING_PET_PROCESS_STOP_TIMEOUT_SEC`.

## Verified Current-Server Checks

Run from a source checkout with `PYTHONPATH=src`.

Automated validation:

```bash
PYTHONPATH=src python -m pytest -q
PYTHONPATH=src python -m ruff check src tests scripts
PYTHONPATH=src python -m mypy src tests
PYTHONPATH=src python -m compileall -q src
python -m pip wheel . --no-deps -w /tmp/coding_pet_wheel
systemd-analyze --user verify \
  packaging/systemd/coding-pet-daemon.service \
  packaging/systemd/coding-pet-widget.service \
  packaging/systemd/coding-pet.target
```

2026-05-20 result before the optional Codex adapter refactor:

- `154 passed`
- `ruff`: all checks passed
- `mypy`: no issues found in 80 source files
- `compileall`: passed
- `pip wheel`: passed; wheel includes Python modules, `codex-default` PNGs, classic fallback assets, 20 PMD SpriteCollab sample themes, the theme manifest/registry, operations docs, RHEL requirements, and systemd shared-data files under `share/coding-pet/`
- `systemd-analyze --user verify`: passed

2026-06-02 WSL/Linux verification after the Python 3.12 and Codex pet-package refactor:

- `465 passed`
- `ruff`: all checks passed
- `mypy`: no issues found in 86 source files
- `compileall`: passed with Python 3.12.3
- `admin evidence-bundle --profile current`: passed and writes
  `systemd-units.json`, `systemd-runtime.json`, `widget-smoke.json`, and
  `hook-event-smoke.json` alongside acceptance, environment, tmux, wheelhouse,
  copied-pet, and hook installation evidence; runtime/optional reports include
  explicit `profile` metadata, transcript evidence records the configured custom
  redaction pattern count, and `summary.json` includes schema version 1, an ISO
  timestamp, and a base artifact manifest
- `admin wheelhouse-check`: static checks, required-distribution wheel records,
  SHA-256/size transfer manifest, `coding_pet` wheel shared-data inspection, and
  installed PySide6/theme/systemd smoke were verified for the offline packaging
  path
- `admin evidence-bundle --require-pet-packages`: copied pet package evidence
  includes per-package SHA-256, size, file count, source package, and manifest
  metadata, plus consistent `total`, `passed`, `failed`, and `pets` counts
- `admin backend-evidence-check` and `admin target-evidence-check` require
  real backend action reports and their backend summary manifest to record the
  accepted outcome, not just legacy `ok=true`
- Target `summary.json` manifests include `backend-summary.json` and all
  required Claude Code/OpenCode backend report paths.

Runtime smoke checks:

```bash
PYTHONPATH=src python -m coding_pet.cli admin doctor
CODING_PET_DAEMON_ONESHOT=1 PYTHONPATH=src python -m coding_pet.cli daemon run
PYTHONPATH=src python -m coding_pet.cli widget run
PYTHONPATH=src python -m coding_pet.cli daemon discover-tmux
PYTHONPATH=src python -m coding_pet.cli admin tmux-control-check \
  --json-out /tmp/coding-pet-tmux-control-check.json
PYTHONPATH=src python -m coding_pet.cli admin systemd-unit-check \
  --json-out /tmp/coding-pet-systemd-units.json
PYTHONPATH=src python -m coding_pet.cli admin wheelhouse-check wheelhouse \
  --json-out /tmp/coding-pet-wheelhouse.json
PYTHONPATH=src python -m coding_pet.cli daemon monitor \
  --agent claude_code \
  --cmd "claude code 'summarize'" \
  --workspace /tmp
```

Expected constrained-server signals:

- `backend_claude_code=unavailable:not installed (missing 'claude')`
- `backend_opencode=unavailable:not installed (missing 'opencode')`
- `backend_codex=unavailable:not installed (missing 'codex')` when the optional Codex adapter is not installed
- `gui_runtime=unavailable:no_display` on this headless host; `gui_runtime=unavailable` covers missing Qt/PySide6 runtime libraries.
- `theme=codex-default` and `theme_missing_assets=none`.
- `daemon run` in oneshot mode prints `coding-pet daemon ready ...` and exits cleanly.
- `widget run` prints runtime/state information and gracefully reports unavailable GUI runtime when Qt cannot start or no graphical display is present.
- `discover-tmux` lists current panes and marks non-agent panes as ignored when no matching Claude/OpenCode/Codex rules apply.
- `admin tmux-control-check` creates a disposable tmux session and reports `tmux_control_check=ok` when raw text survives the buffer paste path.
- `admin systemd-unit-check` records `systemd_units=ok` when the packaged
  user unit files pass `systemd-analyze --user verify`.
- `daemon monitor` exits non-zero before launch with an unavailable-backend diagnostic.

## Remaining Work on This Server

Only maintenance and packaging polish should remain here:

- Re-run the smoke checks after environment, packaging, or dependency changes.
- Keep README and operations docs synchronized with actual CLI output.
- Validate user-service startup on the final target GUI session when systemd user services and desktop session variables are available.
- Do not add large backend-specific behavior on this server unless a real backend becomes available.

## Deferred to Future Backend-Enabled Server

The following are intentionally out of scope for the current constrained server and should be handled through `docs/architecture/future-agent-enabled-server-plan.md`:

- Rich backend-native capability negotiation beyond the current structured
  action capability seed.
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
- Default `codex-default` sprite assets are generated original repo assets, PMD sample assets preserve non-commercial attribution, all registered production moods are complete, and the active theme is diagnosable through `admin doctor`.
- Remaining backend-rich work is explicitly deferred to the future server plan.

All of these criteria are met as of the verification above.
