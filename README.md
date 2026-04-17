# coding-pet

coding-pet is a production-quality desktop companion for monitoring multiple AI coding agent sessions on Linux systems such as Red Hat Enterprise Linux 8.10.

## Current direction

- Python application with a long-running daemon and GUI widget layer
- One pet per monitored session
- Shared control panel for all sessions
- Claude Code CLI and OpenCode CLI monitoring targets
- Screen-edge stack layout for multiple pets

## Development setup

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
pytest -v
```

## Planned CLI surface

```bash
coding-pet daemon run
coding-pet widget run
coding-pet admin doctor
```
