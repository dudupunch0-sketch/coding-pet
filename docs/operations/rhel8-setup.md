# coding-pet on RHEL 8.10

Last verified locally: 2026-06-02

## Target assumptions

- Red Hat Enterprise Linux 8.10 or a compatible Linux enterprise desktop/server install
- Python 3.12
- graphical session available for the widget and desktop notifications
- Unix domain sockets available under the user runtime directory

When preparing the company-server bundle from Windows, run local preflight checks
from WSL or another Linux shell. Git Bash/native Windows runs are useful for
editing and source-control chores, but they are not accepted as target evidence.

## Dependencies

Minimum development/runtime expectations:
- Python 3.12
- `pip`
- root runtime requirements entrypoint `requirements.txt`, which delegates to
  the RHEL runtime profile under `requirements/`
- PySide6 Python package constrained to the RHEL 8 compatible wheel range in
  `requirements/constraints-rhel8.txt`
- Pillow from the runtime wheelhouse for PNG/WebP Codex pet atlas validation
- working GUI runtime libraries for Qt
- `notify-send` or DBus/libnotify-compatible desktop notification path
- `tmux` when monitoring already-running Claude Code/OpenCode terminal panes
- a prebuilt wheelhouse or company package mirror when the host cannot reach external package indexes

Completed inactive pets remain visible for `CODING_PET_SHOW_COMPLETED_FOR_SEC`
seconds before the daemon removes them from the widget. The default is 20
seconds; live sessions are not removed by this retention timer.

Create a virtual environment and install the project:
```bash
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[gui]'
```

For intranet-only hosts, build and copy a wheelhouse first:

```text
docs/operations/offline-rhel8-wheelhouse.md
```

For Codex-style pet packages downloaded outside the intranet and copied in by
the user:

```text
docs/operations/codex-pet-packages.md
```

The pet commands accept either an extracted package directory, a `pet.json`, a
Petdex-style `petjson.json`, or a ZIP download containing exactly one pet
manifest. On an internet-connected staging workstation,
`admin download-petdex <slug> --output-dir ...` can create a transfer-ready ZIP
and `<slug>.petdex.json` metadata record before the files are copied into the
intranet. When that sidecar is copied beside the ZIP, target evidence records it
as `petdex_metadata` and checks that its archive hash still matches the ZIP
transfer hash. ZIPs are extracted into a temporary directory for validation and
rejected if they contain unsafe paths or symlinks.

## Important GUI note

In the current CI/container environment used for development, PySide6 imports can fail because system GUI libraries such as `libEGL.so.1` are unavailable. Even when imports succeed, Linux still needs `DISPLAY` or `WAYLAND_DISPLAY` for a real widget window. The widget code handles missing GUI support gracefully for tests and smoke checks, but a real desktop deployment needs the full Qt runtime stack and a graphical user session present.

If `scripts/run_widget.py` prints:
```text
PySide6 GUI runtime is unavailable in this environment.
```
then the Python package is installed but the host still lacks GUI runtime support or a graphical display for the user session.

## Verified commands

Top-level help:
```bash
PYTHONPATH=src python -m coding_pet.cli --help
```

Installed console script help:
```bash
coding-pet --help
```

Daemon help:
```bash
PYTHONPATH=src python -m coding_pet.cli daemon --help
```

Widget help:
```bash
PYTHONPATH=src python -m coding_pet.cli widget --help
```

Daemon monitor help:
```bash
PYTHONPATH=src python -m coding_pet.cli daemon monitor --help
```

Admin doctor help:
```bash
PYTHONPATH=src python -m coding_pet.cli admin doctor --help
```

Current-host acceptance diagnostics:
```bash
PYTHONPATH=src python -m coding_pet.cli admin acceptance-check \
  --profile current \
  --json-out /tmp/coding-pet-acceptance-current.json
```

Target RHEL acceptance diagnostics:
```bash
PYTHONPATH=src python -m coding_pet.cli admin acceptance-check \
  --profile target \
  --json-out /tmp/coding-pet-acceptance-target.json
```

Target evidence bundle:
```bash
PYTHONPATH=src python -m coding_pet.cli admin evidence-bundle \
  --profile target \
  --output-dir /tmp/coding-pet-target-evidence \
  --wheelhouse wheelhouse \
  --require-wheelhouse \
  --pet-source /path/to/downloaded-pets \
  --require-pet-packages
```

List available bundled and imported pet themes:
```bash
PYTHONPATH=src python -m coding_pet.cli admin list-pets
```

Persist the selected pet for systemd user services:
```bash
PYTHONPATH=src python -m coding_pet.cli admin set-pet <pet-id>
```

Inspect the selected pet's frame plan before GUI validation:
```bash
PYTHONPATH=src python -m coding_pet.cli admin inspect-pet <pet-id>
```

Render a single frame preview PNG when PySide6 is available:
```bash
PYTHONPATH=src python -m coding_pet.cli admin render-pet-frame <pet-id> \
  --mood alert \
  --output /tmp/coding-pet-preview.png
```

Render a full Codex/Petdex contact sheet for headless QA:
```bash
PYTHONPATH=src python -m coding_pet.cli admin render-pet-contact-sheet <pet-id> \
  --output /tmp/coding-pet-contact-sheet.png
```

Render row-by-row motion preview GIFs:
```bash
PYTHONPATH=src python -m coding_pet.cli admin render-pet-animation-previews <pet-id> \
  --output-dir /tmp/coding-pet-previews
```

Official Codex-layout atlases use the Codex row-specific frame durations in
the widget and in these GIF previews.

Build the full copied-pet QA bundle:
```bash
PYTHONPATH=src python -m coding_pet.cli admin build-pet-qa /path/to/downloaded-pet \
  --output-dir /tmp/coding-pet-qa
```

Validate and import a staging directory of copied Petdex/CodexPets packages:
```bash
PYTHONPATH=src python -m coding_pet.cli admin validate-pet-batch /path/to/downloaded-pets \
  --json-out /tmp/coding-pet-pet-batch.json
PYTHONPATH=src python -m coding_pet.cli admin import-pet-batch /path/to/downloaded-pets \
  --pets-root ~/.codex/pets \
  --json-out /tmp/coding-pet-pet-import-batch.json
```

Widget script demo:
```bash
PYTHONPATH=src python scripts/run_widget.py
```

Daemon runtime bootstrap:
```bash
PYTHONPATH=src python scripts/run_daemon.py
```

## Current-server smoke checks

These checks were verified on the current constrained server where Claude Code and OpenCode are not installed.

Doctor:
```bash
PYTHONPATH=src python -m coding_pet.cli admin doctor
```
Expected current-server signals include:
- `backend_claude_code=unavailable:not installed (missing 'claude')`
- `backend_opencode=unavailable:not installed (missing 'opencode')`
- `backend_codex=unavailable:not installed (missing 'codex')` when the optional development adapter is not installed
- `gui_runtime=unavailable` or `gui_runtime=unavailable:no_display` in headless/minimal environments
- `theme=codex-default`
- `theme_missing_assets=none`
- `theme_registry_count=22`
- `theme_spritecollab_count=20`
- `show_completed_for_sec=20` unless `CODING_PET_SHOW_COMPLETED_FOR_SEC` is set
- `process_stop_timeout_sec=2` unless `CODING_PET_PROCESS_STOP_TIMEOUT_SEC` is set

Acceptance check:
```bash
PYTHONPATH=src python -m coding_pet.cli admin acceptance-check \
  --profile current \
  --json-out /tmp/coding-pet-acceptance-current.json
```
Expected on this constrained host: `overall=ok`, with GUI and missing agent
backends treated as optional degraded paths.

Daemon startup smoke check:
```bash
CODING_PET_DAEMON_ONESHOT=1 PYTHONPATH=src python -m coding_pet.cli daemon run
```
Expected:
- prints `coding-pet daemon ready ...`
- exits cleanly without requiring agent backends

Widget startup smoke check:
```bash
PYTHONPATH=src python -m coding_pet.cli widget run
```
Expected on this server:
- prints widget runtime/state information
- reports `live_mode=false` when no daemon socket exists
- prints `PySide6 GUI runtime is unavailable in this environment.` when the host lacks Qt runtime support or a graphical display

Tmux pane discovery help:
```bash
PYTHONPATH=src python -m coding_pet.cli daemon discover-tmux --help
PYTHONPATH=src python -m coding_pet.cli daemon monitor-tmux --help
PYTHONPATH=src python -m coding_pet.cli daemon send-tmux-action --help
PYTHONPATH=src python -m coding_pet.cli daemon send-action --help
```

Discover existing tmux panes:
```bash
PYTHONPATH=src python -m coding_pet.cli daemon discover-tmux
```
Expected on a host with tmux sessions:
- matched Claude Code/OpenCode panes are shown with pane id, session name, command, cwd, and `matched`
- other panes are shown as ignored or omitted by include/exclude rules

Enable daemon-side tmux polling:
```bash
CODING_PET_TMUX_ENABLED=1 PYTHONPATH=src python -m coding_pet.cli daemon run
```
This watches already-running panes via `tmux list-panes` and `tmux capture-pane`; it does not launch agents or configure LLM providers. Claude Code and OpenCode are the target server use cases. Codex panes can be matched for local development, but Codex is not required on the company server. When the daemon receives a tmux `send_reply` or `send_without_enter` action request, text is delivered with `tmux load-buffer` and `tmux paste-buffer`, so Korean text, newlines, quotes, `$`, `;`, and backslashes are preserved as raw text. Tmux `approve` and `reject` actions use the matched agent adapter's control text and the same buffer delivery path.
Claude Code/OpenCode default approval/rejection text is `approve`/`reject`.
If the installed target-server builds require different text, set
`CODING_PET_CLAUDE_CODE_APPROVE_TEXT`, `CODING_PET_CLAUDE_CODE_REJECT_TEXT`,
`CODING_PET_OPENCODE_APPROVE_TEXT`, or `CODING_PET_OPENCODE_REJECT_TEXT` in
`~/.config/coding-pet/service.env` after disposable-workspace validation.

Optional hook-driven state updates can be used alongside or instead of tmux
polling when the approved agent build supports hooks/plugins:

```bash
PYTHONPATH=src python -m coding_pet.cli admin install-agent-hooks \
  --hooks-dir ~/.config/coding-pet/hooks
PYTHONPATH=src python -m coding_pet.cli admin agent-hooks-doctor \
  --hooks-dir ~/.config/coding-pet/hooks
```

The install command preserves existing Claude Code settings while merging the
Coding Pet hook entries, and writes a local OpenCode plugin under the approved
plugin path. The generated hook script calls `daemon hook-event` over the local
Unix socket and maps tool/session events to `running`, `idle`, `completed`, or
`failed` without external network access. Hook events are also written to the
SQLite transcript store so detail popups keep an event timeline in hook-only
mode.
The script reads common stdin JSON aliases such as `session_id`, `sessionId`,
`session.id`, `cwd`, `workspace.path`, `project_dir`, `title`, and `summary`,
then falls back to `CODING_PET_HOOK_*`, agent-specific environment variables,
and `PWD`.
Set `CODING_PET_BIN` in the agent environment when the `coding-pet` console
script is not on PATH. `agent-hooks-doctor` runs a local smoke with
`CODING_PET_BIN=true`, so a broken hook script fails before target evidence is
accepted.
When tmux polling is also enabled, matching hook events for the same
agent/workspace update the existing live tmux/process pet instead of creating a
second hook-only pet.
Use `admin write-agent-hooks --output-dir ...` instead when security review
requires manual config merging.
After the daemon service is running, validate the live hook path:

```bash
PYTHONPATH=src python -m coding_pet.cli admin hook-event-smoke-check \
  --json-out /tmp/coding-pet-hook-event-smoke.json
```

This sends a harmless `PreToolUse` event through the local Unix socket, verifies
the corresponding `hook_event` transcript row, and hides the temporary
hook-only pet.

Transcript events are stored in SQLite when transcripts are enabled:
```text
~/.local/state/coding-pet/transcripts.sqlite
```
Use `CODING_PET_TRANSCRIPT_DB` to move the DB or `CODING_PET_TRANSCRIPT_ENABLED=0`
to disable transcript capture. Common token/password/API key patterns are
redacted by default before persistence; keep
`CODING_PET_TRANSCRIPT_REDACT_SECRETS=1` for target evidence. Add
company-specific regexes with `CODING_PET_TRANSCRIPT_REDACTION_PATTERNS`, using
semicolons or newlines to separate multiple patterns.

Connected widgets keep detail popups fresh through the daemon IPC transcript path. Opening a detail popup sends `transcript_request` with `limit=100`, sends a daemon `mark_read` action, and applies later `transcript_snapshot`/`transcript_appended` messages to the popup model. Detail-popup send, send-without-enter, and attach controls emit daemon `action_request` payloads over the same IPC connection.

Validate raw tmux paste transport on the host before touching an agent pane:

```bash
PYTHONPATH=src python -m coding_pet.cli admin tmux-control-check \
  --json-out /tmp/coding-pet-tmux-control-check.json
```

This creates a disposable tmux session, pastes Korean text, newlines, quotes,
`$`, `;`, and backslashes through the same buffer path used by widget actions,
then verifies the captured bytes exactly.

To validate tmux action delivery on a disposable agent session before touching a
real workspace:

```bash
PYTHONPATH=src python -m coding_pet.cli daemon send-tmux-action \
  --pane %3 \
  --agent claude_code \
  --action send_reply \
  --reply-text "keep going"

PYTHONPATH=src python -m coding_pet.cli daemon send-tmux-action \
  --pane %3 \
  --agent claude_code \
  --action approve
```

Use `--no-enter` with `send_reply` when you want to paste a draft without
submitting it.

To capture before/after pane output and require an expected response pattern:

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

Run this only against disposable validation panes. The JSON report includes
bounded before/after pane output tails so it can prove action semantics. Common
secret-like text is redacted before writing those tails, and the backend
evidence checker also rejects reports that contain unredacted secret-like tails,
lack before/after tails, lack a pane id, lack SHA-256 before/after hashes, lack
a successful action result, lack a matched expected regex, have an `after_tail`
that does not match `expected_regex`, or have a `before_tail` that already
matches `expected_regex`. That last condition prevents an already-successful
pane from being counted as action proof.

To validate a running daemon socket without using the GUI widget:

```bash
PYTHONPATH=src python -m coding_pet.cli daemon send-action \
  --session-id tmux-%3 \
  --action send_reply \
  --reply-text "keep going"
```

This uses the same `action_request` IPC path as the widget. It also follows the
daemon's deterministic short socket fallback when the runtime directory path is
too long for a Unix domain socket.

On the actual RHEL 8.10 company desktop, use the target profile as the first
bring-up gate:

```bash
PYTHONPATH=src python -m coding_pet.cli admin acceptance-check \
  --profile target \
  --json-out /tmp/coding-pet-acceptance-target.json
PYTHONPATH=src python -m coding_pet.cli admin evidence-bundle \
  --profile target \
  --output-dir /tmp/coding-pet-target-evidence \
  --wheelhouse wheelhouse \
  --require-wheelhouse \
  --pet-source /path/to/downloaded-pets \
  --require-pet-packages
```

The target acceptance profile requires a Linux host platform, Python 3.12,
glibc >= 2.28, a RHEL 8.10 release file, PySide6 GUI availability, tmux,
Claude Code, OpenCode, writable runtime paths, and a complete selected pet
theme. The final `target-evidence-check` directory gate is stricter about the
archived environment report: `platform.machine` must be `x86_64`,
`platform.release` must include `el8_10`, and `libc.version` must be exactly
`2.28`.
The evidence bundle writes `summary.json`, `acceptance-target.json`,
`environment.json`, `tmux-control.json`, `systemd-units.json`,
`systemd-runtime.json`, `widget-smoke.json`, `hook-event-smoke.json`,
`agent-hooks.json`, `wheelhouse.json`, and `pet-packages.json` so those facts
can be archived with the deployment record. `summary.json`,
`acceptance-target.json`, `environment.json`, `tmux-control.json`,
`systemd-units.json`, `systemd-runtime.json`, `widget-smoke.json`, and
`hook-event-smoke.json`, `agent-hooks.json`, `wheelhouse.json`, and
`pet-packages.json` include `schema_version=1` and an ISO `generated_at`;
`summary.json` also includes a manifest of the base artifact files. The final
directory gate requires those base report files to exist even when wheelhouse,
copied-pet, or hook-installation checks are not required.
For final target evidence, `systemd-runtime.json` must also prove a real desktop
user session: `XDG_RUNTIME_DIR`, `DBUS_SESSION_BUS_ADDRESS`, and either
`DISPLAY` or `WAYLAND_DISPLAY` must be present with recorded target-session
values. It must also record an absolute `systemctl` path, exact command records
for `systemctl --user status`, `is-enabled`, and `is-active`, plus zero return
codes for the user manager, enabled target, and active coding-pet units.
With `--require-wheelhouse`, the bundle fails unless the copied offline package
set passes static RHEL 8.10 wheel checks and the temporary `pip install
--no-index --find-links wheelhouse 'coding-pet[gui]'` smoke test. The
`wheelhouse.json` report also records each wheel's filename, normalized
distribution name, SHA-256, and size in bytes for transfer auditing, and rejects
wheel tags that are incompatible with the RHEL x86_64 Python 3.12 target.
Required target evidence must include a wheel record for each required distribution. With
`--require-pet-packages`, it also fails unless the copied Codex/Petdex package
staging directory passes batch validation and records per-package transfer
metadata: source package, manifest, SHA-256, size, and file count. The report's
`total`, `passed`, `failed`, and accepted pet count must also agree.
If Claude Code/OpenCode hooks are approved as part of the deployment, add
`--require-agent-hooks` to the bundle command after running
`admin install-agent-hooks`; missing hooks will then fail the bundle gate.
For final target-server proof, also collect disposable backend verification
reports into that directory:

```bash
PYTHONPATH=src python -m coding_pet.cli admin collect-target-backend-evidence \
  --output-dir /tmp/coding-pet-target-evidence \
  --claude-pane %3 \
  --opencode-pane %4 \
  --reply-expect-regex "accepted|continuing|received" \
  --approve-expect-regex "accepted|continuing|approved" \
  --reject-expect-regex "rejected|cancelled|denied"
```

If one pane cannot safely exercise reply, approve, and reject in sequence, start
separate disposable panes and pass `--claude-reply-pane`, `--claude-approve-pane`,
`--claude-reject-pane`, `--opencode-reply-pane`, `--opencode-approve-pane`, and
`--opencode-reject-pane` as needed.

Then run the complete directory gate:

```bash
PYTHONPATH=src python -m coding_pet.cli admin target-evidence-check \
  /tmp/coding-pet-target-evidence \
  --json-out /tmp/coding-pet-target-evidence/target-check.json
```
The directory gate requires `systemd-units.json`, `systemd-runtime.json`,
`widget-smoke.json`, `hook-event-smoke.json`, `backend-summary.json`, and the
six disposable Claude Code/OpenCode reply/approve/reject backend reports to
pass. It also checks that
`summary.json`, `acceptance-target.json`, `environment.json`,
`tmux-control.json`, `systemd-units.json`, `systemd-runtime.json`,
`widget-smoke.json`, `hook-event-smoke.json`, `agent-hooks.json`,
`wheelhouse.json`, and `pet-packages.json` have schema version 1 plus ISO
`generated_at`, and `summary.json` has the expected base artifact manifest with
paths that stay inside the checked evidence directory and resolve to the exact
base evidence files; `tmux-control.json` contains the default raw probe text,
matching observed text, a probe pane, and `detail=raw tmux input preserved`;
`systemd-units.json` contains exactly the three coding-pet unit paths, no
duplicate or unexpected unit names, an absolute `systemd-analyze --user verify`
command that matches those verified unit paths, and return code 0;
`agent-hooks.json` contains absolute hook, Claude settings, and OpenCode plugin
paths whose check details match those installation targets;
`widget-smoke.json` verifies the same theme named by `environment.json`;
`hook-event-smoke.json` records the fixed smoke session id and uses the checked
evidence directory as the hook workspace;
`acceptance-target.json` contains all required
Linux/RHEL/Python/dependency/path/GUI/tmux/backend/theme checks, rejects any
failing required check or duplicate check name, and `environment.json`
confirms Linux x86_64, Python 3.12 with an absolute python executable path,
exact glibc 2.28, RHEL 8.10 via `el8_10` `platform.release`, GUI
availability, an absolute `tmux_binary` path that points to `tmux`, the selected
theme name/detail, an absolute `notify-send` path, enabled SQLite transcripts
with secret redaction and a positive retention limit, and available Claude
Code/OpenCode backends with explicit `binary_path` values matching their
`available at ...` reasons. The environment
paths for config, state, runtime, state file, logs, and transcript DB must be
absolute, the runtime path must be under `/run/user`, and `transcript.db_path`
must match `paths.transcript_db`.
The widget smoke report must show `gui_runtime=available`,
`gui_validated=true`, `theme_ok=true`, a non-empty selected theme,
`qt_widget_created=true`, an absolute resolved `sprite_asset`,
`presentation.mood=alert`, non-empty bubble text, and `available_actions`
containing both `approve` and `reject`. It must also include
absolute resolved sprite assets for `action_surfaces.needs_permission` and
`action_surfaces.needs_input`, and both surfaces must include alert presentation
mood plus non-empty bubble text; the input surface must include `send_reply` and
non-empty reply shortcuts so the same target evidence proves the reply workflow
is exposed.
The systemd runtime report must show `target_enabled.unit=coding-pet.target`,
`target_enabled.state=enabled`, and `coding-pet-daemon.service`,
`coding-pet-widget.service`, and `coding-pet.target` active in the user
manager, with exactly those three runtime unit entries and no duplicates or
unexpected units. It must also show the user
manager is reachable, `XDG_RUNTIME_DIR` is present, and either `DISPLAY` or
`WAYLAND_DISPLAY` is present with recorded `/run/user` session values for the
desktop widget service. It also verifies the recorded `systemctl --user`
commands for the manager, target enablement, and active units.
The hook-event smoke report must show `hook_result.ok=true`,
`hook_result.state=running`, empty `errors`, `transcript.verified=true`,
positive transcript event count, a `PreToolUse` event for Claude Code or
OpenCode with session/workspace metadata, and `cleanup_result.ok=true` with
`hide_pet`, `outcome=local_updated`, `reason=hidden`, and a non-empty cleanup
detail. Its socket path must point to `coding-pet.sock` under the runtime
directory recorded in `environment.json`.
The transcript and cleanup session ids must match `hook_result.session_id`,
`hook_result.session_id` must match the `hook-{agent}-{session}` identity
derived from the smoke event, and the transcript DB path must match
`environment.json`, so the final gate proves
the same daemon session was created, audited, and cleaned up.
For approve/reject backend reports, it also checks that `action_result.delivered_text`
matches the backend control message recorded in `environment.json`.
All backend reports must include non-empty, redaction-safe
`action_result.delivered_text`, matching `action_result.action`,
`action_result.outcome=accepted`, unique before/after hash pairs across the
bundle, and a non-empty `action_result.session_id`, so a report cannot pass with
only `action_result.ok=true`. The session id must match the checked tmux pane as
`tmux-<pane>`, tying evidence to the selected Claude Code/OpenCode pane. Each
backend report must also include the verified tmux-buffer action capability for
its requested action.
The target gate also compares every backend report's delivered text with the
`expected_delivered_text` and `expected_outcome` recorded by
`backend-summary.json`, including `send_reply` reports. The backend summary
must contain exactly those six schema-versioned `profile=target`, `ok=true`
reports, with non-empty pane ids, expected regexes, accepted expected outcomes,
verified tmux-buffer action capabilities, and report paths that point to the
expected backend report filenames inside the checked evidence directory.
Those paths must resolve to the exact backend report files the gate reads.
Each backend report's pane id and
expected regex must match the corresponding summary entry, and its outcome and
capability payload must match the backend summary entry.
The top-level `summary.json` artifact manifest must also include
`backend-summary.json` and all six backend report paths, and failed backend
collection must mark `backend_evidence` in `failed_required`.
`backend-summary.json` itself must be versioned with `schema_version=1` and
`profile=target`, and each backend report must also carry `schema_version=1`
and `profile=target`.
`wheelhouse.json`, `pet-packages.json`, and `agent-hooks.json` must be present
even when they record skipped or non-required checks.
Optional reports still need a minimum typed status shape: `ok` and `required`
must be booleans, all three must have schema version 1 plus ISO `generated_at`,
`wheelhouse.json` and `pet-packages.json` must include boolean `skipped`, and
`agent-hooks.json` must include a `checks` list.
When `agent-hooks.json` marks hooks as required, the gate also checks that
`agent_hooks.ok=true` and that `hook_script`, `hook_script_smoke`,
`claude_settings`, and `opencode_plugin` checks are present, required, ok, and
carry detail strings.
When `wheelhouse.json` marks the offline package set as required, the gate also
checks that `wheelhouse.ok=true` and that the wheelhouse evidence was not
skipped. It also requires `install_smoke.ok=true`, `install_smoke.skipped=false`,
and `install_smoke.stage=import`, then checks that each required distribution
has a wheel record carrying SHA-256, positive size metadata, and RHEL x86_64
Python 3.12-compatible tags, with no duplicate wheel distribution, filename, or
SHA-256 records.
When `pet-packages.json` marks copied pets as required, the gate also checks
that `pet_packages.ok=true`, that pet package evidence was not skipped, and
that every accepted copied pet has source package, manifest, theme id, SHA-256,
size, and file count metadata. Each accepted pet must also carry the
Codex/Petdex validation surface: `theme_format=codex_pet`, spritesheet path,
atlas size, atlas grid, frame size, positive per-row frame counts, mood row
mappings for every widget mood, and `atlas_cells.ok=true` with no cell errors.
It also rejects inconsistent `total`, `passed`, `failed`, and `pets` counts, as
well as duplicate `theme_id`, `source_package`, or `transfer.sha256` records.

## Monitoring two simultaneous agents

The following examples require a different server that actually has Claude Code and OpenCode installed. They are included here only as reference for a backend-capable environment, not as a smoke check for the current server.

Terminal 1:
```bash
PYTHONPATH=src python -m coding_pet.cli daemon monitor \
  --agent claude_code \
  --cmd "claude code 'summarize the repository'" \
  --workspace /repos/a
```

Terminal 2:
```bash
PYTHONPATH=src python -m coding_pet.cli daemon monitor \
  --agent opencode \
  --cmd "opencode run 'review the latest patch'" \
  --workspace /repos/b
```

On the current constrained server, `daemon monitor` is still useful as a fail-fast diagnostic: it should reject unavailable backends clearly rather than attempting launch.

## Files and paths

Systemd user-service unit files are shipped in this repository under:
- `packaging/systemd/coding-pet-daemon.service`
- `packaging/systemd/coding-pet-widget.service`
- `packaging/systemd/coding-pet.target`

Validate them with:
```bash
systemd-analyze --user verify \
  packaging/systemd/coding-pet-daemon.service \
  packaging/systemd/coding-pet-widget.service \
  packaging/systemd/coding-pet.target
```

Install for the current user:
```bash
mkdir -p ~/.config/coding-pet ~/.config/systemd/user
cp packaging/systemd/coding-pet.service.env.example ~/.config/coding-pet/service.env
$EDITOR ~/.config/coding-pet/service.env
cp packaging/systemd/coding-pet-daemon.service ~/.config/systemd/user/
cp packaging/systemd/coding-pet-widget.service ~/.config/systemd/user/
cp packaging/systemd/coding-pet.target ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now coding-pet.target
```

At minimum, set these values in `~/.config/coding-pet/service.env` for the target checkout:
```text
CODING_PET_REPO=/absolute/path/to/coding-pet
CODING_PET_PYTHON=/absolute/path/to/coding-pet/.venv/bin/python
```

If starting from a graphical login, import GUI/session variables before `enable --now`:
```bash
systemctl --user import-environment DISPLAY WAYLAND_DISPLAY XAUTHORITY DBUS_SESSION_BUS_ADDRESS XDG_RUNTIME_DIR
```

The widget unit is ordered after `graphical-session.target`, and both services use `Restart=on-failure`.

By default coding-pet uses:
- config dir: `~/.config/coding-pet`
- state dir: `~/.local/state/coding-pet`
- runtime dir: `${XDG_RUNTIME_DIR}/coding-pet`
- logs: `~/.local/state/coding-pet/logs`
- persisted snapshot: `~/.local/state/coding-pet/state.json`
- transcript DB: `~/.local/state/coding-pet/transcripts.sqlite`

Useful overrides:
```bash
export CODING_PET_CONFIG_DIR=/custom/config
export CODING_PET_STATE_DIR=/custom/state
export CODING_PET_RUNTIME_DIR=/custom/runtime/coding-pet  # final runtime dir
export CODING_PET_STATE_FILE=/custom/state/state.json
export CODING_PET_LOG_DIR=/custom/logs
export CODING_PET_ASSETS_DIR=/custom/assets/sprites
export CODING_PET_TMUX_ENABLED=1
export CODING_PET_TMUX_CAPTURE_LINES=200
export CODING_PET_TMUX_POLL_INTERVAL_MS=1000
export CODING_PET_TMUX_INCLUDE_SESSION_PATTERNS='claude-*,opencode-*,agent-*'
export CODING_PET_TMUX_INCLUDE_COMMANDS='claude,opencode'
export CODING_PET_TMUX_EXCLUDE_SESSION_PATTERNS=''
export CODING_PET_TRANSCRIPT_DB=/custom/state/transcripts.sqlite
export CODING_PET_TRANSCRIPT_ENABLED=1
export CODING_PET_TRANSCRIPT_REDACT_SECRETS=1
export CODING_PET_STALLED_AFTER_SEC=300
```

## Company server handoff

For target-server bring-up and expected company-specific decisions, use:

```text
docs/operations/company-server-handoff.md
```

## Troubleshooting

### Widget does not open
- verify a graphical session exists
- verify Qt runtime libraries are installed
- run `PYTHONPATH=src python scripts/run_widget.py`
- if you get the GUI runtime unavailable message, fix host GUI libraries first

### No desktop notifications
- ensure `notify-send` exists on the system path
- ensure the process is running inside the user desktop session with access to the GUI bus
- otherwise notifications currently fall back to structured logging

### Daemon snapshot not written
- verify the state directory is writable
- verify `CODING_PET_STATE_FILE` is not pointing to a protected path
- check `~/.local/state/coding-pet/state.json`

### Detail popup transcript is empty or stale
- verify `CODING_PET_TRANSCRIPT_ENABLED=1`
- verify `CODING_PET_TRANSCRIPT_REDACT_SECRETS=1`
- verify `CODING_PET_TRANSCRIPT_DB` points to a writable SQLite path
- verify the widget is connected to the live daemon socket, not only a restored snapshot
- run `PYTHONPATH=src python -m coding_pet.cli admin doctor` and check `transcript_db`, `transcript_enabled`, `runtime_socket`, and `runtime_socket_exists`

### CLI commands appear missing
If you are running from a source checkout, prefer:
```bash
PYTHONPATH=src python -m coding_pet.cli ...
```
This avoids importing an older editable install from a different checkout.

## Current limitations

- the action transport into live sessions writes adapter-defined control messages to monitored process stdin or tmux panes; `daemon send-tmux-action` can validate delivery on disposable panes, but the real Claude Code/OpenCode workflow semantics still need target-host validation
- the GUI shell still depends on a full PySide6/Qt runtime, which is unavailable in the current headless test environment
- full manual PySide6 detail-popup UX still needs target-host validation; send/attach action wiring, the daemon tmux action path, and headless request builders are covered by automated tests
- restored snapshot sessions are intentionally read-only until a live daemon connection replaces them with active sessions
- default `codex-default` assets are generated original repo art; optional `pmd-*` PMD SpriteCollab sample themes are CC BY-NC 4.0 and for non-commercial selectable-character testing only; replace them with approved company art or imported Codex/Petdex pet packages if the target deployment requires brand-specific assets
- transcript capture is a bounded tmux screen-diff log with default redaction
  for common token/password/API key patterns and configurable company regex
  patterns; perfect terminal replay is future work
- target-server systemd, GUI, notification, and backend behavior must be validated on the actual company server
