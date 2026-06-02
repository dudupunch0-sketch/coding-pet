# coding-pet

Last verified locally: 2026-06-02

coding-pet is a production-quality desktop companion for monitoring local AI coding-agent sessions on Linux systems such as Red Hat Enterprise Linux 8.10.

## Current direction

- Python application with a long-running daemon and GUI widget layer
- One pet per monitored session
- Shared control panel for all sessions
- Claude Code CLI and OpenCode CLI are the production targets
- Codex CLI support is optional and only intended as a local development/smoke adapter when `codex` is installed
- Screen-edge stack layout for multiple pets
- Intranet-friendly deployment through prebuilt wheelhouses; no runtime dependency download

## Current implementation status

Implemented today:
- typed session and event models
- concurrent daemon monitor manager
- Claude Code, OpenCode, and optional Codex adapters
- registry-backed optional backend detection with fail-fast degraded behavior when local agent binaries are unavailable
- structured logging and XDG-aware configuration
- daemon/widget IPC over Unix domain sockets
- malformed IPC messages receive structured error responses without dropping
  the daemon connection
- desktop notification backend with cooldowns
- widget shell, panel view model, and snapshot boot support
- JSON state persistence for restart resilience
- packaged systemd user-service unit files
- offline-safe Codex-style default PNG sprite theme, retained classic text fallback assets, and 20 selectable PMD SpriteCollab sample character themes
- `daemon run`, `widget run`, and `admin doctor` CLI runtime commands
- daemon-owned live action routing for `send_reply`, `send_without_enter`, `approve`, and `reject`
- per-session `action_capabilities` with legacy `supported_actions` compatibility
  so the widget only exposes actions the daemon can route
- normalized `action_result` messages include stable `outcome` values
  (`accepted`, `local_updated`, `rejected`, `timed_out`, `unsupported`,
  `backend_failed`) while preserving legacy `ok` compatibility
- backend/target evidence checks reject real-backend reports or backend summary
  entries that omit the accepted action outcome
- completed inactive sessions stay visible briefly and are then removed by the
  daemon; tune the retention with `CODING_PET_SHOW_COMPLETED_FOR_SEC`
- daemon restart does not resurrect completed pets whose retention window has
  already elapsed
- state snapshots are written with atomic replace semantics so interrupted
  writes do not corrupt the previous snapshot
- unreadable or schema-invalid state snapshots are quarantined as
  `state.json.invalid.*` and ignored during restore
- tmux pane discovery/capture/control modules for already-running Claude Code/OpenCode sessions, with Codex detection available for local development
- offline-safe Claude Code/OpenCode hook-event ingress for tool/session state changes
- SQLite transcript store with timestamped `in`, `out`, hook-event, and `system`
  events plus default and configurable regex redaction for token/password/API key
  patterns
- IPC transcript snapshot requests plus appended-event streaming to connected widgets
- rule-based tmux snapshot classifier for `needs_input`, `needs_choice`, `needs_permission`, `stalled`, and failure states
- headless-safe detail popup/view-model/reply-box helpers for raw tmux action request construction
- normalized action failure reasons for unavailable, unsupported, missing, read-only, and no-live-control-channel paths
- explicit widget action feedback plus read-only restored-session handling
- detail-popup open flow that requests the latest transcript, sends daemon `mark_read`, and wires send/attach/hide actions back through IPC
- Codex/Petdex/CodexPets package validation with real PNG/WebP atlas pixel checks plus official Codex row frame counts and frame durations
- RHEL 8.10 offline wheelhouse docs and constraints under `requirements/` and `docs/operations/offline-rhel8-wheelhouse.md`

Still in progress:
- validating real Claude Code/OpenCode backend-native action outcomes for the adapter-defined control messages
- richer manual GUI UX polish in a full PySide6 environment
- company-specific deployment validation on the target server
- custom/licensed production art beyond the bundled PMD SpriteCollab sample character set

## Packaging and user services

The package already exports a console entrypoint:
```bash
coding-pet --help
```

The repository now includes user-service unit files under `packaging/systemd/`:
- `coding-pet-daemon.service`
- `coding-pet-widget.service`
- `coding-pet.target`

Validate them with:
```bash
systemd-analyze --user verify \
  packaging/systemd/coding-pet-daemon.service \
  packaging/systemd/coding-pet-widget.service \
  packaging/systemd/coding-pet.target
```

For a source checkout, first create `~/.config/coding-pet/service.env` from the checked-in template and set the target-server paths:
```bash
mkdir -p ~/.config/coding-pet ~/.config/systemd/user
cp packaging/systemd/coding-pet.service.env.example ~/.config/coding-pet/service.env
$EDITOR ~/.config/coding-pet/service.env
```

Then install/link the user service files:
```bash
cp packaging/systemd/coding-pet-daemon.service ~/.config/systemd/user/
cp packaging/systemd/coding-pet-widget.service ~/.config/systemd/user/
cp packaging/systemd/coding-pet.target ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now coding-pet.target
```

## Development setup

```bash
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
PYTHONPATH=src python -m pytest -q
```

For a minimal runtime install without the GUI extra:
```bash
python -m pip install -e .
```

For the widget runtime:
```bash
python -m pip install -e '.[gui]'
```

## Local verification gate

Run the meaningful local gate in WSL or another Linux environment, not Git Bash
or native Windows. The target profile records the host platform and requires
`platform.system() == "Linux"` so Windows-side evidence cannot accidentally
stand in for the RHEL desktop.

The current WSL/Linux verification passed with:

```text
pytest: 465 passed
ruff: All checks passed!
mypy: no issues found in 86 source files
compileall: passed with Python 3.12.3
systemd unit/runtime, widget, wheelhouse, pet-package, hook, and hook-event smoke artifacts: recorded by admin evidence-bundle with explicit profile metadata
wheelhouse check: static wheels, SHA-256 transfer manifest, coding-pet shared data, and installed PySide6/theme/systemd smoke paths verified
```

The previous constrained-server verification also passed with:

```text
compileall: passed
systemd-analyze --user verify: passed
pip wheel: passed
wheel contents: Python modules, codex-default PNGs, classic text fallback, 20 PMD SpriteCollab sample character themes, theme registry, default manifest, operations docs, RHEL requirements, and systemd shared-data files present
```

The built wheel installs shared data under `share/coding-pet/`, including:
- `share/coding-pet/assets/sprites/theme-manifest.json`
- `share/coding-pet/assets/sprites/codex-default/*.png`
- `share/coding-pet/assets/sprites/classic/*.txt`
- `share/coding-pet/assets/sprites/pmd-*/*.png`
- `share/coding-pet/assets/sprites/theme-registry.json`
- `share/coding-pet/docs/operations/offline-rhel8-wheelhouse.md`
- `share/coding-pet/docs/operations/codex-pet-packages.md`
- `share/coding-pet/docs/operations/llm-target-execution-runbook.md`
- `share/coding-pet/requirements/constraints-rhel8.txt`
- `share/coding-pet/requirements/rhel8-runtime.txt`
- `share/coding-pet/systemd/coding-pet.service.env.example`
- `share/coding-pet/systemd/coding-pet-daemon.service`
- `share/coding-pet/systemd/coding-pet-widget.service`
- `share/coding-pet/systemd/coding-pet.target`

## Verified commands

These commands were verified against the current source tree in this repository snapshot.

Show top-level CLI help:
```bash
PYTHONPATH=src python -m coding_pet.cli --help
```

Show daemon help:
```bash
PYTHONPATH=src python -m coding_pet.cli daemon --help
```

Show daemon monitor command help:
```bash
PYTHONPATH=src python -m coding_pet.cli daemon monitor --help
```

Show tmux discovery command help:
```bash
PYTHONPATH=src python -m coding_pet.cli daemon discover-tmux --help
```

Run current-host acceptance diagnostics:
```bash
PYTHONPATH=src python -m coding_pet.cli admin acceptance-check \
  --profile current \
  --json-out /tmp/coding-pet-acceptance-current.json
```

Run target RHEL acceptance diagnostics on the company server:
```bash
PYTHONPATH=src python -m coding_pet.cli admin acceptance-check \
  --profile target \
  --json-out /tmp/coding-pet-acceptance-target.json
```

Collect acceptance, environment, tmux transport, systemd user-unit, widget smoke,
hook-event smoke, and hook-installation evidence into one directory:
```bash
PYTHONPATH=src python -m coding_pet.cli admin evidence-bundle \
  --profile target \
  --output-dir /tmp/coding-pet-target-evidence \
  --wheelhouse wheelhouse \
  --require-wheelhouse \
  --pet-source /path/to/downloaded-pets \
  --require-pet-packages
```
If Claude Code/OpenCode hooks are an approved deployment requirement, add
`--require-agent-hooks` so missing hook installation fails the bundle gate.
If the offline package set is validated separately, omit `--wheelhouse` and
`--require-wheelhouse`; the bundle will still write a skipped `wheelhouse.json`.
If copied Codex/Petdex pets are not part of the release gate, omit
`--pet-source` and `--require-pet-packages`; the bundle will still write a
skipped `pet-packages.json`.

Verify packaged systemd user units directly:
```bash
PYTHONPATH=src python -m coding_pet.cli admin systemd-unit-check \
  --json-out /tmp/coding-pet-systemd-units.json
```

After enabling the user services on the target desktop session, verify that the
target and both services are active:
```bash
PYTHONPATH=src python -m coding_pet.cli admin systemd-runtime-check \
  --json-out /tmp/coding-pet-systemd-runtime.json
```

Validate a copied offline wheelhouse before target install:
```bash
PYTHONPATH=src python -m coding_pet.cli admin wheelhouse-check wheelhouse \
  --json-out /tmp/coding-pet-wheelhouse.json
```

Verify raw tmux paste transport in a disposable probe session:
```bash
PYTHONPATH=src python -m coding_pet.cli admin tmux-control-check \
  --json-out /tmp/coding-pet-tmux-control-check.json
```

Check that the selected pet theme can create a widget shell. Add `--required`
on the target desktop session to require actual Qt widget creation:
```bash
PYTHONPATH=src python -m coding_pet.cli admin widget-smoke-check \
  --json-out /tmp/coding-pet-widget-smoke.json
```

Verify that one hook event reaches the running daemon, appears in SQLite
transcripts, and can be cleaned up locally:
```bash
PYTHONPATH=src python -m coding_pet.cli admin hook-event-smoke-check \
  --json-out /tmp/coding-pet-hook-event-smoke.json
```

Run the widget layer:
```bash
PYTHONPATH=src python -m coding_pet.cli widget run
```

List bundled and imported pet themes:
```bash
PYTHONPATH=src python -m coding_pet.cli admin list-pets
```

On an internet-connected staging workstation, download one Petdex pet by slug
into a transfer directory:
```bash
PYTHONPATH=src python -m coding_pet.cli admin download-petdex boba \
  --output-dir /tmp/downloaded-pets \
  --json-out /tmp/downloaded-pets/boba-download.json
```
This writes `/tmp/downloaded-pets/boba.zip` plus
`/tmp/downloaded-pets/boba.petdex.json`, including the source URLs, ZIP
SHA-256, byte size, and validation report. Copy those files into the intranet;
`validate-pet-batch` and target evidence keep the sidecar as
`petdex_metadata` and check that its archive hash still matches the copied ZIP.
The target runtime still does not download external pet files.

Validate a copied Codex/Petdex pet package before enabling it:
```bash
PYTHONPATH=src python -m coding_pet.cli admin validate-pet /path/to/downloaded-pet \
  --json-out /tmp/coding-pet-validation.json
```
`/path/to/downloaded-pet` may be a package directory, a `pet.json`,
`petjson.json`, or a ZIP download containing exactly one pet manifest.

The command verifies `pet.json`, local asset paths, symlinks, PNG/WebP header
dimensions, official atlas cell transparency/occupancy, official row timing,
and unsafe ZIP entries, then prints `atlas_size=...` plus `atlas_cells=ok` for
the detected spritesheet. The JSON report can be saved with target-server
acceptance evidence.
For current Petdex-style packages, a 1728x1664 spritesheet with no explicit
`states` metadata is inferred as a 9x8 Petdex atlas; the validator reports
`atlas_grid={"columns":9,"rows":8}` in JSON.
Explicit layout fields may be omitted, but if present they must be positive
integers; invalid `columns`, `rows`, or frame dimensions fail validation.
Batch validation and import discover both `pet.json` and Petdex-style
`petjson.json` manifests.

Validate a directory of copied ZIPs or extracted packages before moving them
onto the intranet target:
```bash
PYTHONPATH=src python -m coding_pet.cli admin validate-pet-batch /path/to/downloaded-pets \
  --json-out /tmp/coding-pet-pet-batch.json
```

Install a validated directory of copied ZIPs or extracted packages into the
configured pets root:
```bash
PYTHONPATH=src python -m coding_pet.cli admin import-pet-batch /path/to/downloaded-pets \
  --pets-root ~/.codex/pets \
  --json-out /tmp/coding-pet-pet-import-batch.json
```

Build the full pet QA bundle in one step:
```bash
PYTHONPATH=src python -m coding_pet.cli admin build-pet-qa /path/to/downloaded-pet \
  --output-dir /tmp/coding-pet-qa
```

Install a validated Codex/Petdex pet package into the local pets root:
```bash
PYTHONPATH=src python -m coding_pet.cli admin import-pet /path/to/downloaded-pet
```
ZIP downloads are safely extracted during validation and copied into the
configured pets root as a normal directory.

Persist the active pet in `~/.config/coding-pet/service.env` for systemd user
services:
```bash
PYTHONPATH=src python -m coding_pet.cli admin set-pet <pet-id>
```

Inspect the exact frame plan the widget will use before GUI validation:
```bash
PYTHONPATH=src python -m coding_pet.cli admin inspect-pet <pet-id>
```

Render a single frame preview PNG when PySide6 is available:
```bash
PYTHONPATH=src python -m coding_pet.cli admin render-pet-frame <pet-id> \
  --mood alert \
  --output /tmp/coding-pet-preview.png
```

Render a full Codex/Petdex atlas contact sheet for QA:
```bash
PYTHONPATH=src python -m coding_pet.cli admin render-pet-contact-sheet <pet-id> \
  --output /tmp/coding-pet-contact-sheet.png
```

Render row-by-row motion preview GIFs for QA:
```bash
PYTHONPATH=src python -m coding_pet.cli admin render-pet-animation-previews <pet-id> \
  --output-dir /tmp/coding-pet-previews
```
For official Codex-layout atlases, these GIFs use the same per-row frame
durations as the Codex pet contract rather than a single uniform timer.

Run the widget script demo shell:
```bash
PYTHONPATH=src python scripts/run_widget.py
```

Run the daemon runtime bootstrap:
```bash
PYTHONPATH=src python scripts/run_daemon.py
```

## Constrained-server smoke checks

These checks are valid on the current server even though Claude Code and OpenCode are not installed.

Doctor:
```bash
PYTHONPATH=src python -m coding_pet.cli admin doctor
```
Expected current-server signals include:
- `backend_claude_code=unavailable:not installed (missing 'claude')`
- `backend_opencode=unavailable:not installed (missing 'opencode')`
- `backend_codex=unavailable:not installed (missing 'codex')` when the optional local Codex adapter is not installed
- `tmux_binary=...` and `tmux_enabled=...`
- `transcript_db=~/.local/state/coding-pet/transcripts.sqlite` or the configured equivalent
- `gui_runtime=unavailable` or `gui_runtime=unavailable:no_display` in headless/minimal environments
- `theme=codex-default`
- `theme_missing_assets=none`
- `theme_registry_count=22`
- `theme_spritecollab_count=20`

Current-host acceptance:
```bash
PYTHONPATH=src python -m coding_pet.cli admin acceptance-check \
  --profile current \
  --json-out /tmp/coding-pet-acceptance-current.json
```
Expected on this constrained host:
- `overall=ok`
- unavailable GUI, tmux, notifications, or agent backends are reported as non-required when they are absent

Target-host acceptance:
```bash
PYTHONPATH=src python -m coding_pet.cli admin acceptance-check \
  --profile target \
  --json-out /tmp/coding-pet-acceptance-target.json
```
Expected on the RHEL 8.10 x86_64 company desktop:
- Linux host platform, Python 3.12, glibc >= 2.28, `/etc/redhat-release` containing RHEL 8.10, GUI runtime, tmux, Claude Code, OpenCode, writable paths, and the selected theme all report `ok=true`
- `overall=ok`

Evidence bundle:
```bash
PYTHONPATH=src python -m coding_pet.cli admin evidence-bundle \
  --profile target \
  --output-dir /tmp/coding-pet-target-evidence \
  --wheelhouse wheelhouse \
  --require-wheelhouse \
  --pet-source /path/to/downloaded-pets \
  --require-pet-packages
```
Expected on the target desktop:
- `summary.json`, `acceptance-target.json`, `environment.json`,
  `tmux-control.json`, `systemd-units.json`, `systemd-runtime.json`,
  `widget-smoke.json`, `hook-event-smoke.json`, `agent-hooks.json`,
  `wheelhouse.json`, and `pet-packages.json` have `schema_version=1` plus ISO
  `generated_at`; `summary.json` also has `ok=true` and the required artifact
  manifest
- `acceptance-target.json`, `environment.json`, `tmux-control.json`,
  `systemd-units.json`, `systemd-runtime.json`, `widget-smoke.json`,
  `hook-event-smoke.json`, `agent-hooks.json`, `wheelhouse.json`, and
  `pet-packages.json` are present
- `target-evidence-check` rejects the bundle unless the acceptance,
  environment, tmux-control, systemd-units, systemd-runtime, widget-smoke, and
  hook-event-smoke reports, plus the wheelhouse, pet-package, and agent-hook
  reports, are versioned/timestamped, the acceptance report has all required
  Linux/RHEL/Python/dependency/path/GUI/tmux/backend/theme checks, and any
  required acceptance check is passing, with no duplicate check names.
  `environment.json` must also confirm the same platform/backend/transcript
  facts, a Python 3.12 executable recorded as an absolute python path, an
  absolute `tmux_binary` path that points to `tmux`, an absolute `notify-send`
  path, and explicit Claude Code/OpenCode `binary_path` values matching their
  `available at ...` backend reasons. Its config/state/runtime/log/transcript
  paths must be absolute, the runtime path must stay under `/run/user`, and
  `transcript.db_path` must match `paths.transcript_db`.
  `systemd-runtime.json` must include an absolute `systemctl` path,
  real desktop session values for `XDG_RUNTIME_DIR`, `DBUS_SESSION_BUS_ADDRESS`,
  and `DISPLAY` or `WAYLAND_DISPLAY`, exact `systemctl --user` command evidence
  for the user manager, enabled target, and active units, plus zero return
  codes.
  The final target gate pins archived host evidence to RHEL 8.10 by requiring
  `platform.machine=x86_64`, `platform.release` to include `el8_10`, and
  `libc.version` to be exactly `2.28`.
  It also requires `tmux-control.json` to record the default raw probe text,
  matching observed text, a probe pane, and `detail=raw tmux input preserved`.
  `widget-smoke.json` must verify the same theme named by `environment.json`.
  On the target profile it also requires the hook event smoke to verify daemon
  delivery, transcript persistence, cleanup, the fixed smoke session id, and
  the checked evidence directory as the hook workspace.

Tmux transport self-check:
```bash
PYTHONPATH=src python -m coding_pet.cli admin tmux-control-check \
  --json-out /tmp/coding-pet-tmux-control-check.json
```
Expected on any host with tmux:
- `tmux_control_check=ok`
- `detail=raw tmux input preserved`
- the JSON report's `expected_text` and `observed_text` match the default raw
  probe containing Korean text, shell metacharacters, backslashes, and quotes

Daemon startup smoke check:
```bash
CODING_PET_DAEMON_ONESHOT=1 PYTHONPATH=src python -m coding_pet.cli daemon run
```
Expected:
- prints `coding-pet daemon ready ...`
- exits cleanly without requiring any local agent backend

Widget startup smoke check:
```bash
PYTHONPATH=src python -m coding_pet.cli widget run
```
Expected on this server:
- prints widget runtime/state information
- reports `live_mode=false` when no daemon socket exists
- prints `PySide6 GUI runtime is unavailable in this environment.` when the host lacks Qt runtime support or a graphical display

Monitor commands for Claude Code or OpenCode still appear in the CLI, but on this server they are expected to fail fast with an unavailable-backend diagnostic instead of attempting launch.

Discover already-running agent panes in tmux:
```bash
PYTHONPATH=src python -m coding_pet.cli daemon discover-tmux
```

Enable daemon-side tmux polling and timestamped transcripts:
```bash
CODING_PET_TMUX_ENABLED=1 PYTHONPATH=src python -m coding_pet.cli daemon run
```
The tmux path monitors existing panes discovered via `tmux list-panes`; it does not launch Claude Code/OpenCode or configure providers. Codex panes can be detected for local development, but Codex is not required for the company server. When a tracked tmux pane disappears, a failed session keeps its failed state for operator review; otherwise the daemon treats the session as completed, marks it inactive, and lets `CODING_PET_SHOW_COMPLETED_FOR_SEC` remove the pet after the short completion display window. When the daemon receives a tmux `send_reply` or `send_without_enter` action request, it passes text through with `tmux load-buffer`/`paste-buffer`, preserving Korean text, newlines, quotes, `$`, `;`, and backslashes. For tmux `approve` and `reject`, the daemon asks the matched agent adapter for its control text and delivers that through the same tmux buffer path; Claude Code/OpenCode currently map to `approve`/`reject`, while the optional Codex adapter maps to `y`/`n`.
If a target-server Claude Code/OpenCode build expects different approval text,
set `CODING_PET_CLAUDE_CODE_APPROVE_TEXT`,
`CODING_PET_CLAUDE_CODE_REJECT_TEXT`, `CODING_PET_OPENCODE_APPROVE_TEXT`, or
`CODING_PET_OPENCODE_REJECT_TEXT` in `~/.config/coding-pet/service.env` after
disposable-workspace validation.

When a connected widget opens a detail popup, it marks the local row read, requests the latest 100 transcript events from the daemon, sends a daemon-side `mark_read` action, and refreshes the popup when `transcript_snapshot` or `transcript_appended` messages arrive. Detail-popup send, send-without-enter, attach, and hide controls emit the same daemon `action_request` payloads used by the panel.
`hide_pet` is a local dismiss action for inactive sessions; live tmux/process
sources must stop or disappear first so they do not immediately recreate the pet.
For daemon-owned process sessions, service shutdown and explicit stop requests
best-effort terminate the launched process and persist the latest session as
inactive/read-only instead of leaving a stale live pet behind. If the process
does not exit within `CODING_PET_PROCESS_STOP_TIMEOUT_SEC` seconds, the daemon
uses a kill fallback.
Completed inactive snapshots whose display window already elapsed are skipped
on daemon restore, so service restarts do not show old completed pets again.

Capture and classify a specific pane once:
```bash
PYTHONPATH=src python -m coding_pet.cli daemon monitor-tmux \
  --pane %3 \
  --agent claude_code \
  --title auth-fix
```

Send one validation action to a selected tmux pane through the same daemon control
path used by the widget:
```bash
PYTHONPATH=src python -m coding_pet.cli daemon send-tmux-action \
  --pane %3 \
  --agent claude_code \
  --action send_reply \
  --reply-text "keep going"
```

For approval validation on a disposable session:
```bash
PYTHONPATH=src python -m coding_pet.cli daemon send-tmux-action \
  --pane %3 \
  --agent claude_code \
  --action approve
```

Capture before/after output and require an expected response pattern:
```bash
PYTHONPATH=src python -m coding_pet.cli daemon verify-tmux-action \
  --pane %3 \
  --agent claude_code \
  --action approve \
  --expect-regex "accepted|continuing|approved" \
  --json-out /tmp/coding-pet-verify-claude-approve.json
PYTHONPATH=src python -m coding_pet.cli admin backend-evidence-check \
  /tmp/coding-pet-verify-claude-approve.json \
  --agent claude_code \
  --action approve
```
Use this only on disposable validation panes; the JSON report includes bounded
before/after pane output tails as evidence. Common secret-like text is redacted
before writing the report, and `backend-evidence-check` rejects unredacted
secret-like tails, missing tails, missing or unredacted
`action_result.delivered_text`, missing `action_result.session_id`, mismatched
`action_result.action`, and `after_tail` values that do not match the configured
`expected_regex`. It also rejects reports with no pane id, reports whose
before/after hashes are not SHA-256 hex, and reports where `before_tail` already
matches `expected_regex`, because that does not prove the action changed the
backend state or what control/reply text was actually delivered.

For hook-based state updates, install local hook files into the approved agent
config:
```bash
PYTHONPATH=src python -m coding_pet.cli admin install-agent-hooks \
  --hooks-dir ~/.config/coding-pet/hooks
PYTHONPATH=src python -m coding_pet.cli admin agent-hooks-doctor \
  --hooks-dir ~/.config/coding-pet/hooks
```
Those hooks call `daemon hook-event` locally and map tool/session events to pet
states without requiring external network access.
The generated script reads common stdin JSON aliases such as `session_id`,
`sessionId`, `session.id`, `cwd`, `workspace.path`, `project_dir`, `title`, and
`summary`, then falls back to hook environment variables and the current working
directory.
`agent-hooks-doctor` also runs a local hook-script smoke with
`CODING_PET_BIN=true`, so it verifies the generated script can execute without
requiring a live daemon connection.
After the daemon service is running, `admin hook-event-smoke-check` sends a
real `PreToolUse` hook event through the Unix socket, verifies the resulting
`hook_event` transcript row, and hides the temporary hook-only pet.
When tmux monitoring is also enabled, hook events for the same agent/workspace
update the existing live tmux/process session instead of creating a duplicate
pet.
Use `admin write-agent-hooks --output-dir ...` instead when security review
requires copying the Claude settings snippet or OpenCode plugin manually.

For final target-server proof, collect all six disposable backend reports into
the evidence directory. If approve/reject/reply need separate disposable panes,
pass the action-specific pane overrides shown in `docs/operations/rhel8-setup.md`.
```bash
PYTHONPATH=src python -m coding_pet.cli admin collect-target-backend-evidence \
  --output-dir /tmp/coding-pet-target-evidence \
  --claude-pane %3 \
  --opencode-pane %4 \
  --reply-expect-regex "accepted|continuing|received" \
  --approve-expect-regex "accepted|continuing|approved" \
  --reject-expect-regex "rejected|cancelled|denied"
```
Then run the complete directory gate:
```bash
PYTHONPATH=src python -m coding_pet.cli admin target-evidence-check \
  /tmp/coding-pet-target-evidence \
  --json-out /tmp/coding-pet-target-evidence/target-check.json
```
This gate requires `systemd-units.json`, target `systemd-runtime.json`,
target `widget-smoke.json`, and target `hook-event-smoke.json` to pass.
It also rejects weak `summary.json`, `acceptance-target.json`,
`environment.json`, `tmux-control.json`, `systemd-units.json`,
`systemd-runtime.json`, `widget-smoke.json`, `hook-event-smoke.json`,
`wheelhouse.json`, `pet-packages.json`, and `agent-hooks.json` reports unless
they have schema version 1 and an ISO `generated_at`. `summary.json` must also
have an `output_dir` matching the checked evidence directory and an artifact
manifest for the base evidence files whose paths stay inside that directory and
resolve to the exact files the gate reads. `systemd-units.json` must include
exactly the three coding-pet unit files, no duplicate or unexpected unit names,
an absolute `systemd-analyze --user verify` command that matches those verified
unit paths, and return code 0.
`agent-hooks.json` must include absolute `hooks_dir`, `claude_settings`, and
`opencode_plugin` paths, and its check details must point back to those hook
installation paths. `wheelhouse.json`, `pet-packages.json`, and
`agent-hooks.json` must also be
present even when those reports mark their checks as skipped or not required.
Optional reports still have a minimum status schema: `ok` and `required` must
be booleans, `wheelhouse.json` and `pet-packages.json` must include boolean
`skipped`, and `agent-hooks.json` must include a `checks` list.
`environment.json` must also confirm Linux x86_64, Python 3.12, exact glibc
2.28, RHEL 8.10 via `el8_10`, GUI availability, selected theme name/detail,
absolute Python/tmux/notify-send paths, enabled transcripts, absolute
config/state/runtime/log/transcript paths, a positive transcript retention
limit, and Claude Code/OpenCode `binary_path` entries matching their
`available at ...` reasons.
The systemd runtime report must show
the systemd user manager reachable, `XDG_RUNTIME_DIR` plus either `DISPLAY` or
`WAYLAND_DISPLAY` present with recorded session values,
`target_enabled.unit=coding-pet.target`, `target_enabled.state=enabled`, exact
`systemctl --user status`, `is-enabled`, and `is-active` command records, and
the daemon, widget, and target units active.
The runtime unit list must contain exactly `coding-pet-daemon.service`,
`coding-pet-widget.service`, and `coding-pet.target`, with no duplicate or
unexpected unit entries.
The widget smoke report must show `gui_runtime=available`, `gui_validated=true`,
`theme_ok=true`, a non-empty selected theme, an absolute resolved sprite asset
for the selected theme, `presentation.mood=alert`, non-empty bubble text, and
`available_actions` containing both `approve` and `reject`. It also records
`action_surfaces.needs_permission` and `action_surfaces.needs_input` with
absolute resolved sprite assets, alert presentation moods, and non-empty bubble
text; the input surface must expose `send_reply` and non-empty reply shortcuts,
so the final gate proves the widget can expose both approval and reply workflows.
The hook-event smoke report must show `hook_result.ok=true`,
`hook_result.state=running`, `errors=[]`, `transcript.verified=true`, positive
transcript event count, a `PreToolUse` event for Claude Code or OpenCode with
session/workspace metadata, and `cleanup_result.ok=true` with `hide_pet`,
`outcome=local_updated`, `reason=hidden`, and a non-empty cleanup detail; its
socket path must point to `coding-pet.sock` under
`environment.json`'s runtime directory, `hook_result.session_id` must match the
`hook-{agent}-{session}` identity derived from the smoke event, transcript and
cleanup session ids must match `hook_result.session_id`, and the transcript DB
path must match `environment.json`. When `agent-hooks.json` marks hooks as required, it also
requires `agent_hooks.ok=true` and ok required checks for
`hook_script`, `hook_script_smoke`, `claude_settings`, and `opencode_plugin`.
When `wheelhouse.json` marks the offline package set as required, it also
requires `wheelhouse.ok=true`, refuses skipped wheelhouse evidence, requires
`install_smoke.ok=true` with `skipped=false` and `stage=import`, and checks that
every required distribution has a Python 3.12-compatible RHEL x86_64 wheel record
with SHA-256 and size metadata for transfer auditing, with no duplicate wheel
distribution, filename, or SHA-256 records.
When `pet-packages.json` marks copied pets as required, it also requires
`pet_packages.ok=true`, refuses skipped pet package evidence, and checks each
pet entry for theme id, manifest, source package, SHA-256, size, and file count
transfer metadata. Each accepted pet must also include Codex/Petdex validation
surface: `theme_format=codex_pet`, spritesheet path, atlas size, atlas grid,
frame size, positive per-row frame counts, mood row mappings for every widget
mood, and `atlas_cells.ok=true` with no cell errors. It also requires `total`,
`passed`, `failed`, and the `pets` list count to be internally consistent, and
rejects duplicate `theme_id`, `source_package`, or `transfer.sha256` records.
It also requires `backend-summary.json` plus all six disposable Claude
Code/OpenCode reply/approve/reject backend reports. The summary records the
pane, report path, expected regex, expected delivered text, expected outcome,
and verified action capability for exactly those six reports. The target gate
cross-checks it against each report's `expected_regex`,
`action_result.action`, `action_result.session_id`,
`action_result.delivered_text`, `action_result.outcome`, `capability`, and pane id;
approve/reject reports are also checked against the backend control messages in
`environment.json`. The action session id must equal the tmux pane session id
(`tmux-<pane>`), so archived backend evidence is tied to the selected Claude
Code/OpenCode pane. Each backend report's before/after hash pair must be unique
within the target bundle, so copied action evidence cannot satisfy multiple
checks. Backend summary report paths must also stay inside the checked evidence
directory and resolve to the exact backend report files the gate reads. The
top-level `summary.json` artifact manifest must also include
`backend-summary.json` and all six backend report paths, and failed backend
collection marks `backend_evidence` in `failed_required`.
`backend-summary.json` itself is versioned with `schema_version=1` and
`profile=target`, and each backend-summary report entry also carries
`schema_version=1`, `profile=target`, and `ok=true`.

Send an action through a running daemon socket, matching the widget IPC path:
```bash
PYTHONPATH=src python -m coding_pet.cli daemon send-action \
  --session-id tmux-%3 \
  --action send_reply \
  --reply-text "keep going"
```

Monitor a session from source checkout:
```bash
PYTHONPATH=src python -m coding_pet.cli daemon monitor \
  --agent claude_code \
  --cmd "claude code 'summarize the repository'" \
  --workspace /path/to/repo
```

Monitor an OpenCode session:
```bash
PYTHONPATH=src python -m coding_pet.cli daemon monitor \
  --agent opencode \
  --cmd "opencode run 'review the latest patch'" \
  --workspace /path/to/repo
```

## Runtime paths

By default coding-pet uses XDG-style paths:
- config: `~/.config/coding-pet`
- state: `~/.local/state/coding-pet`
- runtime: `${XDG_RUNTIME_DIR}/coding-pet` or `~/.local/state/coding-pet/runtime`
- socket: `coding-pet.sock` under the runtime directory, or a deterministic
  short fallback under the system temp directory when the Unix socket path would
  exceed platform limits
- snapshot file: `~/.local/state/coding-pet/state.json`
- transcript DB: `~/.local/state/coding-pet/transcripts.sqlite`
- logs: `~/.local/state/coding-pet/logs`

Runtime overrides consumed by the current code:
- `CODING_PET_CONFIG_DIR`
- `CODING_PET_STATE_DIR`
- `CODING_PET_RUNTIME_DIR` (final runtime directory; coding-pet does not append another `coding-pet` segment)
- `CODING_PET_STATE_FILE`
- `CODING_PET_LOG_DIR`
- `CODING_PET_LOG_LEVEL`
- `CODING_PET_CAPTURE_TRANSCRIPTS`
- `CODING_PET_TMUX_ENABLED`
- `CODING_PET_TMUX_CAPTURE_LINES`
- `CODING_PET_TMUX_POLL_INTERVAL_MS`
- `CODING_PET_TMUX_INCLUDE_SESSION_PATTERNS`
- `CODING_PET_TMUX_INCLUDE_COMMANDS`
- `CODING_PET_TMUX_EXCLUDE_SESSION_PATTERNS`
- `CODING_PET_TRANSCRIPT_ENABLED`
- `CODING_PET_TRANSCRIPT_DB`
- `CODING_PET_TRANSCRIPT_REDACT_SECRETS`
- `CODING_PET_STALLED_AFTER_SEC`
- `CODING_PET_ASSETS_DIR`
- `CODING_PET_CODEX_PETS_DIR`
- `CODING_PET_CLAUDE_CODE_APPROVE_TEXT`, `CODING_PET_CLAUDE_CODE_REJECT_TEXT`
- `CODING_PET_OPENCODE_APPROVE_TEXT`, `CODING_PET_OPENCODE_REJECT_TEXT`
- `CODING_PET_THEME`

Smoke-test/dev toggle:
- `CODING_PET_DAEMON_ONESHOT` makes `daemon run` print readiness, serve one loop, and exit cleanly.

## Documentation

- Architecture: `docs/architecture/coding-pet.md`
- Current constrained-server status: `docs/architecture/current-server-hardening-plan.md`
- Future backend-capable track: `docs/architecture/future-agent-enabled-server-plan.md`
- Operations: `docs/operations/rhel8-setup.md`
- Offline/intranet install: `docs/operations/offline-rhel8-wheelhouse.md`
- Codex/Petdex pet package compatibility: `docs/operations/codex-pet-packages.md`
- LLM target execution runbook: `docs/operations/llm-target-execution-runbook.md`
- Company server handoff: `docs/operations/company-server-handoff.md`
- Airgap upload bundle builder: `scripts/build_airgap_transfer_bundle.py`
- Default asset policy: `assets/sprites/codex-default/README.md`, `assets/sprites/theme-registry.json`, and `assets/sprites/PMDCOLLAB_LICENSE.md`

## Current limitations

- `python -m coding_pet.cli daemon run` and `widget run` now exist, but the current host still lacks a real PySide6/Qt graphical session for manual GUI exercise
- live panel actions are routed through adapter-defined stdin/tmux control messages; the transport is covered by tests, but real Claude Code/OpenCode acceptance semantics still need validation on installed sessions
- full manual PySide6 GUI UX still needs target-host validation even though detail-popup action wiring, daemon tmux action transport, and headless request helpers are tested
- restored snapshot sessions are intentionally read-only until a live daemon snapshot replaces them
- `daemon monitor` for Claude Code and OpenCode is intentionally fail-fast on this server because those backends are not installed locally
- Codex support is optional for local development and should not be treated as a company-server prerequisite
- the GUI shell falls back gracefully when PySide6 runtime libraries are unavailable
- tmux transcript rows are bounded screen-diff events, not a perfect terminal
  recording; common secrets and configured company regex patterns are redacted
  before persistence, but disable or relocate the transcript DB for highly
  sensitive panes
- target-server GUI/backend behavior still needs validation on the actual company server
