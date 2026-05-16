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
- `tmux` when monitoring already-running Claude Code/OpenCode terminal panes

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
- `gui_runtime=unavailable` in headless/minimal environments

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
- prints `PySide6 GUI runtime is unavailable in this environment.` when the host lacks Qt runtime support

Tmux pane discovery help:
```bash
PYTHONPATH=src python -m coding_pet.cli daemon discover-tmux --help
PYTHONPATH=src python -m coding_pet.cli daemon monitor-tmux --help
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
This watches already-running panes via `tmux list-panes` and `tmux capture-pane`; it does not launch agents or configure LLM providers. Detail-popup input is delivered with `tmux load-buffer` and `tmux paste-buffer`, so Korean text, newlines, quotes, `$`, `;`, and backslashes are preserved as raw text.

Transcript events are stored in SQLite when transcripts are enabled:
```text
~/.local/state/coding-pet/transcripts.sqlite
```
Use `CODING_PET_TRANSCRIPT_DB` to move the DB or `CODING_PET_TRANSCRIPT_ENABLED=0` to disable transcript capture.

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
systemd-analyze verify packaging/systemd/coding-pet-daemon.service
systemd-analyze verify packaging/systemd/coding-pet-widget.service
systemd-analyze verify packaging/systemd/coding-pet.target
```

Install for the current user:
```bash
mkdir -p ~/.config/systemd/user
cp packaging/systemd/coding-pet-daemon.service ~/.config/systemd/user/
cp packaging/systemd/coding-pet-widget.service ~/.config/systemd/user/
cp packaging/systemd/coding-pet.target ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now coding-pet.target
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
export CODING_PET_RUNTIME_DIR=/custom/runtime
export CODING_PET_STATE_FILE=/custom/state/state.json
export CODING_PET_LOG_DIR=/custom/logs
export CODING_PET_TMUX_ENABLED=1
export CODING_PET_TMUX_CAPTURE_LINES=200
export CODING_PET_TMUX_POLL_INTERVAL_MS=1000
export CODING_PET_TRANSCRIPT_DB=/custom/state/transcripts.sqlite
export CODING_PET_TRANSCRIPT_ENABLED=1
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

- the action transport into live sessions currently writes simple adapter-defined control messages to monitored process stdin; this still needs validation against real Claude Code/OpenCode workflows
- the GUI shell still depends on a full PySide6/Qt runtime, which is unavailable in the current headless test environment
- restored snapshot sessions are intentionally read-only until a live daemon connection replaces them with active sessions
- asset/theme pack is still placeholder quality
