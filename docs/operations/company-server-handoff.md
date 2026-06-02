# Company Server Handoff Plan

Last verified locally: 2026-06-02

## Goal

Bring `coding-pet` to a company Linux/RHEL server with the current repository already hardened as far as this constrained server can verify. This handoff separates:

- work completed and verifiable in this checkout now;
- target-server checks that require the company GUI/session/backend environment;
- company-specific choices that should be configured, not guessed, during bring-up.

For an LLM executor that must run the remaining target-server procedure step by
step, use `docs/operations/llm-target-execution-runbook.md` as the executable
runbook and keep this document as the broader handoff context.

## Local Baseline Already Covered

The current checkout is intended to be carried over as a source checkout first, not as a final fleet package.

Locally verified scope:

- Backend-less daemon and widget startup paths.
- Degraded behavior when Claude Code/OpenCode are not installed.
- Optional Codex adapter support for local development only; Codex is not a company-server prerequisite.
- Inactive hook/restored/completed sessions can be dismissed locally with
  `hide_pet`; live sessions keep their pet until the monitored source stops.
- Inactive completed sessions are automatically removed after
  `CODING_PET_SHOW_COMPLETED_FOR_SEC` seconds; live completed sessions remain
  visible until the monitored source stops or is explicitly dismissed.
- Restarted daemons do not resurrect inactive completed sessions whose
  retention window has already elapsed.
- State snapshots are written with atomic replace semantics, so a failed write
  should preserve the previous `state.json`.
- If an existing snapshot is unreadable or schema-invalid, it is moved beside
  the original as `state.json.invalid.*` and startup continues without restored
  sessions.
- When a tracked tmux pane disappears, failed sessions stay failed for review;
  other sessions become inactive completed sessions and follow the same
  retention cleanup.
- When the daemon stops a process it launched, it best-effort terminates that
  process, uses a kill fallback after `CODING_PET_PROCESS_STOP_TIMEOUT_SEC`,
  and persists the last session snapshot as inactive/read-only.
- Manual state overrides are local daemon corrections and do not require a live
  backend control channel.
- Action acknowledgements include normalized `outcome` values while preserving
  legacy `ok` compatibility for older widget/operator tooling.
- Systemd user unit syntax.
- Offline-safe Codex-style default PNG sprite theme under `assets/sprites/codex-default/`.
- Fallback classic text sprites under `assets/sprites/classic/`.
- 20 selectable PMD SpriteCollab sample character themes under `assets/sprites/pmd-*` with preserved CC BY-NC 4.0 attribution.
- Asset discovery via checked-in source assets, optional `CODING_PET_ASSETS_DIR`, or installed `share/coding-pet/assets`.
- Hook events are stored as local transcript rows for hook-only session history.
- Malformed IPC messages return structured errors instead of closing the daemon
  connection, which helps diagnose bad hook/widget payloads.
- `admin doctor` reporting config paths, GUI runtime availability, backend availability, and sprite theme health.
- Current WSL/Linux verification for this refactor: `465 passed`, ruff clean, mypy clean over 86 source files, compileall clean with Python 3.12.3.
- Evidence bundles include systemd user-unit syntax verification as
  `systemd-units.json`.
- Target evidence checks cross-check Claude Code/OpenCode approve/reject reports
  against the control messages recorded in `environment.json`.
- Target evidence checks reject current-profile runtime/optional evidence so WSL
  smoke reports cannot be mixed into final RHEL target bundles.
- Target backend evidence reports must include
  `action_result.outcome=accepted`; reports that only set legacy `ok=true` are
  rejected as too weak for final backend validation.
- `backend-summary.json` must also declare `expected_outcome=accepted` for each
  Claude Code/OpenCode action report and match the individual report outcome.
- `backend-summary.json` is versioned with `schema_version=1` and
  `profile=target`.
- Offline wheelhouses can be checked with `admin wheelhouse-check`, including
  `coding_pet` wheel shared-data inspection and a temporary `--no-index
  --find-links` install smoke that imports PySide6 and resolves installed
  theme/systemd shared data.
- Previous full local verification gate also had systemd units verified and wheel build/inspection passed.

Wheel/package artifact inspection confirmed these installed shared-data paths:

```text
share/coding-pet/assets/sprites/theme-manifest.json
share/coding-pet/assets/sprites/theme-registry.json
share/coding-pet/assets/sprites/codex-default/*.png
share/coding-pet/assets/sprites/classic/*.txt
share/coding-pet/assets/sprites/pmd-*/*.png
share/coding-pet/docs/operations/offline-rhel8-wheelhouse.md
share/coding-pet/docs/operations/codex-pet-packages.md
share/coding-pet/docs/operations/llm-target-execution-runbook.md
share/coding-pet/requirements.txt
share/coding-pet/requirements/constraints-rhel8.txt
share/coding-pet/requirements/rhel8-runtime.txt
share/coding-pet/systemd/coding-pet.service.env.example
share/coding-pet/systemd/coding-pet-daemon.service
share/coding-pet/systemd/coding-pet-widget.service
share/coding-pet/systemd/coding-pet.target
```

## Files to Bring to the Company Server

Copy or clone the whole repository checkout. Important paths:

```text
README.md
docs/operations/rhel8-setup.md
docs/operations/company-server-handoff.md
packaging/systemd/coding-pet-daemon.service
packaging/systemd/coding-pet-widget.service
packaging/systemd/coding-pet.target
packaging/systemd/coding-pet.service.env.example
requirements.txt
requirements/constraints-rhel8.txt
requirements/rhel8-runtime.txt
docs/operations/offline-rhel8-wheelhouse.md
docs/operations/codex-pet-packages.md
docs/operations/llm-target-execution-runbook.md
scripts/build_airgap_transfer_bundle.py
assets/sprites/theme-manifest.json
assets/sprites/theme-registry.json
assets/sprites/codex-default/*.png
assets/sprites/classic/*.txt
assets/sprites/pmd-*/*.png
```

## Target Server Prerequisites

Confirm these before enabling user services:

```bash
python3 --version
command -v python3
command -v systemctl
systemctl --user status >/dev/null
printf 'DISPLAY=%s\nWAYLAND_DISPLAY=%s\nXDG_RUNTIME_DIR=%s\n' "$DISPLAY" "$WAYLAND_DISPLAY" "$XDG_RUNTIME_DIR"
```

Expected:

- Python 3.12.
- A real user session, not only a non-interactive root shell.
- `XDG_RUNTIME_DIR` set to a writable per-user runtime directory.
- `DISPLAY` or `WAYLAND_DISPLAY` set when GUI widget validation is required.

If the server is SSH-only/headless, the daemon can still smoke-test, but the widget cannot be considered GUI-validated.

## Source Checkout Install

From the company server checkout:

```bash
cd /path/to/coding-pet
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[gui]'
```

On intranet-only hosts, do not let pip reach external indexes. Build or mirror the wheelhouse from `docs/operations/offline-rhel8-wheelhouse.md`, then install with:

```bash
python -m pip install --no-index --find-links wheelhouse -e '.[gui]'
```

If a built project wheel is present in `wheelhouse/`, validate the wheelhouse
before relying on it for intranet-only installs:

```bash
PYTHONPATH=src python -m coding_pet.cli admin wheelhouse-check wheelhouse \
  --json-out /tmp/coding-pet-wheelhouse.json
```

Keep the resulting JSON with the transfer record. It includes each wheel's
filename, normalized distribution name, SHA-256, and size in bytes, so the
copied intranet wheelhouse can be audited after transfer.

For final target evidence, prefer passing the same copied wheelhouse into
`admin evidence-bundle --wheelhouse wheelhouse --require-wheelhouse` so the
deployment archive contains `wheelhouse.json` beside the acceptance, tmux, hook,
and systemd reports.
If copied Codex/Petdex packages are part of the release gate, pass the staging
directory as `--pet-source /path/to/downloaded-pets --require-pet-packages` so
the archive also contains `pet-packages.json`.

Run baseline checks:

```bash
PYTHONPATH=src python -m pytest -q
PYTHONPATH=src python -m coding_pet.cli admin doctor
PYTHONPATH=src python -m coding_pet.cli admin acceptance-check \
  --profile current \
  --json-out /tmp/coding-pet-acceptance-current.json
PYTHONPATH=src python -m coding_pet.cli admin evidence-bundle \
  --profile current \
  --output-dir /tmp/coding-pet-current-evidence
PYTHONPATH=src python -m coding_pet.cli admin systemd-unit-check \
  --json-out /tmp/coding-pet-systemd-units.json
CODING_PET_DAEMON_ONESHOT=1 PYTHONPATH=src python -m coding_pet.cli daemon run
PYTHONPATH=src python -m coding_pet.cli widget run
```

Expected first-pass behavior depends on the target session:

- GUI-capable desktop session: `widget run` should open the pet window.
- Headless/minimal session: `widget run` should print `PySide6 GUI runtime is unavailable in this environment.` and exit cleanly.
- `acceptance-check --profile current` should print `overall=ok`; GUI and missing agent backends are optional in this constrained profile.
- Backends not installed: `admin doctor` should show unavailable backend lines and `daemon monitor` should fail fast instead of launching.
- Codex not installed: expected unless you are using the optional local development adapter.

## Systemd User Service Bring-Up

Create the per-user config directory and copy the service environment template:

```bash
mkdir -p ~/.config/coding-pet ~/.config/systemd/user
cp packaging/systemd/coding-pet.service.env.example ~/.config/coding-pet/service.env
```

Edit `~/.config/coding-pet/service.env` for the real checkout and venv paths:

```text
CODING_PET_REPO=/absolute/path/to/coding-pet
CODING_PET_PYTHON=/absolute/path/to/coding-pet/.venv/bin/python
```

Optional company-server path overrides can be added there if home directories or runtime directories are restricted:

```text
CODING_PET_CONFIG_DIR=/approved/config/path/coding-pet
CODING_PET_STATE_DIR=/approved/state/path/coding-pet
CODING_PET_RUNTIME_DIR=/approved/runtime/path/coding-pet  # final runtime directory
CODING_PET_LOG_DIR=/approved/log/path/coding-pet
CODING_PET_ASSETS_DIR=/absolute/path/to/coding-pet/assets/sprites
CODING_PET_SHOW_COMPLETED_FOR_SEC=20
CODING_PET_PROCESS_STOP_TIMEOUT_SEC=2
```

Install and verify user units:

```bash
cp packaging/systemd/coding-pet-daemon.service ~/.config/systemd/user/
cp packaging/systemd/coding-pet-widget.service ~/.config/systemd/user/
cp packaging/systemd/coding-pet.target ~/.config/systemd/user/
systemd-analyze --user verify ~/.config/systemd/user/coding-pet-daemon.service \
  ~/.config/systemd/user/coding-pet-widget.service \
  ~/.config/systemd/user/coding-pet.target
systemctl --user daemon-reload
```

If services are started from an existing graphical login, import GUI-related variables before starting:

```bash
systemctl --user import-environment DISPLAY WAYLAND_DISPLAY XAUTHORITY DBUS_SESSION_BUS_ADDRESS XDG_RUNTIME_DIR
```

Start services:

```bash
systemctl --user enable --now coding-pet.target
systemctl --user status coding-pet-daemon.service
systemctl --user status coding-pet-widget.service
journalctl --user -u coding-pet-daemon.service -u coding-pet-widget.service -n 100 --no-pager
```

## Company-Specific Adjustment Plan

These are the likely target-server adjustments. They should be planned and recorded during bring-up rather than guessed in this checkout.

### 1. GUI Runtime

Check:

```bash
PYTHONPATH=src python -m coding_pet.cli admin doctor
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
PYTHONPATH=src python -m coding_pet.cli widget run
```

If `gui_runtime=unavailable` or `gui_runtime=unavailable:no_display`, install or enable the server-approved Qt/PySide6 runtime libraries and make sure the user service receives `DISPLAY`/`WAYLAND_DISPLAY`. Do not change widget code until host GUI prerequisites are known.

The target acceptance profile is stricter than `doctor`: it fails unless the
host platform is Linux and Python 3.12, glibc >= 2.28, RHEL 8.10, PySide6 GUI availability, tmux, Claude Code,
OpenCode, writable runtime paths, and the selected pet theme all pass. The
final target evidence directory gate also requires the archived
`environment.json` to prove RHEL 8.10 x86_64 more tightly with
`platform.machine=x86_64`, `platform.release` including `el8_10`, and
`libc.version` exactly `2.28`.
The evidence bundle records that target acceptance result together with
structured environment/backend/theme data, the disposable tmux transport
self-check, systemd user-unit/runtime verification, widget smoke evidence,
hook-event smoke evidence, and required offline wheelhouse validation when
`--require-wheelhouse` is used, plus copied pet package validation when
`--require-pet-packages` is used.
The final `systemd-runtime.json` must prove a real desktop user session with
`XDG_RUNTIME_DIR`, `DBUS_SESSION_BUS_ADDRESS`, and either `DISPLAY` or
`WAYLAND_DISPLAY` present with recorded target-session values.

### 2. User Session and Systemd

Check:

```bash
systemctl --user status
loginctl show-user "$USER" -p Linger
```

If services must run without an active login, decide internally whether user lingering is approved:

```bash
loginctl enable-linger "$USER"
```

Only run that after company policy approval.

### 3. Notification Path

Check:

```bash
PYTHONPATH=src python -m coding_pet.cli admin doctor | grep notify_send
command -v notify-send
```

If unavailable, either install a libnotify-compatible package or accept structured logging as the notification fallback.

### 4. Backend CLIs

Check:

```bash
PYTHONPATH=src python -m coding_pet.cli admin doctor | grep '^backend_'
command -v claude || true
command -v opencode || true
```

If Claude Code/OpenCode are approved and installed, run controlled disposable-workspace validation before real workspaces:

```bash
mkdir -p /tmp/coding-pet-smoke-workspace
PYTHONPATH=src python -m coding_pet.cli daemon monitor \
  --agent claude_code \
  --cmd "claude code 'say ready and exit'" \
  --workspace /tmp/coding-pet-smoke-workspace
```

Before sending input to an agent pane, verify the raw tmux transport on the
target host itself:

```bash
PYTHONPATH=src python -m coding_pet.cli admin tmux-control-check \
  --json-out /tmp/coding-pet-tmux-control-check.json
```

This must report `tmux_control_check=ok` and should be kept with the target
acceptance evidence.

For already-running tmux sessions, validate the same action path the widget uses:

```bash
PYTHONPATH=src python -m coding_pet.cli daemon discover-tmux
PYTHONPATH=src python -m coding_pet.cli daemon send-tmux-action \
  --pane %3 \
  --agent claude_code \
  --action send_reply \
  --reply-text "keep going"
PYTHONPATH=src python -m coding_pet.cli daemon send-tmux-action \
  --pane %3 \
  --agent claude_code \
  --action approve
PYTHONPATH=src python -m coding_pet.cli daemon verify-tmux-action \
  --pane %3 \
  --agent claude_code \
  --action approve \
  --expect-regex "accepted|continuing|approved" \
  --json-out /tmp/coding-pet-verify-claude-approve.json
PYTHONPATH=src python -m coding_pet.cli admin backend-evidence-check \
  /tmp/coding-pet-verify-claude-approve.json \
  --agent claude_code \
  --action approve \
  --json-out /tmp/coding-pet-check-claude-approve.json
```

After the daemon service is running, validate the widget IPC action path without
opening the GUI:

```bash
PYTHONPATH=src python -m coding_pet.cli daemon send-action \
  --session-id tmux-%3 \
  --action send_reply \
  --reply-text "keep going"
```

Repeat for OpenCode if installed. The automated suite verifies that reply text and adapter-defined approve/reject control text are delivered through stdin/tmux without shell quoting. Still validate that the real installed Claude Code/OpenCode builds accept those control messages with harmless prompts before using live project tasks.
If the target CLI expects different approval/rejection text, set
`CODING_PET_CLAUDE_CODE_APPROVE_TEXT`, `CODING_PET_CLAUDE_CODE_REJECT_TEXT`,
`CODING_PET_OPENCODE_APPROVE_TEXT`, or `CODING_PET_OPENCODE_REJECT_TEXT` in
`~/.config/coding-pet/service.env`, then rerun `admin evidence-bundle` and the
disposable-workspace checks. The evidence bundle records the active control
messages under each backend entry in `environment.json`.
Keep `verify-tmux-action` JSON reports only from disposable validation panes;
they include bounded before/after pane output tails as evidence. Common
secret-like text and configured company regex patterns are redacted before
writing the report, and `backend-evidence-check` rejects missing tails,
unredacted secret-like tails,
missing pane ids, missing or unredacted `action_result.delivered_text`,
non-SHA before/after hashes, `after_tail` values that do not match
`expected_regex`, and `before_tail` values that already match `expected_regex`.
Pass each report through `admin backend-evidence-check` before treating it as
target-server proof.
For final target-server proof, collect the six disposable backend reports into
`/tmp/coding-pet-target-evidence`, then run the complete directory gate:

```bash
PYTHONPATH=src python -m coding_pet.cli admin collect-target-backend-evidence \
  --output-dir /tmp/coding-pet-target-evidence \
  --claude-pane %3 \
  --opencode-pane %4 \
  --reply-expect-regex "accepted|continuing|received" \
  --approve-expect-regex "accepted|continuing|approved" \
  --reject-expect-regex "rejected|cancelled|denied"
```

Use the action-specific pane options when reply, approve, and reject need
separate disposable panes.

```bash
PYTHONPATH=src python -m coding_pet.cli admin target-evidence-check \
  /tmp/coding-pet-target-evidence \
  --json-out /tmp/coding-pet-target-evidence/target-check.json
```
If Claude Code/OpenCode hooks are approved for the deployment, run
`admin evidence-bundle --require-agent-hooks ...` after `admin
install-agent-hooks`; the resulting `agent-hooks.json` becomes part of the same
target evidence directory and `target-evidence-check` requires it to be healthy.
After the daemon service is running, also keep live hook smoke evidence in the
same directory:

```bash
PYTHONPATH=src python -m coding_pet.cli admin hook-event-smoke-check \
  --json-out /tmp/coding-pet-target-evidence/hook-event-smoke.json
```

That check sends a harmless hook event through the Unix socket, verifies the
SQLite `hook_event` transcript row, and hides the temporary hook-only pet.
If the offline wheelhouse is a release gate, keep `--wheelhouse wheelhouse
--require-wheelhouse` on that same bundle command; `target-evidence-check` then
requires `wheelhouse.ok=true` and a non-skipped `install_smoke` report that
reached `stage=import`.
If copied Petdex/CodexPets packages are a release gate, keep
`--pet-source /path/to/downloaded-pets --require-pet-packages` on the same
bundle command; `target-evidence-check` then requires `pet_packages.ok=true`
and consistent `total`, `passed`, `failed`, and `pets` counts, with no
duplicate `theme_id`, `source_package`, or `transfer.sha256` records.
On an internet-connected staging workstation, `admin download-petdex <slug>
--output-dir /tmp/downloaded-pets` can create a ZIP plus `<slug>.petdex.json`
metadata with source URLs, ZIP SHA-256, byte size, and validation details. Copy
those files into the intranet and validate them on the target. The final
`pet-packages.json` records the sidecar as `petdex_metadata` and checks that the
sidecar's archive hash still matches the copied ZIP transfer hash; do not make
the target desktop runtime depend on external Petdex access.

### 5. Internal Backend or Proxy Rules

If the company server must use an internal backend rather than local CLIs, do not hardcode it in the widget. Add it as a daemon adapter using the same backend registry/action-router boundary. The future-server plan remains the source for that work:

```text
docs/architecture/future-agent-enabled-server-plan.md
```

### 6. Asset Policy

Default assets are original `codex-default` PNGs generated for this repo by `scripts/generate_codex_default_sprites.py`; they are not copied OpenAI, Petdex, or codex-pets.net art. The removed legacy `company-pet` sprite directory must not be used in target evidence. The `pmd-*` directories are separately registered PMD SpriteCollab sample character themes licensed CC BY-NC 4.0 with per-character `credits.txt`; they are for non-commercial selectable-character testing, not company-owned production art. Codex/Petdex-style `pet.json` plus `spritesheet.webp` or `spritesheet.png` packages can be copied in separately and validated with `admin validate-pet` or installed with `admin import-pet`. Validation checks PNG/WebP dimensions, alpha support, used-cell occupancy, transparent unused cells, and opaque-background mistakes against the manifest layout before the package is accepted. Current Petdex packages that omit explicit state metadata are accepted when their 1728x1664 atlas matches the 9x8 Petdex layout. If a copied pet manifest supplies explicit layout values such as `columns`, `rows`, or `frame.width`, those values must be positive integers. If the company requires brand art, replace only the files under a new complete theme directory or import an approved pet package deliberately; keep the selected theme complete.

Required moods:

```text
idle
typing
celebrate
alert
thinking
sleepy
sad
```

After any asset change:

```bash
PYTHONPATH=src python -m pytest tests/test_theme_assets.py -q
PYTHONPATH=src python -m coding_pet.cli admin build-pet-qa /path/to/downloaded-pet --output-dir /tmp/coding-pet-qa
PYTHONPATH=src python -m coding_pet.cli admin validate-pet-batch /path/to/downloaded-pets \
  --json-out /tmp/coding-pet-pet-batch.json
PYTHONPATH=src python -m coding_pet.cli admin import-pet-batch /path/to/downloaded-pets \
  --pets-root ~/.codex/pets \
  --json-out /tmp/coding-pet-pet-import-batch.json
PYTHONPATH=src python -m coding_pet.cli admin validate-pet /path/to/downloaded-pet \
  --json-out /tmp/coding-pet-validation.json
PYTHONPATH=src python -m coding_pet.cli admin set-pet <pet-id>
PYTHONPATH=src python -m coding_pet.cli admin inspect-pet <pet-id>
PYTHONPATH=src python -m coding_pet.cli admin render-pet-contact-sheet <pet-id> --output /tmp/coding-pet-contact-sheet.png
PYTHONPATH=src python -m coding_pet.cli admin render-pet-animation-previews <pet-id> --output-dir /tmp/coding-pet-previews
PYTHONPATH=src python -m coding_pet.cli admin render-pet-frame <pet-id> --mood alert --output /tmp/coding-pet-preview.png
PYTHONPATH=src python -m coding_pet.cli admin doctor
```

## Target-Server Exit Criteria

The company-server bring-up is complete when:

- `PYTHONPATH=src python -m pytest -q` passes on the target server.
- `admin doctor` reports correct config/state/runtime/log paths.
- `admin acceptance-check --profile target` reports `overall=ok`.
- `admin evidence-bundle --profile target --output-dir ...` writes
  `summary.json`, `acceptance-target.json`, `environment.json`,
  `tmux-control.json`, `systemd-units.json`, `systemd-runtime.json`,
  `widget-smoke.json`, `hook-event-smoke.json`, `agent-hooks.json`,
  `wheelhouse.json`, and `pet-packages.json` with `schema_version=1` and ISO
  `generated_at`; `summary.json` also has `ok=true` and the required artifact
  manifest. The latter three files must be present even when they record skipped
  or non-required checks.
  Those optional reports still need typed status fields: boolean `ok` and
  `required`; boolean `skipped` for wheelhouse and copied-pet reports; and a
  `checks` list for agent-hook reports.
  Required agent-hook evidence includes ok required checks for `hook_script`,
  `hook_script_smoke`, `claude_settings`, and `opencode_plugin`, each with a
  detail string.
  Required wheelhouse evidence includes a wheel record for each required
  distribution, with per-wheel SHA-256 and size metadata, no duplicate wheel
  distribution, filename, or SHA-256 records, plus
  `install_smoke.ok=true`, `install_smoke.skipped=false`, and
  `install_smoke.stage=import`.
  Required copied-pet evidence includes source package, manifest, theme id,
  SHA-256, size, and file count metadata for each accepted pet, plus consistent
  `total`, `passed`, `failed`, and `pets` counts. Each accepted pet must also
  include the Codex/Petdex validation surface: `theme_format=codex_pet`,
  spritesheet, atlas size/grid, frame size, positive frame counts, mood row
  mappings for every widget mood, and `atlas_cells.ok=true` with no cell errors.
- `admin systemd-unit-check --json-out ...` reports `systemd_units=ok`.
- `admin systemd-runtime-check --json-out ...` reports `systemd_runtime=ok`
  after `coding-pet.target` is enabled and started from a graphical user
  session with `XDG_RUNTIME_DIR` plus `DISPLAY` or `WAYLAND_DISPLAY`. The final
  target evidence gate checks the recorded session values, the `/run/user`
  DBus address, exact `systemctl --user` command records,
  `target_enabled.unit=coding-pet.target`, `target_enabled.state=enabled`, and
  exactly one active runtime entry each for `coding-pet-daemon.service`,
  `coding-pet-widget.service`, and `coding-pet.target`.
- `admin widget-smoke-check --required --json-out ...` reports
  `widget_smoke=ok` in the real graphical desktop session with `theme_ok=true`
  and an absolute resolved sprite asset. The final gate also checks that the smoke uses
  the same theme named by `environment.json`, renders the alert mood, exposes
  approve/reject actions, and records absolute resolved sprite assets, alert
  presentation moods, and non-empty bubble text for
  `action_surfaces.needs_permission` and `action_surfaces.needs_input`; the input
  surface must expose `send_reply` plus non-empty reply shortcuts.
- `admin hook-event-smoke-check --json-out ...` reports
  `hook_event_smoke=ok` with a `PreToolUse` hook event,
  `hook_result.state=running`, empty `errors`, `transcript.verified=true`,
  positive transcript event count, `hide_pet` cleanup with `outcome=local_updated`,
  `reason=hidden`, and non-empty cleanup detail,
  fixed smoke session id, the checked evidence directory as workspace, socket path pointing to
  `coding-pet.sock` under the runtime directory from `environment.json`,
  hook result session id matching the `hook-{agent}-{session}` identity derived
  from the smoke event, transcript DB path matching `environment.json`, and
  transcript/cleanup session ids matching `hook_result.session_id`.
- `admin tmux-control-check --json-out ...` reports `tmux_control_check=ok`
  with the default raw probe text preserved in `observed_text`.
- `admin agent-hooks-doctor --json-out ...` reports hook installation paths
  whose check details match `hooks_dir`, Claude settings, and OpenCode plugin
  targets.
- `daemon verify-tmux-action --expect-regex ... --json-out ...` proves
  approve/reject/reply behavior on disposable Claude Code/OpenCode panes and
  redacts common secret-like text from captured evidence tails.
- `admin backend-evidence-check <verify-report.json> --agent ... --action ...`
  accepts each disposable backend behavior report and rejects missing,
  unredacted, regex-mismatched, or already-matched-before evidence tails, plus
  missing pane ids, non-SHA before/after hashes, and missing or unredacted
  `action_result.delivered_text`. It also requires the daemon-returned
  `action_result.action` to match the checked action and
  `action_result.session_id` to match the checked tmux pane as `tmux-<pane>`,
  with a unique before/after hash pair for each target backend report.
- `admin collect-target-backend-evidence --output-dir ...` writes the six
  backend reports and `backend-summary.json` entries with schema version 1,
  `profile=target`, `ok=true`, plus
  pane, report path, `expected_regex`, `expected_delivered_text`,
  `expected_outcome`, and `capability` for every reply/approve/reject report.
  The target gate compares those pane ids, expected regexes, delivered text,
  expected outcomes, and capability payloads with the actual backend report
  bodies.
- `admin target-evidence-check /tmp/coding-pet-target-evidence` accepts the
  complete RHEL/tmux/hook/wheelhouse/pet-package/backend evidence directory.
  This includes versioned `summary.json`, `acceptance-target.json`,
  `environment.json`, `tmux-control.json`, `systemd-units.json`,
  `systemd-runtime.json`, `widget-smoke.json`, `hook-event-smoke.json`,
  `agent-hooks.json`, `wheelhouse.json`, and `pet-packages.json` identity
  metadata, the `summary.json` artifact manifest, required acceptance checks
  including dependency/path readiness, any extra required checks, and duplicate
  check-name rejection, structured environment details including selected theme
  name/detail, a Python 3.12 executable recorded as an absolute python path, an
  absolute `tmux_binary` path that points to `tmux`, an absolute `notify-send`
  path, a positive transcript retention limit, plus explicit Claude
  Code/OpenCode `binary_path` values matching their `available at ...` backend
  reasons,
  absolute config/state/runtime/log/transcript paths with runtime under
  `/run/user`, self-contained summary and backend-summary paths that resolve to
  the exact files inside the checked evidence directory,
  target `systemd-units.json` with exactly the three coding-pet unit paths, no
  duplicate or unexpected unit names, absolute `systemd-analyze --user verify`
  command matching those verified unit paths, and return code 0,
  target `systemd-runtime.json` with reachable user manager, desktop session
  environment values under `/run/user`, absolute `systemctl` path, exact
  `systemctl --user status`, `is-enabled`, and `is-active` command records,
  zero return codes, and active user services,
  target `widget-smoke.json` with `gui_validated=true`, `theme_ok=true`, a
  selected theme, alert presentation, bubble text, and approve/reject action
  surface,
  target `hook-event-smoke.json` with `PreToolUse`, transcript count,
  `transcript.verified=true`, and `hide_pet` cleanup with hidden reason/detail,
  `backend-summary.json`, each disposable Claude Code/OpenCode
  reply/approve/reject report, exact six-report backend summary manifest, and
  delivered-text cross-checks between the summary, each report, and
  approve/reject control messages. The backend summary also records the
  verified tmux-buffer action capability for each reply/approve/reject action,
  including `requires_text` and semantics, and each backend report must carry
  the same capability payload. Each backend report must also carry
  `schema_version=1`, `profile=target`, the daemon-returned
  `action_result.action` for the requested action, and a
  non-empty `action_result.session_id`. The top-level `summary.json` artifact
  manifest must also list `backend-summary.json` and all six backend report
  paths, and failed backend collection marks `backend_evidence` in
  `failed_required`. Skipped/non-required wheelhouse,
  copied-pet, or agent-hook evidence must still be represented by typed,
  versioned JSON reports.
- `admin install-agent-hooks --hooks-dir ...` installs the local hook script,
  merges Claude Code settings, and writes the OpenCode plugin for offline
  hook-driven state updates when those agent integrations are approved.
  The generated script reads common stdin JSON aliases for session/workspace
  identity before falling back to hook and agent environment variables.
  Hook events for the same agent/workspace update existing live tmux/process
  pets rather than creating duplicate hook-only pets.
- `admin agent-hooks-doctor --hooks-dir ...` reports `agent_hooks=ok` against
  the approved Claude Code settings and OpenCode plugin paths, including a
  local hook-script smoke that does not require a live daemon.
- `admin doctor` reports `theme=codex-default` or the approved company theme with `theme_missing_assets=none`.
- `admin inspect-pet <pet-id>` reports the expected sprite assets or Codex atlas frame plan.
- `admin build-pet-qa /path/to/downloaded-pet --output-dir ...` writes `validation.json`, `contact-sheet.png`, `animation-previews/*.gif`, and `run-summary.json` for copied Codex/Petdex packages.
- `admin validate-pet-batch /path/to/downloaded-pets --json-out ...` accepts the copied staging set before intranet transfer.
- `admin import-pet-batch /path/to/downloaded-pets --pets-root ... --json-out ...` installs approved packages under `<pets-root>/<pet-id>/`.
- `admin render-pet-contact-sheet <pet-id> --output ...` writes a contact sheet for Codex/Petdex packages.
- `admin render-pet-animation-previews <pet-id> --output-dir ...` writes one GIF per atlas row.
- `admin render-pet-frame <pet-id> --mood alert --output ...` writes a non-empty PNG preview on hosts with PySide6 available.
- `daemon run` oneshot prints `coding-pet daemon ready ...`.
- `widget run` is either GUI-validated in a real graphical session or explicitly recorded as headless-only.
- systemd user services start and logs show no crash loop.
- backend availability matches the company's intended deployment mode.
- any real backend action semantics are validated in disposable workspaces before production workspaces.

## What Not to Claim Yet

Do not claim these until the target server proves them:

- real PySide6 GUI behavior on the company desktop session;
- real Claude Code/OpenCode control semantics;
- internal backend compatibility;
- long-running multi-session stability under actual team workflows;
- final company asset/brand approval.
