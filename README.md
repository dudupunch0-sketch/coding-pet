# coding-pet

Last verified locally: 2026-05-20

coding-pet is a production-quality desktop companion for monitoring multiple AI coding agent sessions on Linux systems such as Red Hat Enterprise Linux 8.10.

## Current direction

- Python application with a long-running daemon and GUI widget layer
- One pet per monitored session
- Shared control panel for all sessions
- Claude Code CLI and OpenCode CLI monitoring targets
- Screen-edge stack layout for multiple pets

## Current implementation status

Implemented today:
- typed session and event models
- concurrent daemon monitor manager
- Claude Code and OpenCode adapters
- registry-backed optional backend detection with fail-fast degraded behavior when local agent binaries are unavailable
- structured logging and XDG-aware configuration
- daemon/widget IPC over Unix domain sockets
- desktop notification backend with cooldowns
- widget shell, panel view model, and snapshot boot support
- JSON state persistence for restart resilience
- packaged systemd user-service unit files
- company-safe default PNG sprite theme, retained classic text fallback assets, and 20 selectable PMD SpriteCollab sample character themes
- `daemon run`, `widget run`, and `admin doctor` CLI runtime commands
- daemon-owned live action routing for `send_reply`, `approve`, and `reject`
- tmux pane discovery/capture/control modules for already-running Claude Code/OpenCode sessions
- SQLite transcript store with timestamped `in`, `out`, and `system` events
- IPC transcript snapshot requests plus appended-event streaming to connected widgets
- rule-based tmux snapshot classifier for `needs_input`, `needs_choice`, `needs_permission`, `stalled`, and failure states
- headless-safe detail popup/view-model/reply-box helpers for raw tmux action request construction
- normalized action failure reasons for unavailable, unsupported, missing, read-only, and no-live-control-channel paths
- explicit widget action feedback plus read-only restored-session handling
- detail-popup open flow that requests the latest transcript and sends a daemon `mark_read` action

Still in progress:
- validating agent-specific control semantics against real Claude Code/OpenCode behavior
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
systemd-analyze verify packaging/systemd/coding-pet-daemon.service
systemd-analyze verify packaging/systemd/coding-pet-widget.service
systemd-analyze verify packaging/systemd/coding-pet.target
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
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
PYTHONPATH=src python -m pytest -q
```

## Local verification gate

The latest local verification on the constrained development server passed with:

```text
pytest: 154 passed
ruff: All checks passed!
mypy: no issues found in 80 source files
compileall: passed
systemd-analyze verify: passed
pip wheel: passed
wheel contents: company-pet PNGs, classic text fallback, 20 PMD SpriteCollab sample character themes, theme registry, default manifest, and systemd shared-data files present
```

The built wheel installs shared data under `share/coding-pet/`, including:
- `share/coding-pet/assets/sprites/theme-manifest.json`
- `share/coding-pet/assets/sprites/company-pet/*.png`
- `share/coding-pet/assets/sprites/classic/*.txt`
- `share/coding-pet/assets/sprites/pmd-*/*.png`
- `share/coding-pet/assets/sprites/theme-registry.json`
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

Run the widget layer:
```bash
PYTHONPATH=src python -m coding_pet.cli widget run
```

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
- `tmux_binary=...` and `tmux_enabled=...`
- `transcript_db=~/.local/state/coding-pet/transcripts.sqlite` or the configured equivalent
- `gui_runtime=unavailable` or `gui_runtime=unavailable:no_display` in headless/minimal environments
- `theme=company-pet`
- `theme_missing_assets=none`
- `theme_registry_count=22`
- `theme_spritecollab_count=20`

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
The tmux path monitors existing panes discovered via `tmux list-panes`; it does not launch Claude Code/OpenCode or configure providers. When the daemon receives a tmux `send_reply` or `send_without_enter` action request, it passes text through with `tmux load-buffer`/`paste-buffer`, preserving Korean text, newlines, quotes, `$`, `;`, and backslashes.

When a connected widget opens a detail popup, it marks the local row read, requests the latest 100 transcript events from the daemon, sends a daemon-side `mark_read` action, and refreshes the popup when `transcript_snapshot` or `transcript_appended` messages arrive.

Capture and classify a specific pane once:
```bash
PYTHONPATH=src python -m coding_pet.cli daemon monitor-tmux \
  --pane %3 \
  --agent claude_code \
  --title auth-fix
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
- `CODING_PET_STALLED_AFTER_SEC`
- `CODING_PET_ASSETS_DIR`

Smoke-test/dev toggle:
- `CODING_PET_DAEMON_ONESHOT` makes `daemon run` print readiness, serve one loop, and exit cleanly.

## Documentation

- Architecture: `docs/architecture/coding-pet.md`
- Current constrained-server status: `docs/architecture/current-server-hardening-plan.md`
- Future backend-capable track: `docs/architecture/future-agent-enabled-server-plan.md`
- Operations: `docs/operations/rhel8-setup.md`
- Company server handoff: `docs/operations/company-server-handoff.md`
- Default asset policy: `assets/sprites/company-pet/README.md`, `assets/sprites/theme-registry.json`, and `assets/sprites/PMDCOLLAB_LICENSE.md`

## Current limitations

- `python -m coding_pet.cli daemon run` and `widget run` now exist, but the current host still lacks a real PySide6/Qt graphical session for manual GUI exercise
- live panel actions are routed through adapter-defined stdin control messages; per-agent approval/rejection semantics still need validation against real Claude Code/OpenCode sessions
- full PySide6 detail-popup button wiring and manual GUI UX still need target-host validation even though the daemon tmux action path and headless request helpers are tested
- restored snapshot sessions are intentionally read-only until a live daemon snapshot replaces them
- `daemon monitor` for Claude Code and OpenCode is intentionally fail-fast on this server because those backends are not installed locally
- the GUI shell falls back gracefully when PySide6 runtime libraries are unavailable
- tmux transcript rows are bounded screen-diff events, not a perfect terminal recording; disable or relocate the transcript DB if a workspace may print sensitive text
- target-server GUI/backend behavior still needs validation on the actual company server
