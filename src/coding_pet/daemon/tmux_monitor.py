from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from coding_pet.classifiers.agent_state import AgentStateClassifier
from coding_pet.config import TmuxConfig
from coding_pet.daemon.action_router import ActionResult, SessionActionRequest, failure_result
from coding_pet.daemon.manager import MonitorManager
from coding_pet.daemon.session_registry import SessionRegistry
from coding_pet.models import AttentionState, SessionStatus, attention_priority
from coding_pet.tmux.capture import new_output_from_snapshot, snapshot_hash
from coding_pet.tmux.client import TmuxClient
from coding_pet.tmux.control import send_raw_text_to_tmux_pane
from coding_pet.tmux.discovery import discover_agent_panes
from coding_pet.tmux.models import MatchedTmuxPane, TmuxPaneInfo
from coding_pet.transcripts.model import TranscriptDirection, TranscriptEvent, TranscriptSource
from coding_pet.transcripts.store import TranscriptStore

TranscriptEventCallback = Callable[[TranscriptEvent], Awaitable[None]]


def session_id_for_pane(pane: TmuxPaneInfo) -> str:
    return f"tmux-{pane.pane_id}"


@dataclass(slots=True)
class _PaneState:
    pane: TmuxPaneInfo
    previous_snapshot: str | None = None


@dataclass(slots=True)
class TmuxMonitorService:
    registry: SessionRegistry
    manager: MonitorManager
    client: TmuxClient
    transcript_store: TranscriptStore | None
    config: TmuxConfig
    stalled_after: timedelta = timedelta(seconds=300)
    on_transcript_event: TranscriptEventCallback | None = None
    classifier: AgentStateClassifier = field(init=False)
    _pane_states: dict[str, _PaneState] = field(default_factory=dict)
    _known_tmux_sessions: set[str] = field(default_factory=set)
    _task: asyncio.Task[None] | None = None

    def __post_init__(self) -> None:
        self.classifier = AgentStateClassifier(stalled_after=self.stalled_after)

    def build_action_request(
        self,
        session_id: str,
        action: str,
        reply_text: str | None = None,
        *,
        press_enter: bool = True,
    ) -> SessionActionRequest:
        payload: dict[str, object] = {
            "type": "action_request",
            "session_id": session_id,
            "action": action,
            "press_enter": press_enter,
        }
        if reply_text is not None:
            payload["reply_text"] = reply_text
        return SessionActionRequest.from_message(payload)

    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._task = asyncio.create_task(self.run())

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    async def run(self) -> None:
        while True:
            try:
                await self.poll_once()
            except Exception:
                # tmux is optional; keep the daemon alive in degraded mode.
                pass
            await asyncio.sleep(self.config.poll_interval_ms / 1000)

    async def poll_once(self) -> None:
        panes = await asyncio.to_thread(self.client.list_panes)
        discovery = discover_agent_panes(panes, config=self.config)
        current_session_ids: set[str] = set()
        for matched in discovery.matched:
            session_id = session_id_for_pane(matched.pane)
            current_session_ids.add(session_id)
            await self._upsert_matched_pane(matched)

        disappeared = self._known_tmux_sessions - current_session_ids
        for session_id in disappeared:
            await self._mark_disappeared(session_id)
        self._known_tmux_sessions = current_session_ids

    async def _upsert_matched_pane(self, matched: MatchedTmuxPane) -> None:
        pane = matched.pane
        session_id = session_id_for_pane(pane)
        now = datetime.now(UTC)
        current_status = await self.registry.get(session_id)
        state = self._pane_states.setdefault(session_id, _PaneState(pane=pane))
        state.pane = pane
        previous_snapshot = state.previous_snapshot
        previous_hash = current_status.output_hash if current_status is not None else None
        snapshot = await asyncio.to_thread(
            self.client.capture_pane,
            pane.pane_id,
            lines=self.config.capture_lines,
        )
        current_hash = snapshot_hash(snapshot)
        snapshot_changed = previous_hash != current_hash
        if (
            previous_snapshot is None
            and current_status is not None
            and current_status.output_hash == current_hash
        ):
            new_output = ""
        else:
            new_output = new_output_from_snapshot(previous_snapshot, snapshot)
        state.previous_snapshot = snapshot
        if new_output and self.transcript_store is not None:
            await self._append_transcript_event(
                session_id=session_id,
                direction="out",
                source="tmux_capture",
                text=new_output,
                ts=now,
            )
            await self.transcript_store.prune_events(
                session_id,
                max_events=self.config.capture_lines * 25,
            )

        last_output_at = (
            now
            if snapshot_changed or current_status is None
            else current_status.last_output_at or current_status.last_event_at
        )
        decision = self.classifier.classify_snapshot(
            snapshot,
            snapshot_changed=snapshot_changed,
            last_output_at=last_output_at,
            observed_at=now,
        )
        snippet = self._snippet(new_output or snapshot)
        title = pane.title or pane.session_name
        updated = SessionStatus(
            session_id=session_id,
            agent_kind=matched.agent_kind,
            title=title,
            workspace=pane.current_path,
            state=decision.state,
            summary=decision.summary,
            last_event_at=now,
            last_output_snippet=snippet,
            attention_score=attention_priority(decision.state),
            unread=self._next_unread(current_status, decision.state, new_output),
            live=True,
            source_kind="tmux",
            tmux_pane_id=pane.pane_id,
            tmux_session_name=pane.session_name,
            tmux_window_pane=pane.window_pane,
            tmux_current_command=pane.current_command,
            last_activity_at=(
                now
                if snapshot_changed
                else current_status.last_activity_at
                if current_status
                else now
            ),
            last_input_at=current_status.last_input_at if current_status else None,
            last_output_at=last_output_at,
            last_dashboard_input=current_status.last_dashboard_input if current_status else None,
            estimated_current_request=decision.estimated_current_request,
            agent_waiting_message=decision.agent_waiting_message,
            state_reason=decision.reason,
            output_hash=current_hash,
        )
        await self.registry.upsert(updated)
        self.manager.register_control_channel(session_id, self._handle_action)

    async def _mark_disappeared(self, session_id: str) -> None:
        self.manager.unregister_control_channel(session_id)
        current = await self.registry.get(session_id)
        if current is None:
            return
        now = datetime.now(UTC)
        await self.registry.upsert(
            current.model_copy(
                update={
                    "live": False,
                    "state": AttentionState.UNKNOWN,
                    "summary": "tmux pane disappeared",
                    "last_event_at": now,
                    "state_reason": "pane_disappeared",
                    "attention_score": attention_priority(AttentionState.UNKNOWN),
                }
            )
        )

    async def _handle_action(self, request: SessionActionRequest) -> ActionResult | None:
        current = await self.registry.get(request.session_id)
        if current is None or current.tmux_pane_id is None:
            return failure_result(
                session_id=request.session_id,
                action=request.action,
                reason="tmux_target_missing",
                detail="tmux pane target is missing",
            )
        if request.action in {"send_reply", "send_without_enter"}:
            return await self._send_input(request, current)
        if request.action == "attach":
            target = current.tmux_session_name or current.tmux_pane_id
            return {
                "type": "action_result",
                "session_id": request.session_id,
                "action": request.action,
                "ok": True,
                "reason": "attach_command",
                "detail": f"tmux attach -t {target}",
            }
        if request.action == "mark_read":
            await self.registry.mark_read(request.session_id)
            return {
                "type": "action_result",
                "session_id": request.session_id,
                "action": request.action,
                "ok": True,
                "reason": "marked_read",
                "detail": "session marked read",
            }
        if request.action == "manual_state_override" and request.state_override is not None:
            updated = current.model_copy(
                update={
                    "state": request.state_override,
                    "summary": f"Manual state: {request.state_override.value}",
                    "state_reason": "manual_state_override",
                    "attention_score": attention_priority(request.state_override),
                    "last_event_at": datetime.now(UTC),
                }
            )
            await self.registry.upsert(updated)
            return {
                "type": "action_result",
                "session_id": request.session_id,
                "action": request.action,
                "ok": True,
                "reason": "state_overridden",
                "detail": f"state set to {request.state_override.value}",
            }
        return failure_result(
            session_id=request.session_id,
            action=request.action,
            reason="unsupported_action",
            detail=f"{request.action} is not supported for tmux sessions",
        )

    async def _send_input(
        self,
        request: SessionActionRequest,
        current: SessionStatus,
    ) -> ActionResult:
        assert current.tmux_pane_id is not None
        text = request.reply_text or ""
        now = datetime.now(UTC)
        if self.transcript_store is not None:
            await self._append_transcript_event(
                session_id=request.session_id,
                direction="in",
                source="dashboard_input",
                text=text,
                ts=now,
            )
        try:
            await asyncio.to_thread(
                send_raw_text_to_tmux_pane,
                current.tmux_pane_id,
                text,
                press_enter=request.press_enter,
                client=self.client,
            )
        except Exception as exc:
            if self.transcript_store is not None:
                await self._append_transcript_event(
                    session_id=request.session_id,
                    direction="system",
                    source="system",
                    text=f"paste failed: {exc}",
                    ts=datetime.now(UTC),
                )
            return failure_result(
                session_id=request.session_id,
                action=request.action,
                reason="tmux_paste_failed",
                detail=str(exc),
            )
        updated = current.model_copy(
            update={
                "state": AttentionState.RUNNING,
                "summary": "Input sent",
                "last_dashboard_input": text,
                "last_input_at": now,
                "last_activity_at": now,
                "last_event_at": now,
                "state_reason": "dashboard_input_sent",
                "attention_score": attention_priority(AttentionState.RUNNING),
            }
        )
        await self.registry.upsert(updated)
        return {
            "type": "action_result",
            "session_id": request.session_id,
            "action": request.action,
            "ok": True,
            "reason": "delivered",
            "detail": f"input delivered to tmux pane {current.tmux_pane_id}",
        }

    async def _append_transcript_event(
        self,
        *,
        session_id: str,
        direction: TranscriptDirection,
        source: TranscriptSource,
        text: str,
        ts: datetime,
    ) -> TranscriptEvent | None:
        if self.transcript_store is None:
            return None
        event = await self.transcript_store.append(
            session_id=session_id,
            direction=direction,
            source=source,
            text=text,
            ts=ts,
        )
        if self.on_transcript_event is not None:
            try:
                await self.on_transcript_event(event)
            except Exception:
                # Transcript broadcast is best-effort; storing the event and
                # keeping tmux monitoring alive is more important than a single
                # client notification.
                pass
        return event

    def _snippet(self, text: str, *, limit: int = 500) -> str:
        compact = "\n".join(line.rstrip() for line in text.splitlines() if line.strip())
        if len(compact) <= limit:
            return compact
        return compact[-limit:]

    def _next_unread(
        self,
        current_status: SessionStatus | None,
        next_state: AttentionState,
        new_output: str,
    ) -> bool:
        if current_status is None:
            return False
        return current_status.unread or next_state != current_status.state or bool(new_output)
