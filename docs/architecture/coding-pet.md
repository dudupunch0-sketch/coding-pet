# coding-pet architecture

## Goal

coding-pet monitors multiple AI coding agent sessions and presents their state through small desktop pets, a shared session panel, notifications, and persisted state. Claude Code and OpenCode are the production targets; Codex support is optional and kept as a local development adapter.

## High-level components

### 1. Agent adapters
Files:
- `src/coding_pet/agents/base.py`
- `src/coding_pet/agents/claude_code.py`
- `src/coding_pet/agents/opencode.py`
- `src/coding_pet/agents/codex.py`
- `src/coding_pet/agents/registry.py`

Responsibilities:
- normalize per-agent launch metadata
- build initial `SessionStatus`
- classify output lines through the shared classifier
- provide agent-specific launch commands
- provide adapter-defined control messages for reply, approval, and rejection actions
- report whether local backend binaries are available so daemon/CLI flows can degrade cleanly
- keep optional adapters, such as Codex, outside the production assumptions for the company server

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
- enforce each session's `action_capabilities` before dispatching live control,
  while preserving legacy `supported_actions` snapshots
- discover and poll already-running tmux panes when tmux monitoring is enabled
- preserve raw dashboard input and adapter-defined control messages by delivering them through tmux buffers instead of shell-quoted strings
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

These models are the contract between daemon, IPC, persistence, and widget
layers. `SessionStatus.action_capabilities` records which daemon actions are
safe for that session and the transport/semantics behind each action. The older
`supported_actions` list is still populated for snapshot compatibility.
Restored/inactive sessions are reduced to local-only actions.

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
- `hook_event`
- `hook_event_result`
- `ping`

Behavior:
- a new widget receives a full snapshot first
- later updates stream incrementally
- widget action requests are sent back over the same socket and acknowledged with `action_result`
- malformed JSON and non-object IPC payloads are answered with structured
  `error` messages while keeping the connection alive
- `action_result` carries a stable `outcome` value plus legacy-compatible
  `ok`, `reason`, and `detail` fields; normalized outcomes cover `accepted`,
  `local_updated`, `rejected`, `timed_out`, `unsupported`, and
  `backend_failed`
- degraded failures still use stable `reason` strings such as unavailable
  backends, inactive sessions, unsupported session capabilities, or missing
  live control
- `mark_read` is a daemon-local session-state action and does not require an agent control channel
- `hide_pet` is a daemon-local dismiss action for inactive sessions; live control
  sources must stop or disappear before they can be hidden
- `manual_state_override` is a daemon-local correction action and does not
  require an agent control channel
- `transcript_request` returns recent transcript rows for one session, or an empty `ok=false` snapshot when transcripts are unavailable
- daemon-side transcript appends are broadcast as `transcript_appended` so an open detail popup can stay current
- Claude Code/OpenCode hook scripts can send `hook_event` messages to update pet state without network access
- reconnecting widgets can rebuild state without restarting the daemon

### 5. Widget layer
Files:
- `src/coding_pet/gui/app.py`
- `src/coding_pet/gui/widget.py`
- `src/coding_pet/gui/bubble.py`
- `src/coding_pet/gui/theme.py`
- `src/coding_pet/gui/runtime.py`
- `src/coding_pet/gui/session_panel.py`
- `src/coding_pet/gui/detail_view_model.py`
- `src/coding_pet/gui/detail_popup.py`
- `src/coding_pet/gui/transcript_view.py`
- `src/coding_pet/gui/reply_box.py`

Responsibilities:
- map daemon session state to pet mood and bubble text
- keep a stable multi-pet layout on screen
- expose a shared panel view model for urgent sessions and actions
- show a per-session detail popup model with target identity, last input, agent request, transcript rows, and raw reply/attach action request helpers
- bootstrap from persisted snapshot before live IPC updates arrive
- render transient success/failure action feedback without overwriting the real session summary
- treat restored snapshot sessions as read-only in the panel
- on detail-popup open, request the latest transcript snapshot and send `mark_read`; later `transcript_snapshot` and `transcript_appended` messages update the popup model
- route detail-popup send, send-without-enter, and attach actions back to the daemon over IPC
- discover the default `codex-default` PNG theme and the registered PMD SpriteCollab sample character themes from source assets, `CODING_PET_ASSETS_DIR`, or installed `share/coding-pet/assets`
- keep the classic text theme available as an explicit fallback

Current implementation notes:
- the shell supports a PySide6-backed UI when runtime libraries and a Linux graphical display are present
- in headless, no-display, or incomplete GUI environments, the non-Qt fallback still preserves state/layout logic for tests and command verification

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
- write snapshots through a temporary file and atomic replace so interrupted
  writes keep the previous snapshot intact
- quarantine unreadable or schema-invalid snapshots as `state.json.invalid.*`
  and continue startup with an empty restored snapshot
- store timestamped transcript events in SQLite for tmux output, dashboard
  input, hook events, and system notes
- redact common token/password/API key patterns before transcript persistence

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

### hook-driven sessions

1. Claude Code hooks or OpenCode plugins call the local hook script.
2. The hook script extracts session/workspace/title/summary from common stdin
   JSON aliases or environment overrides, then sends `hook_event` over the
   daemon Unix socket without external network access.
3. `DaemonRuntime` converts the event to a `SessionStatus(source_kind="hook")`.
4. The same event is stored as a `hook_event` transcript row and broadcast as
   `transcript_appended`, so detail popups keep a local event timeline even when
   no tmux transcript is available.

### tmux-discovered sessions

1. `TmuxMonitorService` calls `tmux list-panes -a` and applies include/exclude rules.
2. Matched Claude Code/OpenCode panes become `SessionStatus(source_kind="tmux")` entries with pane/session/cwd metadata. Codex panes may also match in local development, but Codex is not required on the company server.
3. The monitor captures recent output with `tmux capture-pane -p -J -S -N`, diffs snapshots, stores new output in SQLite transcripts, and best-effort broadcasts appended transcript events to connected widgets.
4. `AgentStateClassifier` evaluates the snapshot with deterministic patterns; no LLM call is used for status detection.
5. Daemon tmux action handlers for `send_reply` and `send_without_enter` preserve raw text and call `tmux load-buffer`, `paste-buffer`, and optional `send-keys Enter`. For `approve` and `reject`, the matched agent adapter supplies the control text before the same tmux delivery path is used.
6. When a matched pane disappears, failed sessions keep their failure state for
   operator review. Other sessions become inactive `completed` sessions and are
   removed after the configured completed-session retention window.

## Concurrency model

- one monitor task per session
- `SessionRegistry` guarded by `asyncio.Lock`
- registry subscribers receive update callbacks asynchronously
- widget IPC listener runs as a background task separate from UI presentation state

## Restart behavior

- daemon-side snapshot persistence writes the latest session set to disk
- widget can load the snapshot before it connects to the daemon socket
- restored snapshot sessions are treated as non-live/read-only until a live daemon snapshot replaces them
- restored inactive completed sessions are skipped when their completed-session
  retention window already elapsed; recent completed sessions only keep the
  remaining display time
- process-launched sessions set `live=false` when their monitored process exits
- when a process-launched monitor is stopped by daemon shutdown or
  `stop_session`, the daemon best-effort terminates the owned process and marks
  the snapshot inactive without pretending the agent completed successfully;
  after `CODING_PET_PROCESS_STOP_TIMEOUT_SEC`, it uses a kill fallback
- tmux-discovered sessions set `live=false` when their pane disappears; failed
  sessions preserve failure state, while other disappeared panes become
  inactive `completed` sessions
- reconnecting IPC clients receive a fresh snapshot immediately
- reconnect clears stale action feedback so the snapshot becomes the source of truth again

## Current gaps

- actual agent-native approval/rejection semantics are still adapter-defined stdin strings rather than proven per-agent protocols
- the PySide6 environment on this host is still unavailable for real manual GUI runs, so some UX work remains test-driven only
- full manual PySide6 detail-popup UX still needs target-host validation; send/attach action wiring, daemon action handlers, and headless request builders are covered by tests
- this server still uses constrained degraded-mode operation for Claude Code/OpenCode because those binaries are not installed locally; the optional Codex adapter follows the same degraded behavior
- default `codex-default` sprite/theme assets are generated original repo art, not third-party character art; PMD SpriteCollab sample character themes are bundled separately for non-commercial selectable-character testing, and final company brand art or approved Codex/Petdex packages can replace them through complete imported themes
- transcript capture is a bounded tmux screen-diff log; common secret patterns
  and configured organization-specific regexes are redacted, while perfect TTY
  replay is future work
- company-server GUI/backend behavior still needs validation on the actual target environment
