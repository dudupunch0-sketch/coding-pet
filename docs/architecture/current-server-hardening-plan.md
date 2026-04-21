# Current Server Hardening Plan

## Goal

Make `coding-pet` dependable on the current disk-constrained server without requiring local Claude Code or OpenCode installs. Keep this plan limited to the minimum work needed to remove remaining hardcoded backend assumptions, make degraded-mode failures deterministic, and prove the system stays testable with no real backends present.

## Constraints

- The current server has no Claude Code installed.
- The current server has no OpenCode installed.
- The current server does not have enough disk space to add those tools.
- Current-server work must remain useful and verifiable with zero real agent backends available.
- Anything that mainly depends on real backend behavior should move to the future server plan.

## Already Done

- Daemon runtime and Unix-socket IPC are in place.
- Widget live mode and `action_result` feedback are implemented.
- Restored sessions are already treated as read-only until live state replaces them.
- Reconnect reset behavior is already implemented.
- Backend availability detection already exists through the backend registry.
- `admin doctor` already reports backend availability.
- `daemon monitor` already fails fast when a requested backend is unavailable.
- Architecture and operations docs were already updated to match the current baseline.

## Mandatory Remaining Work

- Remove daemon hardcoded adapter selection and route through the optional backend registry or a tiny capability lookup.
  `src/coding_pet/daemon/app.py` must stop choosing adapters via `adapter_for()` and instead use the same optional-backend source of truth already used for availability reporting.
- Normalize the failure contract for unavailable, unsupported, read-only, and dead-session flows.
  Keep daemon, IPC, and widget handling consistent so these cases return stable reasons instead of ad hoc messages.
- Strengthen backend-less tests.
  Add or tighten tests around registry-backed adapter resolution, degraded action handling, and widget behavior so the suite remains trustworthy without Claude Code or OpenCode installed.

## Recommended Remaining Work

- Expand `admin doctor` only if it materially improves operator diagnosis on this server.
- Add deploy smoke checks and service verification for daemon and widget startup in degraded mode.
- Polish README and operations docs only enough to reflect the final constrained-server behavior and the split with the future server plan.

## Moved to Future Server Plan

- Rich per-session capability negotiation beyond simple availability and support checks.
- Backend-native reply, approve, and reject semantics validated against real installed backends.
- Transcript and process integration expansion beyond the current lightweight runtime path.
- Internal or company backend support, including endpoint and credential handling.
- Real-backend integration testing, mixed-backend validation, and backend-specific operator workflows.

## Design Direction for Remaining Current-Server Work

- Reuse the existing backend registry. Do not introduce a second registry, plugin system, or large abstraction layer on this server.
- Replace `DaemonApp.adapter_for()` with a small registry-backed lookup so daemon launch and control paths use the same optional-backend truth source as `daemon monitor` and `admin doctor`.
- Do not build a rich capability system yet. Current-server hardening only needs enough support lookup to avoid hardcoded selection and to reject unsupported actions cleanly.
- Prefer a small set of stable reason strings and simple human-readable details. If the current `action_result` shape needs one more field, add a single reason string rather than a larger error schema.
- Keep widget and daemon contracts simple. The daemon should make the decision; the widget should only reflect success, failure, read-only state, or unsupported state without learning backend-specific policy.

## Verification

- Run targeted tests for registry-backed adapter resolution with no local backends installed.
- Run daemon and widget action-path tests for unavailable, unsupported, read-only, and dead-session cases.
- Verify `coding-pet daemon monitor` still fails fast for unavailable backends.
- Verify `coding-pet admin doctor` remains clear and non-fatal in a backend-less environment.
- Keep all required verification runnable on the current server without installing Claude Code or OpenCode.

## Exit Criteria

- The daemon no longer hardcodes adapter selection in `src/coding_pet/daemon/app.py`.
- Unavailable, unsupported, read-only, and dead-session flows produce deterministic failure reasons through the existing control path.
- Backend-less tests cover those degraded cases and pass without real backend binaries.
- The current server is supportable without installing Claude Code or OpenCode.
- Remaining backend-rich work is explicitly deferred to the future server plan.
