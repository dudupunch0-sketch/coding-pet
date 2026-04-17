# coding-pet architecture

## Goal

coding-pet monitors multiple AI coding agent sessions and presents their state through small desktop pets, a shared session panel, notifications, and persisted state.

## High-level components

### 1. Agent adapters
Files:
- `src/coding_pet/agents/base.py`
- `src/coding_pet/agents/claude_code.py`
- `src/coding_pet/agents/opencode.py`

Responsibilities:
- normalize per-agent launch metadata
- build initial `SessionStatus`
- classify output lines through the shared classifier
- provide agent-specific launch commands

### 2. Daemon core
Files:
- `src/coding_pet/daemon/monitor.py`
- `src/coding_pet/daemon/manager.py`
- `src/coding_pet/daemon/app.py`
- `src/coding_pet/daemon/session_registry.py`

Responsibilities:
- launch and monitor one async task per session
- classify raw output into attention-state changes
- maintain a concurrent in-memory session registry
- notify users on important state transitions
- persist snapshots to disk for restart recovery

### 3. Models and events
Files:
- `src/coding_pet/models.py`
- `src/coding_pet/events.py`

Core types:
- `AgentKind`
- `AttentionState`
- `SessionStatus`
- `SessionEvent`

These models are the contract between daemon, IPC, persistence, and widget layers.

### 4. IPC layer
Files:
- `src/coding_pet/ipc/server.py`
- `src/coding_pet/ipc/client.py`

Transport:
- Unix domain socket
- newline-delimited JSON

Supported message types:
- `snapshot`
- `session_updated`
- `session_removed`
- `ping`

Behavior:
- a new widget receives a full snapshot first
- later updates stream incrementally
- reconnecting widgets can rebuild state without restarting the daemon

### 5. Widget layer
Files:
- `src/coding_pet/gui/app.py`
- `src/coding_pet/gui/widget.py`
- `src/coding_pet/gui/bubble.py`
- `src/coding_pet/gui/theme.py`
- `src/coding_pet/gui/session_panel.py`

Responsibilities:
- map daemon session state to pet mood and bubble text
- keep a stable multi-pet layout on screen
- expose a shared panel view model for urgent sessions and actions
- bootstrap from persisted snapshot before live IPC updates arrive

Current implementation notes:
- the shell supports a PySide6-backed UI when runtime libraries are present
- in headless or incomplete GUI environments, the non-Qt fallback still preserves state/layout logic for tests and command verification

### 6. Notifications
Files:
- `src/coding_pet/notifiers/base.py`
- `src/coding_pet/notifiers/desktop.py`
- `src/coding_pet/notifiers/sound.py`

Responsibilities:
- emit desktop alerts for important transitions
- suppress repeated notifications with cooldown tracking
- keep the notifier interface abstract for future DBus/audio expansion

### 7. Persistence
File:
- `src/coding_pet/state_store.py`

Responsibilities:
- store the latest session snapshot in JSON form
- restore known sessions after restart
- provide widget bootstrap state before the daemon socket is available

Default path:
- `~/.local/state/coding-pet/state.json`

## Data flow

1. CLI or future daemon service launches a monitored agent command.
2. `MonitorTask` reads stdout/stderr lines asynchronously.
3. `OutputClassifier` converts lines and exits into `AttentionState` changes.
4. `SessionRegistry` updates the latest `SessionStatus`.
5. `MonitorManager` reacts to registry updates for notifications and persistence.
6. `IpcServer` broadcasts snapshots and incremental updates.
7. `CodingPetWidgetApp` receives IPC messages, updates widget shells, and reflows the layout.

## Concurrency model

- one monitor task per session
- `SessionRegistry` guarded by `asyncio.Lock`
- registry subscribers receive update callbacks asynchronously
- widget IPC listener runs as a background task separate from UI presentation state

## Restart behavior

- daemon-side snapshot persistence writes the latest session set to disk
- widget can load the snapshot before it connects to the daemon socket
- reconnecting IPC clients receive a fresh snapshot immediately

## Current gaps

- full daemon service orchestration is still placeholder-level
- widget panel actions are not yet routed back into live agents
- sprite/theme assets are placeholder quality
- packaging/systemd integration is still pending
