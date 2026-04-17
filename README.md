# coding-pet

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
- structured logging and XDG-aware configuration
- daemon/widget IPC over Unix domain sockets
- desktop notification backend with cooldowns
- widget shell, panel view model, and snapshot boot support
- JSON state persistence for restart resilience

Still in progress:
- full daemon service runtime
- full widget runtime command integration
- production sprite assets

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

For a source checkout, install/link them into the user systemd directory:
```bash
mkdir -p ~/.config/systemd/user
cp packaging/systemd/coding-pet-* ~/.config/systemd/user/
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

Run the widget demo shell:
```bash
PYTHONPATH=src python scripts/run_widget.py
```

Run the daemon placeholder bootstrap:
```bash
PYTHONPATH=src python scripts/run_daemon.py
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
- logs: `~/.local/state/coding-pet/logs`

Useful overrides:
- `CODING_PET_CONFIG_DIR`
- `CODING_PET_STATE_DIR`
- `CODING_PET_RUNTIME_DIR`
- `CODING_PET_STATE_FILE`
- `CODING_PET_LOG_DIR`
- `CODING_PET_LOG_LEVEL`
- `CODING_PET_CAPTURE_TRANSCRIPTS`

## Documentation

- Architecture: `docs/architecture/coding-pet.md`
- RHEL operations guide: `docs/operations/rhel8-setup.md`

## Current limitations

- `python -m coding_pet.cli daemon run` is still a placeholder
- `python -m coding_pet.cli widget run` is still a placeholder
- the GUI shell falls back gracefully when PySide6 runtime libraries are unavailable
- panel actions are modeled in the UI layer but not yet routed back into live monitored sessions
