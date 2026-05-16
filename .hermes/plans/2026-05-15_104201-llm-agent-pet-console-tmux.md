# LLM Agent Pet Console tmux 통합 구현 계획

> **For Hermes/Codex:** 구현을 시작할 때는 이 계획을 task-by-task로 실행한다. GUI/daemon/runtime 경계를 건드리므로 `subagent-driven-development` 방식으로 작은 단위 구현 + 테스트 + 리뷰를 반복한다.

**Goal:** 기존 `coding-pet` 구조를 유지하면서, 이미 tmux 안에서 실행 중인 Claude Code/OpenCode pane들을 pet widget으로 표시하고, 상세 팝업에서 transcript를 보고 raw input을 tmux pane으로 그대로 전달하는 사내 LLM Agent Pet Console을 구현한다.

**Architecture:** 기존 process-launch 기반 monitor는 유지하고, 그 옆에 `source_kind="tmux"` 세션 경로를 추가한다. tmux discovery/capture/control은 새 `src/coding_pet/tmux/` 패키지에 격리하고, daemon은 발견된 pane을 `SessionRegistry`에 upsert하며, action router는 기존 live-control envelope를 확장해 tmux raw paste로 라우팅한다. GUI는 PySide6 lazy import/headless fallback 원칙을 유지하면서 detail popup과 transcript view를 추가한다.

**Tech Stack:** Python 3.11, asyncio, pydantic v2, Typer, PySide6 lazy imports, Unix domain socket NDJSON IPC, tmux CLI, stdlib sqlite3 transcript store, systemd user services.

---

## 0. 계획 범위와 금지 사항

이번 문서는 planning-only 산출물이다. 이 계획 파일 외의 소스/테스트/문서는 아직 변경하지 않는다.

구현 시 유지할 원칙:

- 외부 인터넷, 외부 git clone, telemetry 금지.
- Claude Code/OpenCode provider 설정이나 agent 자체 구현 금지.
- Kanban, worktree, Perforce workspace copy, 자동 patch/submit/shelve는 MVP 범위 밖.
- UI는 사용자가 입력한 문자열을 해석하지 않는다. 대상 session을 명확히 표시하고 그대로 tmux buffer paste만 한다.
- 기존 `daemon monitor --cmd` 기반 기능, IPC 메시지, state restore, widget fallback 테스트를 깨지 않는다.
- 현재 개발 서버에는 Claude Code/OpenCode/PySide6 GUI runtime이 없을 수 있으므로 unit/mock/integration 테스트가 1차 검증 경로다. 실제 tmux+agent+GUI smoke는 RHEL 8.10 사내 데스크톱에서 수행한다.

---

## 1. 현재 repo 확인 결과

읽은 주요 파일:

- `README.md`
- `pyproject.toml`
- `docs/architecture/coding-pet.md`
- `docs/operations/rhel8-setup.md`
- `src/coding_pet/models.py`
- `src/coding_pet/events.py`
- `src/coding_pet/config.py`
- `src/coding_pet/cli.py`
- `src/coding_pet/daemon/action_router.py`
- `src/coding_pet/daemon/runtime.py`
- `src/coding_pet/daemon/manager.py`
- `src/coding_pet/daemon/monitor.py`
- `src/coding_pet/daemon/classifier.py`
- `src/coding_pet/daemon/app.py`
- `src/coding_pet/ipc/server.py`
- `src/coding_pet/ipc/client.py`
- `src/coding_pet/gui/app.py`
- `src/coding_pet/gui/widget.py`
- `src/coding_pet/gui/session_panel.py`
- `src/coding_pet/gui/bubble.py`
- `src/coding_pet/gui/theme.py`
- `src/coding_pet/state_store.py`
- representative tests under `tests/`

Important baseline facts:

- Package is Python 3.11+ with `pydantic`, `PySide6`, and `typer` dependencies.
- `AttentionState` currently lacks `NEEDS_CHOICE` and `UNKNOWN`.
- `SessionStatus` currently has only process-monitor fields; it is safe to add optional tmux/transcript fields because pydantic/state restore already tolerates additional optional defaults if model fields are explicit.
- `daemon run` creates `DaemonRuntime`, restores JSON state, starts `IpcServer`, and wires `SessionActionRouter` to `MonitorManager`.
- `SessionActionRequest` currently supports only `send_reply`, `approve`, `reject`, and trims `reply_text` with `.strip()`. This must change for raw pass-through because leading/trailing whitespace and empty-line structure can be meaningful.
- `IpcServer` forwards only `session_id`, `action`, and `reply_text`; it must forward `press_enter`, `state_override`, and transcript request fields.
- `MonitorManager.has_live_session()` currently depends on process monitor tasks. tmux sessions need either a live monitor task or a registered control channel so action routing does not reject them as non-live.
- `OutputClassifier` is line-based and simple. tmux needs snapshot/block classification with Korean and numbered-choice patterns, without using an LLM.
- GUI code already follows a mostly headless-safe pattern, but `detail_popup`, `transcript_view`, `reply_box`, click handlers, and context menu do not exist yet.
- Existing tests already cover daemon runtime action routing, IPC, widget fallback, state mapping, backend availability, and CLI doctor. New work should extend these tests rather than replacing them.

---

## 2. Key design decisions

### 2.1 Keep launch-based monitor and add tmux source path

Do not convert existing process-launch monitoring into tmux monitoring. Add `source_kind` to `SessionStatus`:

- `source_kind="process"` for existing `daemon monitor --cmd` sessions.
- `source_kind="tmux"` for discovered tmux panes.

This keeps existing behavior stable and lets tmux be enabled/disabled independently.

### 2.2 Keep `AgentKind` enum in MVP unless generic agents become required

The sketch suggested `agent_kind: AgentKind | str`. Current code assumes `status.agent_kind.value` in some places. For MVP, discover only Claude Code/OpenCode panes by command/session/title rules and keep `agent_kind: AgentKind` to avoid broad contract breakage.

If generic `agent-*` support becomes required later, prefer adding `AgentKind.UNKNOWN` plus a separate `agent_label: str | None` instead of widening every consumer to arbitrary `str` in the first pass.

### 2.3 Raw input must preserve bytes/text exactly at the Python string boundary

Change action parsing so `reply_text` is not stripped. `send_reply` requires `reply_text is not None`, not `reply_text.strip()`. `send_without_enter` uses the same `reply_text` with `press_enter=False`.

Use tmux buffer flow:

1. write UTF-8 text to a secure temporary file;
2. `tmux load-buffer -b <unique-buffer> <tempfile>`;
3. `tmux paste-buffer -t <pane_id> -b <unique-buffer>`;
4. optionally `tmux send-keys -t <pane_id> Enter`;
5. delete temp file; optionally `tmux delete-buffer -b <unique-buffer>` after paste.

Never use `tmux send-keys "<user text>"` for freeform text.

### 2.4 Tmux liveness/control should reuse daemon-owned action routing

Do not put tmux control strings in widget code. Add a generic live control registration path in `MonitorManager` or an equivalent daemon service so `SessionActionRouter` can validate session existence/liveness and dispatch through a daemon-owned handler.

Recommended minimal change:

- Add `MonitorManager.register_control_channel(session_id, handler)`.
- Add `MonitorManager.unregister_control_channel(session_id)`.
- Update `MonitorManager.has_live_session(session_id)` to return true for process tasks or registered live control channels whose registry status is `live=True`.
- `TmuxMonitorService` registers a handler for each live pane and unregisters it when the pane disappears.

### 2.5 Transcript is a first-class daemon-side store

Use sqlite3 under `~/.local/state/coding-pet/transcripts.sqlite` by default. Store only timestamped event rows, not unbounded repeated full screen snapshots.

Event directions:

- `in`: dashboard input sent to a pane.
- `out`: new tmux output detected by snapshot diff.
- `system`: discovery, state changes, action results, degraded-mode events.

### 2.6 Snapshot diff is bounded and conservative

MVP should not try to reconstruct a perfect terminal scrollback. Use a deterministic suffix/overlap diff:

- normalize capture text with `splitlines()`;
- compute snapshot hash;
- if hash unchanged, update idle/stalled timing only;
- if previous snapshot exists, find the longest suffix of previous lines that is a prefix of current lines, and append only the remaining lines;
- if no overlap, append a bounded tail with a `system` note that the screen changed discontinuously;
- cap event text and event count per session.

### 2.7 GUI remains headless-safe

All pure logic goes in non-Qt modules or dataclasses. `PySide6` imports stay inside setup/runtime methods. Tests must pass on the current constrained host even if `libEGL.so.1` or GUI display support is absent.

### 2.8 Config should support YAML but keep environment overrides

The requested config is YAML-like. Add a small config loader for `~/.config/coding-pet/config.yaml` while keeping current XDG/env behavior. If adding `PyYAML` is acceptable in the internal package mirror, add it to `pyproject.toml`; otherwise, implement env-first MVP and document YAML as a follow-up. Do not silently invent a partial YAML parser.

Recommended dependency change:

- Add `PyYAML>=6,<7` to `[project.dependencies]` only if internal pip can supply it.
- Unit-test config defaults and env overrides without requiring a real user home.

---

## 3. Acceptance criteria

Functional MVP:

1. `coding-pet daemon discover-tmux` lists tmux panes and marks Claude/OpenCode matches.
2. `coding-pet daemon run` can start IPC plus tmux discovery/monitor loop when config enables tmux.
3. Discovered Claude/OpenCode tmux panes appear as one live `SessionStatus` each.
4. Each pane has stable `session_id`, `source_kind="tmux"`, `tmux_pane_id`, `tmux_session_name`, `tmux_window_pane`, `tmux_current_command`, `workspace`, `title`, timestamps, state, summary, and last snippet.
5. State classifier detects at least RUNNING, NEEDS_INPUT, NEEDS_CHOICE, NEEDS_PERMISSION, STALLED, FAILED, COMPLETED/IDLE/UNKNOWN where applicable.
6. Pet bubble shows short state text, not a long log line.
7. Clicking a pet opens a detail popup showing target info, last dashboard input, estimated agent request, recent transcript, and reply box.
8. `Send` preserves raw text and sends Enter after paste.
9. `Send without Enter` preserves raw text and does not send Enter.
10. Korean, multiline text, quotes, `$`, `;`, and `\` are tested through tmux-control command construction and temp-file content.
11. Transcript store persists `in/out/system` events with timestamps and can list recent events per session.
12. Existing process-monitor tests and CLI commands still pass.
13. No implementation path requires local Claude Code/OpenCode binaries on the current constrained server.
14. No external network/git access is introduced.

---

## 4. Files likely to change

Create:

- `src/coding_pet/tmux/__init__.py`
- `src/coding_pet/tmux/client.py`
- `src/coding_pet/tmux/discovery.py`
- `src/coding_pet/tmux/capture.py`
- `src/coding_pet/tmux/control.py`
- `src/coding_pet/tmux/models.py`
- `src/coding_pet/transcripts/__init__.py`
- `src/coding_pet/transcripts/model.py`
- `src/coding_pet/transcripts/store.py`
- `src/coding_pet/classifiers/__init__.py`
- `src/coding_pet/classifiers/agent_state.py`
- `src/coding_pet/classifiers/patterns.py`
- `src/coding_pet/daemon/tmux_discovery_service.py`
- `src/coding_pet/daemon/tmux_monitor.py`
- `src/coding_pet/gui/detail_popup.py`
- `src/coding_pet/gui/transcript_view.py`
- `src/coding_pet/gui/reply_box.py`
- `src/coding_pet/gui/detail_view_model.py`
- `tests/test_tmux_client.py`
- `tests/test_tmux_discovery.py`
- `tests/test_tmux_capture.py`
- `tests/test_tmux_control.py`
- `tests/test_transcript_store.py`
- `tests/test_agent_state_classifier.py`
- `tests/test_tmux_monitor.py`
- `tests/test_detail_popup_view_model.py`

Modify:

- `pyproject.toml` if `PyYAML` is adopted.
- `src/coding_pet/models.py`
- `src/coding_pet/config.py`
- `src/coding_pet/cli.py`
- `src/coding_pet/daemon/action_router.py`
- `src/coding_pet/daemon/manager.py`
- `src/coding_pet/daemon/runtime.py`
- `src/coding_pet/ipc/server.py`
- `src/coding_pet/ipc/client.py`
- `src/coding_pet/gui/app.py`
- `src/coding_pet/gui/widget.py`
- `src/coding_pet/gui/session_panel.py`
- `src/coding_pet/gui/bubble.py`
- `src/coding_pet/gui/theme.py`
- `src/coding_pet/state_store.py` only if restore compatibility needs explicit migration behavior.
- `docs/architecture/coding-pet.md`
- `docs/operations/rhel8-setup.md`
- `README.md`
- `packaging/systemd/coding-pet-daemon.service` only if a new env flag or config path must be documented in the unit.
- Existing tests that assert exact action lists or state enum coverage.

---

## 5. Step-by-step implementation plan

### Task 1: Establish baseline verification

**Objective:** Prove the current checkout is healthy before adding tmux behavior.

**Files:** none expected.

**Steps:**

1. Run targeted baseline tests:
   - `PYTHONPATH=src python -m pytest tests/test_models.py tests/test_state_store.py tests/test_daemon_runtime.py tests/test_ipc.py tests/test_widget_state_mapping.py -q`
2. Run style/type checks if available in the environment:
   - `PYTHONPATH=src python -m ruff check src tests`
   - `PYTHONPATH=src python -m mypy src`
3. Record any pre-existing failures separately. Do not mix unrelated fixes into tmux implementation commits.

**Expected:** Existing tests pass or known constrained-host GUI/backend limitations are explicitly identified.

---

### Task 2: Extend core state/model contract

**Objective:** Add tmux/session-console fields without breaking existing JSON snapshots.

**Files:**

- Modify: `src/coding_pet/models.py`
- Modify tests: `tests/test_models.py`, `tests/test_state_store.py`, `tests/test_widget_state_mapping.py`

**Model changes:**

- Add `AttentionState.NEEDS_CHOICE = "needs_choice"`.
- Add `AttentionState.UNKNOWN = "unknown"` if needed for degraded tmux/capture failure states.
- Update `_ATTENTION_PRIORITY` to match the requested priority order:
  - `UNKNOWN`: 0
  - `IDLE`: 0
  - `RUNNING`: 10
  - `STALLED`: 20
  - `COMPLETED`: 30
  - `REVIEW_NEEDED`: 40
  - `NEEDS_INPUT`: 50
  - `NEEDS_CHOICE`: 55
  - `NEEDS_PERMISSION`: 60
  - `FAILED`: 70
- Add optional/defaulted `SessionStatus` fields:
  - `source_kind: str = "process"`
  - `tmux_pane_id: str | None = None`
  - `tmux_session_name: str | None = None`
  - `tmux_window_pane: str | None = None`
  - `tmux_current_command: str | None = None`
  - `last_activity_at: datetime | None = None`
  - `last_input_at: datetime | None = None`
  - `last_output_at: datetime | None = None`
  - `last_dashboard_input: str | None = None`
  - `estimated_current_request: str | None = None`
  - `agent_waiting_message: str | None = None`
  - `state_reason: str | None = None`
  - `output_hash: str | None = None`

**Tests:**

- Existing minimal `SessionStatus` construction still works.
- Old JSON payload without new fields restores successfully.
- `NEEDS_CHOICE` priority sorts between `NEEDS_INPUT` and `NEEDS_PERMISSION`.
- `UNKNOWN` does not outrank actionable states.

**Validation command:**

- `PYTHONPATH=src python -m pytest tests/test_models.py tests/test_state_store.py tests/test_widget_state_mapping.py -q`

---

### Task 3: Add config objects for tmux, transcript, input, and UI defaults

**Objective:** Represent requested config without hardcoding all settings in daemon/widget code.

**Files:**

- Modify: `src/coding_pet/config.py`
- Modify: `pyproject.toml` only if adopting `PyYAML`
- Modify tests: `tests/test_config.py`

**Implementation notes:**

Add dataclasses under `config.py` or a small sibling module:

- `TmuxConfig`
  - `enabled: bool = False` initially, unless product decision says on-by-default.
  - `poll_interval_ms: int = 1000`
  - `capture_lines: int = 200`
  - `include_session_patterns: list[str] = ["claude-*", "opencode-*", "agent-*"]`
  - `include_commands: list[str] = ["claude", "opencode"]`
  - `exclude_session_patterns: list[str] = []`
- `InputConfig`
  - `send_method: str = "tmux_buffer"`
  - `enter_after_send: bool = True`
- `TranscriptConfig`
  - `enabled: bool = True`
  - `backend: str = "sqlite"`
  - `max_events_per_session: int = 5000`
  - `redact_secrets: bool = False`
  - `db_path: Path = state_dir / "transcripts.sqlite"`
- `TerminalConfig`
  - `attach_command: str | None = None`
- `UiConfig`
  - include pet size/spacing/click behavior defaults.
- `StateDetectionConfig`
  - `stalled_after_sec: int = 300`
  - `waiting_after_idle_sec: int = 5`

Keep current env overrides and add explicit env vars for testability, e.g.:

- `CODING_PET_TMUX_ENABLED`
- `CODING_PET_TMUX_POLL_INTERVAL_MS`
- `CODING_PET_TMUX_CAPTURE_LINES`
- `CODING_PET_TRANSCRIPT_DB`

**Tests:**

- Defaults match expected values.
- Env overrides work without a real config file.
- If YAML is implemented, temp `config.yaml` overrides defaults while env overrides YAML.

**Validation command:**

- `PYTHONPATH=src python -m pytest tests/test_config.py -q`

---

### Task 4: Create tmux models and list-panes parser

**Objective:** Parse tmux pane metadata deterministically without needing a real tmux server in tests.

**Files:**

- Create: `src/coding_pet/tmux/__init__.py`
- Create: `src/coding_pet/tmux/models.py`
- Create: `src/coding_pet/tmux/discovery.py`
- Create tests: `tests/test_tmux_discovery.py`

**Implementation notes:**

Define:

```python
@dataclass(frozen=True, slots=True)
class TmuxPaneInfo:
    pane_id: str
    session_name: str
    window_pane: str
    current_command: str
    current_path: str
    title: str | None = None
```

Parser requirements:

- Accept the requested output shape:
  - `%3|claude-auth|0.0|claude|/proj/ws/auth|claude-auth`
- Split with `maxsplit=5` so titles containing `|` are not catastrophically truncated.
- Reject malformed rows with a typed parse error or return ignored diagnostics, not silent crashes.
- Normalize empty title to `None`.

Discovery matching rules:

- include if `current_command` exactly matches configured include commands;
- or `session_name`/`title` matches include patterns;
- exclude if session matches exclude pattern;
- infer `AgentKind.CLAUDE_CODE` from command/title/session containing `claude`;
- infer `AgentKind.OPENCODE` from command/title/session containing `opencode`;
- if no supported agent kind can be inferred, mark ignored in CLI output for MVP.

**Tests:**

- Valid row parse.
- Empty output returns empty list.
- Malformed row is ignored/reported.
- Claude/OpenCode command matching.
- Session-pattern matching.
- Exclude pattern wins.
- Unknown `bash` pane ignored.

**Validation command:**

- `PYTHONPATH=src python -m pytest tests/test_tmux_discovery.py -q`

---

### Task 5: Implement tmux client command wrapper

**Objective:** Encapsulate `tmux list-panes` and `tmux capture-pane` command construction and errors.

**Files:**

- Create: `src/coding_pet/tmux/client.py`
- Create/modify: `src/coding_pet/tmux/capture.py`
- Create tests: `tests/test_tmux_client.py`, `tests/test_tmux_capture.py`

**Implementation notes:**

- Create a small command runner protocol so tests can inject fake results.
- Use `subprocess.run([...], text=True, capture_output=True, check=False)` in the default sync runner.
- Daemon async loops should call sync client methods through `asyncio.to_thread(...)` to avoid blocking the event loop.
- `list_panes()` command:
  - `tmux list-panes -a -F '#{pane_id}|#{session_name}|#{window_index}.#{pane_index}|#{pane_current_command}|#{pane_current_path}|#{pane_title}'`
- `capture_pane(pane_id, lines)` command:
  - `tmux capture-pane -t <pane_id> -p -J -S -<lines>`
- Provide explicit exceptions/status for:
  - tmux binary missing;
  - tmux server not running;
  - capture target missing;
  - non-zero tmux exit.

**Tests:**

- Command argv is exact.
- Non-zero command result includes stderr in error detail.
- Capture lines are passed as negative `-S` value.
- Missing binary maps to a doctor-friendly unavailable status.

**Validation command:**

- `PYTHONPATH=src python -m pytest tests/test_tmux_client.py tests/test_tmux_capture.py -q`

---

### Task 6: Implement tmux raw input control

**Objective:** Safely paste arbitrary user text into a pane with optional Enter.

**Files:**

- Create: `src/coding_pet/tmux/control.py`
- Create tests: `tests/test_tmux_control.py`

**Implementation notes:**

Add function/class method:

```python
def send_raw_text_to_pane(pane_id: str, text: str, *, press_enter: bool = True) -> None:
    ...
```

Requirements:

- Do not strip `text`.
- Write temp file with UTF-8.
- Use a unique buffer name per call, e.g. `coding-pet-input-<sanitized-pane-id>-<short-uuid>`.
- Run:
  - `tmux load-buffer -b <buffer> <temp_path>`
  - `tmux paste-buffer -t <pane_id> -b <buffer>`
  - optionally `tmux send-keys -t <pane_id> Enter`
  - optionally `tmux delete-buffer -b <buffer>` best-effort.
- Always delete temp file in `finally`.

**Tests:**

- Korean text is written to the temp file unchanged.
- Multiline text is written unchanged.
- Quotes, `$`, `;`, and `\` are not shell-interpreted because argv list is used.
- `press_enter=True` includes `send-keys Enter`.
- `press_enter=False` omits `send-keys Enter`.
- Temp file cleanup occurs on paste failure.

**Validation command:**

- `PYTHONPATH=src python -m pytest tests/test_tmux_control.py -q`

---

### Task 7: Add transcript event model and sqlite store

**Objective:** Persist timestamped input/output/system events per session.

**Files:**

- Create: `src/coding_pet/transcripts/__init__.py`
- Create: `src/coding_pet/transcripts/model.py`
- Create: `src/coding_pet/transcripts/store.py`
- Create tests: `tests/test_transcript_store.py`

**Model:**

```python
class TranscriptEvent(BaseModel):
    event_id: str
    session_id: str
    ts: datetime
    direction: Literal["in", "out", "system"]
    source: Literal["tmux_capture", "dashboard_input", "system"]
    text: str
```

**Store methods:**

- `initialize()`
- `append_event(event)`
- `append(session_id, direction, source, text, ts=None) -> TranscriptEvent`
- `list_recent_events(session_id, limit=100) -> list[TranscriptEvent]`
- `prune_events(session_id, max_events)`

**SQLite schema:**

```sql
CREATE TABLE IF NOT EXISTS transcript_events (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    ts TEXT NOT NULL,
    direction TEXT NOT NULL,
    source TEXT NOT NULL,
    text TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_transcript_session_ts
ON transcript_events(session_id, ts);
```

**Tests:**

- Append/list by session.
- Timestamp ordering.
- UTF-8 Korean text persists.
- Prune keeps newest N events.
- Missing DB parent directory is created.

**Validation command:**

- `PYTHONPATH=src python -m pytest tests/test_transcript_store.py -q`

---

### Task 8: Add rule-based tmux snapshot classifier

**Objective:** Classify screen snapshots/blocks without LLM calls.

**Files:**

- Create: `src/coding_pet/classifiers/__init__.py`
- Create: `src/coding_pet/classifiers/patterns.py`
- Create: `src/coding_pet/classifiers/agent_state.py`
- Create tests: `tests/test_agent_state_classifier.py`
- Optionally keep existing `src/coding_pet/daemon/classifier.py` for process line monitoring unchanged.

**Implementation notes:**

Define pure function/class:

```python
@dataclass(frozen=True, slots=True)
class AgentStateDecision:
    state: AttentionState
    summary: str
    reason: str
    agent_waiting_message: str | None = None
    estimated_current_request: str | None = None
```

Inputs should include:

- current snapshot text;
- previous hash or changed flag;
- `last_output_at`;
- observed time;
- thresholds.

Precedence:

1. `FAILED`
2. `NEEDS_PERMISSION`
3. `NEEDS_CHOICE`
4. `NEEDS_INPUT`
5. `STALLED`
6. `COMPLETED`
7. `RUNNING`
8. `IDLE`
9. `UNKNOWN`

Pattern coverage:

- English running keywords: reading/analyzing/running/generating/executing/searching/fetching/processing.
- English input prompts: Need clarification, Please clarify, What should I, Would you like, Do you want, Can you confirm.
- Korean input prompts: 어떤, 확인해, 계속할까요, 입력해, 알려주세요.
- Choice prompts: Select, Choose, Pick one, `1)`, `2)`, `[1]`, `[2]`, y/n, yes/no, 선택, 번호를 입력.
- Permission prompts: Allow, Approve, permission, Do you want to proceed, Run this command, 실행할까요, 승인, 권한, 허용.
- Failures: Traceback, Exception, Error:, failed, command not found, segmentation fault, permission denied, 오류, 실패.

**Tests:**

- Each requested state has positive examples.
- Korean prompts are classified.
- Numbered choice beats generic input.
- Permission beats generic choice when approval wording exists.
- Failure beats lower-priority states.
- Stalled requires no output change for threshold duration and no waiting/failure/completion pattern.
- Classifier returns concise summary/bubble text source.

**Validation command:**

- `PYTHONPATH=src python -m pytest tests/test_agent_state_classifier.py -q`

---

### Task 9: Add capture diff helper

**Objective:** Convert repeated `capture-pane` snapshots into bounded transcript output events.

**Files:**

- Modify/create: `src/coding_pet/tmux/capture.py`
- Create tests: `tests/test_tmux_capture.py`

**Implementation notes:**

Add pure helper:

```python
def new_output_from_snapshot(previous: str | None, current: str, *, max_initial_lines: int = 50) -> str:
    ...
```

Behavior:

- If `previous is None`, return bounded tail of current or empty depending on config. Recommended: append last 50 lines as initial context with a system marker.
- If hashes equal, return empty string.
- Use longest suffix/prefix overlap to find new lines.
- If no overlap, return bounded tail and mark discontinuity in caller as `system` event.

**Tests:**

- Simple appended line.
- Wrapped/unchanged snapshot returns empty.
- Discontinuous snapshot is bounded.
- Empty current snapshot handled.

**Validation command:**

- `PYTHONPATH=src python -m pytest tests/test_tmux_capture.py -q`

---

### Task 10: Generalize live control registration in MonitorManager

**Objective:** Let tmux sessions be live/actionable without being launched subprocess monitor tasks.

**Files:**

- Modify: `src/coding_pet/daemon/manager.py`
- Modify tests: `tests/test_daemon_runtime.py`, maybe new `tests/test_tmux_monitor.py`

**Implementation notes:**

Add methods:

```python
def register_control_channel(self, session_id: str, handler: ActionHandler) -> None: ...
def unregister_control_channel(self, session_id: str) -> None: ...
```

Update:

- `start_session()` uses `register_control_channel()` instead of writing `_action_handlers` directly.
- `stop_session()` unregisters.
- `has_live_session()` returns true if:
  - process task exists and not done; or
  - control handler exists and registry status exists with `live=True`.
- `route_action()` keeps existing structured failure behavior.

**Tests:**

- Existing process-action tests still pass.
- Registered control channel makes a non-process session live.
- Unregistering makes it non-live or no-control.
- Missing session still returns `session_not_found` through action router.

**Validation command:**

- `PYTHONPATH=src python -m pytest tests/test_daemon_runtime.py -q`

---

### Task 11: Implement tmux discovery service

**Objective:** Periodically discover panes and upsert/remove live tmux session status.

**Files:**

- Create: `src/coding_pet/daemon/tmux_discovery_service.py`
- Modify: `src/coding_pet/daemon/runtime.py`
- Create tests: `tests/test_tmux_monitor.py` or `tests/test_tmux_discovery_service.py`

**Implementation notes:**

Service responsibilities:

- Poll `TmuxClient.list_panes()` at configured interval.
- Apply include/exclude rules.
- For each matched pane, create/update `SessionStatus` with:
  - `session_id=f"tmux-{pane_id}"`, e.g. `tmux-%3`;
  - `source_kind="tmux"`;
  - `agent_kind` inferred from pane;
  - `title` from title/session;
  - `workspace` from current path;
  - `state=RUNNING` or previous state;
  - tmux metadata fields;
  - `live=True`.
- Register a control channel for each matched pane that routes to tmux control.
- When a pane disappears, unregister control channel and either:
  - set `live=False`, `state=UNKNOWN`, `summary="tmux pane disappeared"`; or
  - emit `session_removed` after a small grace period.

Recommended MVP behavior: mark `live=False` first so restored/transcript context remains visible; add remove/prune later if needed.

**Tests:**

- Discovery upserts two matched panes.
- Unknown shell pane ignored.
- Disappeared pane marked not live and control channel removed.
- Existing status fields like `last_dashboard_input` are preserved on rediscovery.

**Validation command:**

- `PYTHONPATH=src python -m pytest tests/test_tmux_monitor.py -q`

---

### Task 12: Implement tmux pane monitor service

**Objective:** Capture screen snapshots, update transcript, classify state, and broadcast registry updates.

**Files:**

- Create: `src/coding_pet/daemon/tmux_monitor.py`
- Modify: `src/coding_pet/daemon/runtime.py`
- Create tests: `tests/test_tmux_monitor.py`

**Implementation notes:**

Service responsibilities:

- Track per-session previous snapshot/hash and timestamps.
- For each live tmux pane, call `capture_pane(pane_id, capture_lines)`.
- Use Task 9 diff helper to append only new `out` transcript events.
- Use Task 8 classifier to decide state and state_reason.
- Update `SessionStatus` fields:
  - `state`
  - `summary`
  - `last_event_at`
  - `last_activity_at`
  - `last_output_at`
  - `last_output_snippet`
  - `estimated_current_request`
  - `agent_waiting_message`
  - `state_reason`
  - `output_hash`
  - `unread` when state becomes actionable or output changed.
- On capture failure, set `state=UNKNOWN` or `STALLED` with explicit `state_reason`, not `FAILED` unless tmux reports target failure.

**Tests:**

- First capture creates status snippet and bounded transcript context.
- Changed capture appends only new text.
- No change for `stalled_after_sec` sets `STALLED`.
- Question screen sets `NEEDS_INPUT` and extracts request.
- Choice screen sets `NEEDS_CHOICE`.
- Permission screen sets `NEEDS_PERMISSION`.
- Capture error degrades without crashing daemon.

**Validation command:**

- `PYTHONPATH=src python -m pytest tests/test_tmux_monitor.py tests/test_transcript_store.py tests/test_agent_state_classifier.py -q`

---

### Task 13: Wire tmux services into DaemonRuntime

**Objective:** `coding-pet daemon run` starts tmux discovery/monitor when enabled, while keeping process monitor behavior intact.

**Files:**

- Modify: `src/coding_pet/daemon/runtime.py`
- Modify: `src/coding_pet/cli.py`
- Modify tests: `tests/test_daemon_runtime.py`, `tests/test_cli.py`

**Implementation notes:**

- Add optional fields to `DaemonRuntime` for tmux config, tmux client, transcript store, and service tasks.
- In `start()`:
  - initialize transcript store if enabled;
  - start IPC server as before;
  - if `tmux.enabled`, start discovery/monitor background tasks.
- In `stop()`:
  - cancel tmux tasks cleanly;
  - persist snapshot;
  - stop IPC server.
- Ensure `CODING_PET_DAEMON_ONESHOT=1` exits cleanly without requiring tmux server.
- If tmux is unavailable, daemon should log/degrade and doctor should report it; do not crash unless a command explicitly requires tmux.

**Tests:**

- Runtime oneshot still works with tmux disabled.
- Runtime starts fake tmux service when enabled.
- Runtime stops tmux tasks cleanly.
- No local Claude/OpenCode backend is required for tmux-enabled runtime tests.

**Validation command:**

- `PYTHONPATH=src python -m pytest tests/test_daemon_runtime.py tests/test_cli.py -q`

---

### Task 14: Extend action request schema and IPC forwarding

**Objective:** Support raw `send_reply`, `send_without_enter`, attach, mark-read, and manual state override through one action envelope.

**Files:**

- Modify: `src/coding_pet/daemon/action_router.py`
- Modify: `src/coding_pet/ipc/server.py`
- Modify: `src/coding_pet/ipc/client.py` if convenience methods are added.
- Modify: `src/coding_pet/gui/app.py`
- Modify tests: `tests/test_daemon_runtime.py`, `tests/test_ipc.py`, `tests/test_reply_actions.py`, `tests/test_widget_action_feedback.py`

**Implementation notes:**

Extend action literal carefully:

- `send_reply`
- `send_without_enter`
- existing `approve`
- existing `reject`
- `attach`
- `mark_read`
- `hide_pet`
- `manual_state_override`

Add request fields:

- `reply_text: str | None`
- `press_enter: bool = True`
- `state_override: AttentionState | None = None`

Parsing rules:

- Do not strip `reply_text`.
- `send_reply` requires `reply_text is not None`, sets `press_enter=True` unless provided.
- `send_without_enter` requires `reply_text is not None`, sets `press_enter=False` regardless of default.
- `manual_state_override` requires valid `state_override`.
- Unknown actions still return structured `unsupported_action`.
- IPC server forwards `press_enter` and `state_override` fields.

**Tests:**

- Leading/trailing whitespace is preserved.
- Multiline text is preserved through IPC payload.
- `send_without_enter` reaches daemon with `press_enter=False`.
- Existing approve/reject tests still pass.
- Malformed action requests have stable failure reasons.

**Validation command:**

- `PYTHONPATH=src python -m pytest tests/test_daemon_runtime.py tests/test_ipc.py tests/test_reply_actions.py tests/test_widget_action_feedback.py -q`

---

### Task 15: Implement tmux action handler

**Objective:** Deliver dashboard input to the target tmux pane and persist the input transcript.

**Files:**

- Modify: `src/coding_pet/daemon/tmux_monitor.py` or `src/coding_pet/daemon/tmux_discovery_service.py`
- Modify: `src/coding_pet/daemon/manager.py` if routing detail needs to distinguish handler return values.
- Modify tests: `tests/test_tmux_monitor.py`, `tests/test_tmux_control.py`, `tests/test_daemon_runtime.py`

**Implementation notes:**

The registered tmux control handler should:

1. Resolve `session_id` to current pane metadata.
2. For `send_reply` / `send_without_enter`:
   - append transcript `direction="in"`, `source="dashboard_input"`, text exactly as supplied;
   - call `send_raw_text_to_pane(pane_id, reply_text, press_enter=request.press_enter)`;
   - update `SessionStatus.last_dashboard_input`, `last_input_at`, `last_activity_at`, `state=RUNNING`, `summary="Input sent"` or short localized equivalent.
3. For `attach`:
   - return or display `tmux attach -t <session_name>` / configured terminal command;
   - do not silently execute unsafe shell strings unless configured and tested.
4. For `mark_read`:
   - call registry mark-read behavior.
5. For `manual_state_override`:
   - update state and state_reason with system transcript event.

If `MonitorManager.route_action()` currently assumes handlers return `None`, either keep handler side effects and manager builds generic success, or evolve handler return type to include richer `ActionResult`. Choose one path and test it. Recommended: allow optional handler result so tmux attach can return `detail` with attach command.

**Tests:**

- Raw input action calls tmux control with exact pane id/text/press_enter.
- Transcript `in` event is created before or after successful paste according to chosen semantics; if paste fails, record `system` failure event.
- Pane disappearance returns structured failure.
- Attach returns target command detail.

**Validation command:**

- `PYTHONPATH=src python -m pytest tests/test_tmux_monitor.py tests/test_tmux_control.py tests/test_daemon_runtime.py -q`

---

### Task 16: Add transcript IPC messages

**Objective:** Let detail popup request recent transcript and receive appended events.

**Files:**

- Modify: `src/coding_pet/ipc/server.py`
- Modify: `src/coding_pet/gui/app.py`
- Create/modify tests: `tests/test_ipc.py`, `tests/test_widget_integration.py`

**Message types:**

Client request:

```json
{"type":"transcript_request","session_id":"tmux-%3","limit":100}
```

Server response:

```json
{"type":"transcript_snapshot","session_id":"tmux-%3","events":[...]}
```

Broadcast on append:

```json
{"type":"transcript_appended","session_id":"tmux-%3","event":{...}}
```

**Implementation notes:**

- Add optional transcript store dependency to `IpcServer`.
- If transcript is disabled/unavailable, respond with empty snapshot plus `ok=false`/reason or a system event; pick a stable contract and test it.
- Keep `snapshot` and `session_updated` behavior unchanged.

**Tests:**

- Client can request transcript snapshot.
- Appended transcript event is broadcast to connected clients.
- Transcript disabled returns structured degraded response.

**Validation command:**

- `PYTHONPATH=src python -m pytest tests/test_ipc.py tests/test_widget_integration.py -q`

---

### Task 17: Add CLI commands and doctor diagnostics

**Objective:** Expose tmux discovery/manual monitoring and make environment issues visible.

**Files:**

- Modify: `src/coding_pet/cli.py`
- Modify tests: `tests/test_cli.py`
- Modify docs later in Task 21.

**Commands:**

- `coding-pet daemon discover-tmux`
  - Lists pane id, session name, command, cwd, and matched/ignored reason.
  - Does not mutate daemon state.
- `coding-pet daemon monitor-tmux --pane %3 --agent claude_code --title auth-fix`
  - Manually creates/monitors one pane in a foreground daemon-app-like flow or instructs the running daemon depending on existing CLI architecture.
  - MVP can implement discovery output first and defer manual foreground monitor if runtime-only monitoring covers the need.
- `coding-pet admin doctor`
  - add `tmux_binary=...`;
  - add `tmux_server=available|unavailable:<reason>`;
  - add `transcript_db=... writable_parent=...`;
  - add `attach_terminal=...` if configured.

**Tests:**

- `discover-tmux` with fake client prints matched and ignored rows.
- Missing tmux produces exit code 1 for explicit `discover-tmux`, but daemon run degrades if tmux is optional.
- Doctor reports tmux status without requiring tmux server in tests.

**Validation command:**

- `PYTHONPATH=src python -m pytest tests/test_cli.py -q`

---

### Task 18: Update bubble/mood/state presentation logic

**Objective:** Show short user-facing labels for tmux session states.

**Files:**

- Modify: `src/coding_pet/gui/bubble.py`
- Modify: `src/coding_pet/gui/theme.py`
- Modify: `src/coding_pet/gui/session_panel.py`
- Modify tests: `tests/test_widget_state_mapping.py`

**Implementation notes:**

- Add mood mapping for `NEEDS_CHOICE` to thinking/question or alert-equivalent. If no new sprite exists, use existing `THINKING` or `ALERT` fallback.
- Add `UNKNOWN` fallback.
- For pet bubble, prefer short state labels over raw summary for known states:
  - RUNNING: `작업 중...`
  - NEEDS_INPUT: `입력 필요`
  - NEEDS_CHOICE: `선택 필요`
  - NEEDS_PERMISSION: `승인 필요`
  - FAILED: `오류 발생`
  - COMPLETED: `완료됨`
  - STALLED: `멈춘 듯함`
  - IDLE: `대기 중`
  - UNKNOWN: `상태 확인 필요`
- Keep truncation behavior for custom summaries where appropriate.
- `SessionPanelViewModel.actions_for()` should include `SEND_REPLY` for `NEEDS_CHOICE` as well as `NEEDS_INPUT`, and tmux-specific attach/open-detail behavior should not leak agent control details into UI.

**Tests:**

- Every `AttentionState` has mood and bubble text.
- `NEEDS_CHOICE` actions include reply/send.
- Restored/non-live sessions remain read-only.

**Validation command:**

- `PYTHONPATH=src python -m pytest tests/test_widget_state_mapping.py -q`

---

### Task 19: Add detail popup view model and headless-safe tests

**Objective:** Define detail popup data without requiring PySide6 runtime.

**Files:**

- Create: `src/coding_pet/gui/detail_view_model.py`
- Create tests: `tests/test_detail_popup_view_model.py`

**Implementation notes:**

Define pure dataclasses/functions for:

- header fields:
  - agent kind;
  - title;
  - state badge;
  - cwd;
  - tmux target;
  - last activity;
- last input text;
- agent request text;
- transcript rows with timestamp/direction/source/text;
- send target safety label.

**Tests:**

- Tmux target label includes session name, pane id, and cwd.
- Missing tmux fields degrade gracefully for process sessions.
- Last dashboard input and agent waiting message are displayed separately.
- Transcript rows preserve Korean text.

**Validation command:**

- `PYTHONPATH=src python -m pytest tests/test_detail_popup_view_model.py -q`

---

### Task 20: Implement PySide6 detail popup, transcript view, and reply box

**Objective:** Provide the click-through UI for session inspection and raw input.

**Files:**

- Create: `src/coding_pet/gui/detail_popup.py`
- Create: `src/coding_pet/gui/transcript_view.py`
- Create: `src/coding_pet/gui/reply_box.py`
- Modify: `src/coding_pet/gui/widget.py`
- Modify: `src/coding_pet/gui/app.py`
- Modify tests: `tests/test_widget_integration.py`, `tests/test_reply_actions.py`

**Implementation notes:**

- Keep Qt imports inside setup methods.
- `CodingPetWidgetShell` should accept callbacks or app reference for:
  - open detail;
  - send action;
  - request transcript;
  - attach.
- Left click opens detail popup instead of only marking read.
- Detail popup sections:
  - Header
  - Last Input
  - Agent Request
  - Transcript View
  - Reply Box
  - Actions
- Reply box behavior:
  - Ctrl+Enter: `send_reply` with `press_enter=True`
  - Shift+Enter: newline
  - Send button: same as Ctrl+Enter
  - Send without Enter button: `send_without_enter`, `press_enter=False`
- Display target safety label near Send:
  - agent name, session name, cwd, pane id.
- Full Log button can initially show a larger transcript window or request more events from IPC.

**Tests:**

- Headless fallback can call `open_detail_panel()` and records target session.
- `send_reply` action emitted with raw text and `press_enter=True`.
- `send_without_enter` action emitted with raw text and `press_enter=False`.
- Action result feedback still works.

**Validation command:**

- `PYTHONPATH=src python -m pytest tests/test_widget_integration.py tests/test_reply_actions.py tests/test_widget_action_feedback.py tests/test_detail_popup_view_model.py -q`

---

### Task 21: Add widget context menu and attach behavior

**Objective:** Provide right-click operations and safe tmux attach affordance.

**Files:**

- Modify: `src/coding_pet/gui/widget.py`
- Modify: `src/coding_pet/gui/app.py`
- Modify: `src/coding_pet/gui/session_panel.py`
- Modify tests: `tests/test_widget_state_mapping.py`, `tests/test_widget_integration.py`

**Context menu actions:**

- Open Detail
- Attach tmux
- Mark as Read
- Mark as Waiting / Manual state override to `NEEDS_INPUT`
- Mark as Running / Manual state override to `RUNNING`
- Hide This Pet
- Settings placeholder

**Attach behavior:**

MVP safest behavior:

- Send `attach` action to daemon.
- Daemon returns command detail, e.g. `tmux attach -t claude-auth`.
- Widget displays/copies/shows the command, or executes configured `terminal.attach_command` only if explicitly configured.

Avoid arbitrary shell execution by default.

**Tests:**

- Context menu action list depends on live/source state.
- Attach action request includes target session id.
- Manual override action includes `state_override`.

**Validation command:**

- `PYTHONPATH=src python -m pytest tests/test_widget_integration.py tests/test_widget_state_mapping.py -q`

---

### Task 22: Update docs, README, and systemd notes

**Objective:** Make operations and architecture truthful for tmux-console behavior.

**Files:**

- Modify: `README.md`
- Modify: `docs/architecture/coding-pet.md`
- Modify: `docs/operations/rhel8-setup.md`
- Modify: `packaging/systemd/coding-pet-daemon.service` only if required.

**Documentation updates:**

- Explain two monitoring sources:
  - process-launch monitor;
  - tmux existing-session monitor.
- Add sample tmux commands:
  - `tmux new-session -d -s claude-auth -c /proj/ws/auth 'claude'`
  - `tmux new-session -d -s opencode-build -c /proj/ws/build 'opencode'`
- Add config example for tmux/transcript/input/UI.
- Add transcript storage path and security note.
- Add no-external-network guarantee.
- Add current-server validation note:
  - local Claude/OpenCode not required for mocked tests;
  - real GUI/agent manual smoke must run on RHEL GUI host.
- Add troubleshooting for tmux missing, no tmux server, capture failure, paste failure, transcript DB unwritable.

**Validation command:**

- `PYTHONPATH=src python -m pytest tests/test_cli.py -q`
- If markdown lint exists later, run it; none is currently configured.

---

### Task 23: Full validation pass

**Objective:** Prove all existing and new behavior works in the constrained development environment.

**Commands:**

- `PYTHONPATH=src python -m pytest -q`
- `PYTHONPATH=src python -m ruff check src tests`
- `PYTHONPATH=src python -m mypy src`
- `CODING_PET_DAEMON_ONESHOT=1 CODING_PET_TMUX_ENABLED=0 PYTHONPATH=src python -m coding_pet.cli daemon run`
- `PYTHONPATH=src python -m coding_pet.cli admin doctor`
- `PYTHONPATH=src python -m coding_pet.cli daemon discover-tmux` on a host with tmux, or a documented expected failure if no tmux server exists.

Expected constrained-host result:

- Unit tests pass with fake tmux clients.
- Doctor reports tmux availability honestly.
- Daemon oneshot still exits cleanly.
- Widget still degrades gracefully if PySide6 GUI runtime is unavailable.

---

### Task 24: Manual smoke test on target RHEL GUI host

**Objective:** Verify the real desktop/tmux path end-to-end.

**Preconditions:**

- RHEL 8.10-like desktop host.
- Python package installed from internal mirror.
- tmux installed.
- Claude Code/OpenCode available and configured against internal OpenAI-compatible API.
- No external internet required.

**Smoke commands:**

```bash
tmux new-session -d -s claude-test -c /tmp 'claude'
tmux new-session -d -s opencode-test -c /tmp 'opencode'

CODING_PET_TMUX_ENABLED=1 coding-pet daemon run
coding-pet widget run
```

Manual checks:

- Two pets appear.
- Bubble text reflects running/waiting state.
- Clicking pet opens detail popup.
- Popup shows cwd, session name, pane id, last activity.
- Transcript rows receive timestamps.
- Korean input sends correctly.
- Multiline input sends correctly.
- Quotes, `$`, `;`, and `\` send correctly.
- Send without Enter pastes but does not submit.
- Send submits with Enter.
- Attach affordance shows or opens correct tmux session.
- Pane disappearance marks session not live or removes it according to implemented policy.

---

## 6. Testing matrix

Unit tests:

- `tests/test_tmux_discovery.py`
- `tests/test_tmux_client.py`
- `tests/test_tmux_capture.py`
- `tests/test_tmux_control.py`
- `tests/test_agent_state_classifier.py`
- `tests/test_transcript_store.py`
- `tests/test_detail_popup_view_model.py`
- Existing `tests/test_models.py`, `tests/test_config.py`, `tests/test_state_store.py`, `tests/test_widget_state_mapping.py`

Integration tests:

- `tests/test_tmux_monitor.py`
- `tests/test_daemon_runtime.py`
- `tests/test_ipc.py`
- `tests/test_widget_integration.py`
- `tests/test_reply_actions.py`
- `tests/test_widget_action_feedback.py`

Full validation:

```bash
PYTHONPATH=src python -m pytest -q
PYTHONPATH=src python -m ruff check src tests
PYTHONPATH=src python -m mypy src
```

Manual validation:

- RHEL GUI host tmux + real Claude/OpenCode smoke from Task 24.

---

## 7. Risks and mitigations

### Risk: tmux `pane_current_command` may show `bash` instead of `claude`/`opencode`

Mitigation:

- Match session name and pane title as well as command.
- Provide `monitor-tmux --pane --agent` manual override.
- Document recommended session names: `claude-*`, `opencode-*`.

### Risk: Terminal snapshot diff can miss edits or duplicate output

Mitigation:

- Use bounded transcript events and clear discontinuity system markers.
- Keep `last_output_snippet` as current screen tail even when transcript diff is imperfect.
- Do not claim transcript is a perfect tty recording.

### Risk: Raw paste can send to wrong pane

Mitigation:

- Detail popup must display agent name, session name, cwd, and pane id near Send.
- Action result detail includes pane id.
- Optional confirmation can be added later for high-risk states, but MVP should not interrupt normal send flow.

### Risk: `.strip()` or UI normalization corrupts raw input

Mitigation:

- Tests explicitly cover leading/trailing whitespace, multiline, Korean, quotes, `$`, `;`, and `\`.
- Action parser must not trim `reply_text`.
- Reply box must pass text exactly as entered.

### Risk: PySide6 GUI runtime unavailable in CI/current server

Mitigation:

- Keep Qt imports lazy.
- Put view-model logic in pure Python.
- Headless fallback tests remain the primary CI signal.
- Manual GUI smoke is required on target host.

### Risk: YAML dependency unavailable in internal mirror

Mitigation:

- Keep env/default config working without YAML.
- If PyYAML cannot be added, document YAML config as follow-up and expose env vars for MVP.

### Risk: Transcript stores sensitive code/secrets

Mitigation:

- Document path clearly.
- Provide `transcript.enabled=false`.
- Enforce max events per session.
- Keep `redact_secrets=false` explicit in MVP and mark robust redaction as future work.

---

## 8. Open questions before or during implementation

1. Should tmux monitoring be enabled by default in `daemon run`, or only when `CODING_PET_TMUX_ENABLED=1` / config enables it?
   - Recommended default for first landing: disabled unless enabled, to avoid surprising existing users.
2. Should pane disappearance remove the pet immediately or mark it `live=false` for transcript review?
   - Recommended default: mark `live=false` first; add prune/remove config later.
3. Should `attach` execute a configured terminal command or only show/copy the attach command?
   - Recommended default: show/copy command; execute only when `terminal.attach_command` is configured.
4. Is adding `PyYAML` acceptable in the internal package environment?
   - Recommended: add if available; otherwise env-first MVP.
5. Should generic non-Claude/OpenCode panes be supported in MVP?
   - Recommended: no; discover only Claude/OpenCode for stable `AgentKind` compatibility.

---

## 9. Recommended delivery order

1. Model/config contract.
2. tmux parser/client/control pure modules.
3. transcript store.
4. classifier and capture diff.
5. daemon live-control registration plus tmux discovery/monitor services.
6. action schema/IP pushed through IPC.
7. CLI/doctor.
8. GUI detail popup and context actions.
9. docs and full validation.
10. target-host manual smoke.

This order keeps the riskiest terminal-control behavior covered by unit tests before it reaches daemon/UI integration.
