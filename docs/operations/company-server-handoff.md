# Company Server Handoff Plan

Last verified locally: 2026-05-20

## Goal

Bring `coding-pet` to a company Linux/RHEL server with the current repository already hardened as far as this constrained server can verify. This handoff separates:

- work completed and verifiable in this checkout now;
- target-server checks that require the company GUI/session/backend environment;
- company-specific choices that should be configured, not guessed, during bring-up.

## Local Baseline Already Covered

The current checkout is intended to be carried over as a source checkout first, not as a final fleet package.

Locally verified scope:

- Backend-less daemon and widget startup paths.
- Degraded behavior when Claude Code/OpenCode are not installed.
- Systemd user unit syntax.
- Company-safe default PNG sprite theme under `assets/sprites/company-pet/`.
- Fallback classic text sprites under `assets/sprites/classic/`.
- 20 selectable PMD SpriteCollab sample character themes under `assets/sprites/pmd-*` with preserved CC BY-NC 4.0 attribution.
- Asset discovery via checked-in source assets, optional `CODING_PET_ASSETS_DIR`, or installed `share/coding-pet/assets`.
- `admin doctor` reporting config paths, GUI runtime availability, backend availability, and sprite theme health.
- Full local verification gate: `154 passed`, ruff clean, mypy clean over 80 source files, compileall clean, systemd units verified, wheel build/inspection passed.

Wheel/package artifact inspection confirmed these installed shared-data paths:

```text
share/coding-pet/assets/sprites/theme-manifest.json
share/coding-pet/assets/sprites/theme-registry.json
share/coding-pet/assets/sprites/company-pet/*.png
share/coding-pet/assets/sprites/classic/*.txt
share/coding-pet/assets/sprites/pmd-*/*.png
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
assets/sprites/theme-manifest.json
assets/sprites/theme-registry.json
assets/sprites/company-pet/*.png
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

- Python 3.11 or newer.
- A real user session, not only a non-interactive root shell.
- `XDG_RUNTIME_DIR` set to a writable per-user runtime directory.
- `DISPLAY` or `WAYLAND_DISPLAY` set when GUI widget validation is required.

If the server is SSH-only/headless, the daemon can still smoke-test, but the widget cannot be considered GUI-validated.

## Source Checkout Install

From the company server checkout:

```bash
cd /path/to/coding-pet
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
```

Run baseline checks:

```bash
PYTHONPATH=src python -m pytest -q
PYTHONPATH=src python -m coding_pet.cli admin doctor
CODING_PET_DAEMON_ONESHOT=1 PYTHONPATH=src python -m coding_pet.cli daemon run
PYTHONPATH=src python -m coding_pet.cli widget run
```

Expected first-pass behavior depends on the target session:

- GUI-capable desktop session: `widget run` should open the pet window.
- Headless/minimal session: `widget run` should print `PySide6 GUI runtime is unavailable in this environment.` and exit cleanly.
- Backends not installed: `admin doctor` should show unavailable backend lines and `daemon monitor` should fail fast instead of launching.

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
```

Install and verify user units:

```bash
cp packaging/systemd/coding-pet-daemon.service ~/.config/systemd/user/
cp packaging/systemd/coding-pet-widget.service ~/.config/systemd/user/
cp packaging/systemd/coding-pet.target ~/.config/systemd/user/
systemd-analyze verify ~/.config/systemd/user/coding-pet-daemon.service \
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
PYTHONPATH=src python -m coding_pet.cli widget run
```

If `gui_runtime=unavailable` or `gui_runtime=unavailable:no_display`, install or enable the server-approved Qt/PySide6 runtime libraries and make sure the user service receives `DISPLAY`/`WAYLAND_DISPLAY`. Do not change widget code until host GUI prerequisites are known.

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

Repeat for OpenCode if installed. Validate reply/approve/reject semantics with harmless prompts before using live project tasks.

### 5. Internal Backend or Proxy Rules

If the company server must use an internal backend rather than local CLIs, do not hardcode it in the widget. Add it as a daemon adapter using the same backend registry/action-router boundary. The future-server plan remains the source for that work:

```text
docs/architecture/future-agent-enabled-server-plan.md
```

### 6. Asset Policy

Default assets are original `company-pet` PNGs generated for this repo and documented as internal pilot/demo art. The `pmd-*` directories are separately registered PMD SpriteCollab sample character themes licensed CC BY-NC 4.0 with per-character `credits.txt`; they are for non-commercial selectable-character testing, not company-owned production art. If the company requires brand art, replace only the files under a new complete theme directory and update the theme manifest/registry deliberately; keep all seven production moods complete.

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
PYTHONPATH=src python -m coding_pet.cli admin doctor
```

## Target-Server Exit Criteria

The company-server bring-up is complete when:

- `PYTHONPATH=src python -m pytest -q` passes on the target server.
- `admin doctor` reports correct config/state/runtime/log paths.
- `admin doctor` reports `theme=company-pet` or the approved company theme with `theme_missing_assets=none`.
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
