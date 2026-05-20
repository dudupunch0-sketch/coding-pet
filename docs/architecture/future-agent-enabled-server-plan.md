# Future Agent-Enabled Server Plan

## Goal

Start this plan only after current-server hardening is complete. Extend `coding-pet` on a backend-capable server so real installed and internal backends can run through a richer shared daemon contract with negotiated capabilities, backend-native action semantics, backend-native transcript/process integration beyond the current tmux path, and real-backend validation.

## Assumptions for the Future Server

- The future server has enough disk space to install and maintain real backends.
- Claude Code and OpenCode can be installed there.
- If internal or company backends are in scope, the future server also has the required network access, credentials, and endpoints.
- The future server can run gated integration checks in disposable workspaces.
- This plan is a follow-on track, not a replacement for current-server hardening.

## Baseline Expected Before Starting

- Current-server hardening exit criteria are met.
- `src/coding_pet/daemon/app.py` no longer hardcodes adapter selection.
- Degraded-mode failures are normalized for unavailable, unsupported, read-only, and dead-session cases.
- The current tmux path already provides discovery/capture/control, SQLite transcripts, and IPC transcript snapshot/appended-event updates without requiring local Claude Code/OpenCode installs.
- Backend-less tests pass without requiring Claude Code or OpenCode.
- Docs clearly separate constrained-server behavior from future backend-capable behavior.
- Company-server handoff docs, source-checkout systemd units, `company-pet` assets, and wheel shared-data packaging are locally verified.
- Company-server bring-up has followed `docs/operations/company-server-handoff.md` and recorded whether GUI/backend prerequisites are actually present.

## Work Moved Here from the Current Server Plan

- Richer capability negotiation and per-session supported-action exposure.
- Backend-native reply, approve, and reject semantics.
- Backend-native transcript/process integration beyond the current tmux SQLite transcript path.
- Internal or company backend support.
- Real-backend validation against installed tools.
- Any operator workflow or tooling whose value depends on real backends being present.

## Future-Server Workstreams

### 1. Rich Capability Negotiation

- Evolve the current simple availability model into negotiated per-session capabilities.
- Record supported actions, transcript access, reconnect behavior, and backend identity at session start.
- Keep the daemon as the policy boundary so the widget consumes capabilities but does not invent backend rules.

### 2. Backend-Native Action Semantics

- Replace generic placeholder control behavior with backend-native reply, approve, and reject handling where supported.
- Let adapters return richer action outcomes such as accepted, rejected, timed out, unsupported, or backend-failed.
- Preserve a backend-agnostic IPC contract while allowing backend-specific logic to stay inside adapters.

### 3. Backend-Native Transcript and Process Integration Expansion

- Extend the current SQLite transcript path with backend-native history, redaction, and retention controls.
- Correlate backend output, daemon-issued actions, timestamps, process state, and reconnect boundaries.
- Support backends that expose richer history than raw process output.

### 4. Internal and Company Backend Support

- Add adapters for non-CLI or server-owned backends using the same daemon contract.
- Define configuration for endpoints, credentials, and allowlisted capabilities per server.
- Keep Claude Code and OpenCode as first-class reference backends without hardcoding the overall design around only those two.

### 5. Real-Backend Validation and Operations

- Add a gated integration suite for installed backends and any approved internal backend on the future server.
- Validate mixed-backend multi-session operation, restart and reconnect flows, and transcript continuity.
- Write a future-server runbook that stays separate from the constrained-server operating docs.

## Verification on the Future Server

- Run the baseline unit and backend-less suite first.
- Run gated real-backend tests against installed Claude Code, OpenCode, and any approved internal backend on that server.
- Verify negotiated capabilities are exposed correctly per session and drive allowed actions correctly.
- Verify backend-native reply, approve, and reject semantics end to end on real sessions.
- Verify transcript capture, restart, reconnect, and restored-session continuity with real backend activity.

## Exit Criteria

- The future server runs real backends through one daemon contract rather than backend-specific daemon code paths.
- Sessions expose negotiated capabilities, and unsupported actions fail explicitly and predictably.
- Reply, approve, and reject are validated against real backend behavior rather than only placeholder control strings.
- Transcript and process integration is durable, configurable, and correlated with session and action state.
- At least the intended installed backends for that server, including Claude Code or OpenCode and any approved internal backend, pass the future-server validation workflow.
- The future-server track remains clearly separate from current-server hardening and does not reopen constrained-server scope.
