# coding-pet on RHEL 8.10

## Target assumptions

- Red Hat Enterprise Linux 8.10 or a compatible enterprise desktop/server install
- Python 3.11+
- graphical session available for the widget and desktop notifications
- Unix domain sockets available under the user runtime directory

## Dependencies

Minimum development/runtime expectations:
- Python 3.11+
- `pip`
- PySide6 Python package
- working GUI runtime libraries for Qt
- `notify-send` or DBus/libnotify-compatible desktop notification path

Create a virtual environment and install the project:
```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
```

## Important GUI note

In the current CI/container environment used for development, PySide6 imports can fail because system GUI libraries such as `libEGL.so.1` are unavailable. The widget code handles that gracefully for tests, but a real desktop deployment needs the full Qt runtime stack present.

If `scripts/run_widget.py` prints:
```text
PySide6 GUI runtime is unavailable in this environment.
```
then the Python package is installed but the host still lacks GUI runtime support.

## Verified commands

Top-level help:
```bash
PYTHONPATH=src python -m coding_pet.cli --help
```

Daemon help:
```bash
PYTHONPATH=src python -m coding_pet.cli daemon --help
```

Daemon monitor help:
```bash
PYTHONPATH=src python -m coding_pet.cli daemon monitor --help
```

Widget demo:
```bash
PYTHONPATH=src python scripts/run_widget.py
```

Daemon placeholder bootstrap:
```bash
PYTHONPATH=src python scripts/run_daemon.py
```

## Monitoring two simultaneous agents

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

This validates the current monitor command path. A full long-running service wrapper is still pending.

## Files and paths

By default coding-pet uses:
- config dir: `~/.config/coding-pet`
- state dir: `~/.local/state/coding-pet`
- runtime dir: `${XDG_RUNTIME_DIR}/coding-pet`
- logs: `~/.local/state/coding-pet/logs`
- persisted snapshot: `~/.local/state/coding-pet/state.json`

Useful overrides:
```bash
export CODING_PET_CONFIG_DIR=/custom/config
export CODING_PET_STATE_DIR=/custom/state
export CODING_PET_RUNTIME_DIR=/custom/runtime
export CODING_PET_STATE_FILE=/custom/state/state.json
export CODING_PET_LOG_DIR=/custom/logs
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

### CLI commands appear missing
If you are running from a source checkout, prefer:
```bash
PYTHONPATH=src python -m coding_pet.cli ...
```
This avoids importing an older editable install from a different checkout.

## Current limitations

- `daemon run` is still a placeholder
- `widget run` is still a placeholder
- panel actions are not yet routed back to the monitored process
- systemd user services are not yet defined
- asset/theme pack is still placeholder quality
