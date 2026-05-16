# coding-pet architecture

## Goal

coding-pet monitors multiple AI coding agent sessions and presents their state through small desktop pets, a shared session panel, notifications, and persisted state.

## High-level components

### 1. Agent adapters
Files:
- `src/coding_pet/agents/base.py`
- `src/coding_pet/agents/claude_code.py`
- `src/coding_pet/agents/opencode.py`
- `src/coding_pet/agents/registry.py`

Responsibilities:
- normalize per-agent launch metadata
- build initial `SessionStatus`
- classify output lines through the shared classifier
- provide agent-specific launch commands
- report whether local backend binaries are available so daemon/CLI flows can degrade cleanly

### 2. Daemon core
Files:
- `src/coding_pet/daemon/monitor.py`
- `src/coding_pet/daemon/manager.py`
- `src/coding_pet/daemon/app.py`
- `src/coding_pet/daemon/runtime.py`
- `src/coding_pet/daemon/action_router.py`
- `src/coding_pet/daemon/session_registry.py`
- `src/coding_pet/daemon/tmux_monitor.py`
- `src/coding_pet/daemon/tmux_discovery_service.py`

Responsibilities:
- launch and monitor one async task per session
- classify raw output into attention-state changes
- maintain a concurrent in-memory session registry
- notify users on important state transitions
- persist snapshots to disk for restart recovery
- validate and route widget action requests through a daemon-owned control path
- discover and poll already-running tmux panes when tmux monitoring is enabled
- preserve raw dashboard input by delivering it through tmux buffers instead of shell-quoted strings
- distinguish live sessions from restored snapshot-only sessions
- resolve adapters through the backend registry instead of hardcoded daemon selection

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
- `action_request`
- `action_result`
- `transcript_request`
- `transcript_snapshot`
- `transcript_appended`
- `ping`

Behavior:
- a new widget receives a full snapshot first
- later updates stream incrementally
- widget action requests are sent back over the same socket and acknowledged with `action_result`
- `action_result` now carries a stable `reason` string for degraded failures such as unavailable backends, inactive sessions, or missing live control
- reconnecting widgets can rebuild state without restarting the daemon

### 5. Widget layer
Files:
- `src/coding_pet/gui/app.py`
- `src/coding_pet/gui/widget.py`
- `src/coding_pet/gui/bubble.py`
- `src/coding_pet/gui/theme.py`
- `src/coding_pet/gui/session_panel.py`
- `src/coding_pet/gui/detail_view_model.py`
- `src/coding_pet/gui/detail_popup.py`
- `src/coding_pet/gui/transcript_view.py`
- `src/coding_pet/gui/reply_box.py`

Responsibilities:
- map daemon session state to pet mood and bubble text
- keep a stable multi-pet layout on screen
- expose a shared panel view model for urgent sessions and actions
- show a per-session detail popup model with target identity, last input, agent request, transcript rows, and raw reply actions
- bootstrap from persisted snapshot before live IPC updates arrive
- render transient success/failure action feedback without overwriting the real session summary
- treat restored snapshot sessions as read-only in the panel

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
Files:
- `src/coding_pet/state_store.py`
- `src/coding_pet/transcripts/model.py`
- `src/coding_pet/transcripts/store.py`

Responsibilities:
- store the latest session snapshot in JSON form
- restore known sessions after restart as non-live/read-only state
- provide widget bootstrap state before the daemon socket is available
- store timestamped transcript events in SQLite for tmux output, dashboard input, and system notes

Default paths:
- `~/.local/state/coding-pet/state.json`
- `~/.local/state/coding-pet/transcripts.sqlite`

## Data flow

### Process-launched sessions

1. CLI or daemon service launches a monitored agent command.
2. `MonitorTask` reads stdout/stderr lines asynchronously.
3. `OutputClassifier` converts lines and exits into `AttentionState` changes.
4. `SessionRegistry` updates the latest `SessionStatus`.
5. `MonitorManager` reacts to registry updates for notifications and persistence.
6. `IpcServer` broadcasts snapshots and incremental updates.
7. `CodingPetWidgetApp` receives IPC messages, updates widget shells, and reflows the layout.
8. Panel actions such as `send_reply`, `approve`, and `reject` are sent back to the daemon as `action_request` messages.
9. `SessionActionRouter` validates those requests and `MonitorManager` dispatches them through the live session control handler.
10. The widget receives `action_result` acknowledgements and shows transient UI feedback until newer session output arrives.

### tmux-discovered sessions

1. `TmuxMonitorService` calls `tmux list-panes -a` and applies include/exclude rules.
2. Matched Claude Code/OpenCode panes become `SessionStatus(source_kind="tmux")` entries with pane/session/cwd metadata.
3. The monitor captures recent output with `tmux capture-pane -p -J -S -N`, diffs snapshots, and stores new output in SQLite transcripts.
4. `AgentStateClassifier` evaluates the snapshot with deterministic patterns; no LLM call is used for status detection.
5. Detail popup actions preserve raw text and call `tmux load-buffer`, `paste-buffer`, and optional `send-keys Enter`.

## Concurrency model

- one monitor task per session
- `SessionRegistry` guarded by `asyncio.Lock`
- registry subscribers receive update callbacks asynchronously
- widget IPC listener runs as a background task separate from UI presentation state

## Restart behavior

- daemon-side snapshot persistence writes the latest session set to disk
- widget can load the snapshot before it connects to the daemon socket
- restored snapshot sessions are treated as non-live/read-only until a live daemon snapshot replaces them
- reconnecting IPC clients receive a fresh snapshot immediately
- reconnect clears stale action feedback so the snapshot becomes the source of truth again

## Current gaps

- actual agent-native approval/rejection semantics are still stdin-string based placeholders rather than proven per-agent protocols
- the PySide6 environment on this host is still unavailable for real manual GUI runs, so some UX work remains test-driven only
- this server still uses constrained degraded-mode operation for Claude Code/OpenCode because those binaries are not installed locally
- sprite/theme assets are still placeholder quality
