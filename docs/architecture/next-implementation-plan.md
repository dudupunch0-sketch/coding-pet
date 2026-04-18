# Next Implementation Plan

Last updated: 2026-04-18

## Objective

Finish the transition from a monitored-session viewer into a live desktop control loop. The next implementation milestone is not "build a daemon runtime" anymore. It is "route panel actions into active monitored sessions, report the result back to the widget, and make the widget use the live daemon path by default."

## Current Verified Baseline

### Runtime, persistence, and live IPC already exist

- `daemon run` already boots a real `DaemonRuntime`, restores persisted sessions through `MonitorManager.restore_from_store()`, starts `IpcServer`, and exposes a live Unix socket.
- `MonitorManager` already handles persistence, notifications, and registry updates for monitored sessions.
- IPC already supports `snapshot`, `session_updated`, `session_removed`, and `ping`.
- `CodingPetWidgetApp` can already connect to the daemon socket, consume snapshots and incremental updates, and keep deterministic pet layout for multiple live sessions.
- The CLI and widget layers already have test coverage for daemon bootstrap and live IPC updates.

### Panel actions and quick replies already exist

- The panel model already exposes `approve`, `reject`, and `send_reply` actions.
- `SessionPanelViewModel.QUICK_REPLY_SHORTCUTS` already defines these quick replies for `NEEDS_INPUT` sessions:
  - `keep going`
  - `summarize shortly`
- The widget can already dispatch those replies as IPC `action_request` messages with `session_id`, `action`, and `reply_text`.
- `IpcServer` can already forward `action_request` payloads to an injected `action_handler`.
- Existing tests already prove both the shortcut exposure and IPC dispatch path.

### What is still missing

- `DaemonRuntime` does not currently install an `action_handler`, so panel actions sent to the live daemon are not routed anywhere useful.
- Live monitored sessions do not retain a writable control surface for replies or approvals. Monitoring is read-only today.
- There is no daemon-side action router that maps `send_reply`, `approve`, or `reject` into the active monitored process or adapter.
- There is no daemon-to-widget acknowledgement/error event after an action is sent.
- `widget run` is still demo-oriented instead of connecting to the live daemon by default.
- There is still no end-to-end test proving that `keep going` or `summarize shortly` reaches a real monitored session.

## Phase 1: Wire panel actions into the existing daemon runtime

Goal: make `action_request` reach a real daemon-owned routing layer.

Concrete work:

- Add a daemon-owned session action router and inject it into `IpcServer(action_handler=...)` from `DaemonRuntime`.
- Define one validated action contract for:
  - `send_reply`
  - `approve`
  - `reject`
- Reject malformed requests early and log unsupported actions, missing sessions, and dead sessions.
- Keep the router runtime-owned so the widget remains a thin client and adapters stay agent-specific.

Likely touch points:

- `src/coding_pet/daemon/runtime.py`
- `src/coding_pet/ipc/server.py`
- new daemon action-routing module

Exit criteria:

- A live `daemon run` process no longer drops `action_request` on the floor.
- The runtime can identify the target session and hand the request to a daemon-owned router.

Testing checkpoint:

- Add unit tests for action validation and runtime wiring.
- Extend IPC tests to prove a real `DaemonRuntime` passes `action_request` into the router, not just a test-injected standalone `IpcServer`.

## Phase 2: Add a live control channel for monitored sessions

Goal: make routed actions actually change active monitored sessions.

Concrete work:

- Extend monitored-session bookkeeping so each live session retains the control handle needed for action execution.
- Launch monitored processes with the control surface required for replies, starting with stdin-backed reply injection where supported.
- Add adapter-facing control methods or a small control abstraction so agent-specific reply/approval behavior stays out of the widget and IPC layers.
- Implement `send_reply` first and route both freeform replies and quick reply shortcuts through the same path.
- Define read-only behavior for restored historical sessions that have status but no live control channel.

Likely touch points:

- `src/coding_pet/daemon/app.py`
- `src/coding_pet/daemon/manager.py`
- `src/coding_pet/daemon/monitor.py`
- `src/coding_pet/agents/base.py`
- agent-specific adapters

Exit criteria:

- A live monitored session can receive a reply from the daemon action router.
- `keep going` and `summarize shortly` are both routed to the monitored session exactly once.
- Unsupported actions fail explicitly instead of silently disappearing.

Testing checkpoint:

- Add integration tests with a fake controllable process that captures stdin or the chosen control channel.
- Add coverage for dead-session, restored-session, and unsupported-adapter cases.
- Add end-to-end tests proving both built-in shortcuts traverse widget -> IPC -> daemon -> live session.

## Phase 3: Close the widget interaction loop

Goal: make the desktop UI operate against the live daemon rather than a demo-only flow.

Concrete work:

- Change `widget run` so the normal path connects to the daemon socket and shows live sessions.
- Surface action success/failure back into the widget with a dedicated daemon message type rather than fire-and-forget behavior.
- Mark read-only sessions in the panel and disable actions that cannot succeed.
- Preserve unread state, ordering, and panel updates when an action triggers follow-up session output.

Likely touch points:

- `src/coding_pet/cli.py`
- `src/coding_pet/gui/app.py`
- `src/coding_pet/gui/widget.py`
- panel/view-model code

Exit criteria:

- Starting the widget against a running daemon shows live sessions by default.
- Submitting a quick reply or approval visibly succeeds or fails in the UI.
- Reconnects and mid-session widget restarts still rebuild the correct state.

Testing checkpoint:

- Add widget integration tests for action submission plus daemon acknowledgement/error messages.
- Add reconnect coverage for action results arriving after the widget restarts.

## Phase 4: Harden operations and documentation around the live control loop

Goal: make the new behavior supportable on a real desktop install.

Concrete work:

- Add structured logging around action routing, control-channel writes, and action failures.
- Update stale operational docs to match the real daemon/runtime state and the new action flow.
- Re-verify systemd user-service wiring against the actual runtime commands.
- Document which session types are fully interactive versus read-only after restore.

Likely touch points:

- `docs/operations/rhel8-setup.md`
- `docs/architecture/coding-pet.md`
- packaging/service docs

Exit criteria:

- Docs describe the live runtime truthfully.
- Operators can tell whether a session is actionable, restored-only, or failed.
- Standard local service startup instructions match the real code path.

Testing checkpoint:

- Run targeted integration tests for daemon runtime, IPC action flow, and widget action feedback.
- Run the full verification suite before calling the live control loop complete.

## Recommended Delivery Order

1. Land Phase 1 first so panel actions have a real daemon entry point.
2. Land Phase 2 next so `send_reply` and the two quick reply shortcuts stop being dead-end UI affordances.
3. Land Phase 3 after routing exists so the widget can report real outcomes instead of sending blind requests.
4. Finish with Phase 4 so docs and service operations match the live control loop.

## Immediate Next Task

Implement Phase 1 by adding a daemon-owned action router, wiring it into `DaemonRuntime` as the IPC `action_handler`, and covering that path with tests. Do not reopen the daemon bootstrap architecture first; the runtime already exists. The next missing behavior is live action routing.
