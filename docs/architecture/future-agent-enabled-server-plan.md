# Future Agent-Enabled Server Plan

This plan applies only after the current-server hardening plan is complete. It is a separate follow-up track for a future server that already has real agent backends installed, and it must not block or reopen current-server hardening work.

## Goal

Refactor and extend `coding-pet` so the daemon can drive real installed agent backends and server-owned/internal LLM agents as first-class backends, with capability-aware routing, richer action semantics, transcript/process capture, and validation against real tools.

## Assumptions for the Future Server

- The future server has working installations of `claude code`, `opencode`, and possibly one or more company/server-owned agent backends.
- Those backends may expose different control surfaces: stdin/stdout, local IPC, HTTP/gRPC, or job-oriented server APIs.
- The daemon remains the control authority; widget/UI changes should stay limited to surfacing richer backend state and results rather than inventing new client-side policy.
- This is a post-hardening plan for a future server environment only.

## Baseline Expected Before Starting

- `daemon run`, Unix-socket IPC, live action routing, widget action feedback, restored-session read-only behavior, reconnect handling, and cleaned-up architecture/operations docs are already stable.
- `docs/architecture/coding-pet.md` is the source-of-truth baseline for current behavior.
- Current tests for daemon runtime, IPC, widget feedback, adapters, and restored-session behavior are green before future-server changes begin.
- Any future-server work starts as a new track and does not redefine the current-server hardening scope.

## Future-Server Workstreams

### Phase 1: Backend capability contract and plugin registry

Files: `src/coding_pet/models.py`, `src/coding_pet/agents/base.py`, `src/coding_pet/daemon/app.py`, new `src/coding_pet/agents/registry.py`, new `src/coding_pet/agents/plugins/`, `docs/architecture/coding-pet.md`

- Generalize the current adapter surface into a backend plugin/adapter registry instead of a daemon-local switch on `AgentKind`.
- Add a capability model for reply, approve/reject, interrupt/cancel, transcript access, attach/reconnect, and server-owned session metadata.
- Make backend resolution explicit at session start so Claude Code, OpenCode, and internal/server-owned agents all register through the same contract.
- Record backend identity and negotiated capabilities on each session so routing and validation are capability-aware from the start.

### Phase 2: Agent-native control semantics and action lifecycle

Files: `src/coding_pet/daemon/action_router.py`, `src/coding_pet/daemon/manager.py`, `src/coding_pet/daemon/monitor.py`, `src/coding_pet/events.py`, `src/coding_pet/ipc/server.py`, `src/coding_pet/ipc/client.py`, `tests/test_daemon_runtime.py`

- Evolve `send_reply`, `approve`, and `reject` into agent-native operations with action IDs, explicit acknowledgement states, timeout/error surfaces, and unsupported-capability reporting.
- Let adapters return structured action outcomes rather than only generic delivery results, so real backends can distinguish queued, accepted, rejected, ignored, or backend-failed states.
- Keep the daemon as the single policy and correlation point; IPC should carry richer results, not backend-specific transport details.
- Limit UI follow-up to consuming the richer daemon contract rather than embedding backend logic in the widget.

### Phase 3: Transcript and process integration

Files: `src/coding_pet/config.py`, `src/coding_pet/logging.py`, `src/coding_pet/daemon/monitor.py`, `src/coding_pet/state_store.py`, new `src/coding_pet/daemon/transcripts.py` or equivalent, `tests/test_logging.py`, new transcript-focused tests

- Promote transcript capture from a logging toggle into a durable session artifact with redaction, retention policy, and per-session/process linkage.
- Capture enough structure to correlate backend output, daemon-issued actions, timestamps, exit codes, and reconnect/restored-session boundaries.
- Support backends that can expose richer transcripts than raw stdout, including server-owned agents that return message history or approval checkpoints via API.
- Keep transcript capture configurable and safe-by-default for environments that cannot retain full agent output.

### Phase 4: Server-owned and internal backend support

Files: new backend adapters under `src/coding_pet/agents/plugins/`, `src/coding_pet/daemon/app.py`, `src/coding_pet/config.py`, `src/coding_pet/models.py`, `README.md`, `docs/architecture/coding-pet.md`

- Add adapters for backends that are not just local CLI processes, such as company-managed agent runners, internal approval brokers, or server-hosted LLM workers.
- Define a common backend session contract covering launch/start, attach/reconnect, action dispatch, transcript fetch, and capability negotiation.
- Keep Claude Code and OpenCode as first-class reference plugins, but do not hardcode the future design around only those two backends.
- Add configuration for backend discovery, backend-specific credentials/endpoints, and allowlisted capability enablement per server.

### Phase 5: Real-world future-server validation

Files: new `tests/integration/`, new `scripts/validate_real_backends.py` or similar, `docs/operations/` validation runbook, `README.md`

- Add integration tests that use real installed backends where safe, gated behind explicit env flags and disposable workspaces.
- Prefer safe validation prompts: summarize repository state, answer a question about a scratch repo, emit a review summary, or request and answer a benign approval cycle.
- Add server-only validation for capability negotiation, reply/approval semantics, reconnect after daemon restart, transcript capture, and mixed-backend multi-session operation.
- Keep destructive flows, privileged actions, and external network dependencies out of automated validation unless a separate operator-approved harness exists.

## Verification on the Future Server

- Run the current unit and integration suite first, then a gated real-backend suite against installed `claude`, `opencode`, and any available internal backend.
- Prove capability negotiation by starting sessions across different backends and asserting the daemon exposes the correct supported-action set and transcript behavior per session.
- Prove agent-native semantics by exercising reply, approve, and reject on real sessions and checking correlated action outcomes instead of only transport success.
- Prove transcript/process integration by capturing a full session timeline with redaction enabled, daemon restart/reconnect, and restored-session continuity.
- Prove server-owned backend support by attaching at least one non-CLI backend through the same registry and action lifecycle.
- Document the exact future-server validation procedure in `docs/operations/` so it stays separate from the current-server hardening runbook.

## Exit Criteria

- The future server can run at least two real backends end-to-end through the same daemon contract, including Claude Code or OpenCode plus any additional installed/internal backend available on that server.
- Backend registration is plugin/adapter based; adding a new backend does not require editing a hardcoded daemon switch.
- Sessions expose negotiated capabilities, and unsupported actions fail explicitly and predictably.
- Action routing supports agent-native reply/approval semantics with correlated results, not just transport-level acknowledgement.
- Transcript capture is configurable, redacted, and linked to session, process, and action identity.
- A real-backend validation suite and operator runbook exist and pass on the future server.
- This future-server track remains separate from, and does not block, current-server hardening.
