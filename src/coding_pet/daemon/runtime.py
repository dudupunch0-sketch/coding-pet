from __future__ import annotations

import asyncio
import hashlib
import os
import tempfile
from dataclasses import dataclass, field, replace
from datetime import timedelta
from pathlib import Path

from coding_pet.config import StateDetectionConfig, TmuxConfig
from coding_pet.daemon.action_router import SessionActionRouter
from coding_pet.daemon.manager import MonitorManager
from coding_pet.daemon.session_registry import SessionRegistry
from coding_pet.daemon.tmux_monitor import TmuxMonitorService
from coding_pet.hooks import HookEvent, hook_event_from_message, status_for_hook_event
from coding_pet.ipc.server import IpcServer
from coding_pet.notifiers.base import Notifier
from coding_pet.state_store import StateStore
from coding_pet.tmux.client import TmuxClient
from coding_pet.transcripts.model import TranscriptEvent
from coding_pet.transcripts.store import TranscriptStore

DEFAULT_SOCKET_NAME = "coding-pet.sock"
MAX_SOCKET_PATH_BYTES = 100


def default_socket_path(runtime_dir: Path) -> Path:
    candidate = runtime_dir / DEFAULT_SOCKET_NAME
    if len(os.fsencode(candidate)) <= MAX_SOCKET_PATH_BYTES:
        return candidate
    digest = hashlib.sha256(os.fsencode(runtime_dir)).hexdigest()[:12]
    return Path(tempfile.gettempdir()) / f"coding-pet-{digest}.sock"


@dataclass(slots=True)
class DaemonRuntime:
    runtime_dir: Path
    state_store: StateStore
    registry: SessionRegistry = field(default_factory=SessionRegistry)
    notifier: Notifier | None = None
    stall_timeout: timedelta = timedelta(minutes=5)
    notification_cooldown: timedelta = timedelta(minutes=1)
    completed_retention: timedelta | None = None
    process_stop_timeout: timedelta = timedelta(seconds=2)
    action_router: SessionActionRouter | None = None
    ipc_server: IpcServer | None = None
    manager: MonitorManager | None = None
    tmux_config: TmuxConfig | None = None
    tmux_client: TmuxClient | None = None
    transcript_store: TranscriptStore | None = None
    state_detection_config: StateDetectionConfig | None = None
    tmux_monitor: TmuxMonitorService | None = None
    _started: bool = field(init=False, default=False)
    _shutdown_event: asyncio.Event = field(init=False, default_factory=asyncio.Event)

    def __post_init__(self) -> None:
        if self.manager is None:
            self.manager = MonitorManager(
                registry=self.registry,
                stall_timeout=self.stall_timeout,
                notifier=self.notifier,
                notification_cooldown=self.notification_cooldown,
                completed_retention=self.completed_retention,
                process_stop_timeout=self.process_stop_timeout,
                state_store=self.state_store,
            )
        if self.action_router is None:
            self.action_router = SessionActionRouter(
                registry=self.registry,
                is_session_live=self.manager.has_live_session,
                dispatch_action=self.manager.route_action,
            )
        if self.ipc_server is None:
            self.ipc_server = IpcServer(
                socket_path=default_socket_path(self.runtime_dir),
                registry=self.registry,
                transcript_store=self.transcript_store,
            )
        self.ipc_server.action_handler = self.action_router.handle_message
        self.ipc_server.hook_handler = self.handle_hook_event
        if self.ipc_server.transcript_store is None:
            self.ipc_server.transcript_store = self.transcript_store

    @property
    def socket_path(self) -> Path:
        assert self.ipc_server is not None
        return self.ipc_server.socket_path

    async def handle_hook_event(self, message: dict[str, object]) -> dict[str, object]:
        try:
            event = hook_event_from_message(message)
        except ValueError as exc:
            return {
                "type": "hook_event_result",
                "ok": False,
                "reason": "invalid_hook_event",
                "detail": str(exc),
            }
        event = await self._resolve_hook_target_event(event)
        existing = await self.registry.get(event.session_id)
        status = status_for_hook_event(event, existing=existing)
        await self.registry.upsert(status)
        await self._append_hook_transcript_event(
            session_id=event.session_id,
            text=f"{event.event_name}: {event.summary}",
        )
        return {
            "type": "hook_event_result",
            "ok": True,
            "session_id": event.session_id,
            "agent": event.agent_kind.value,
            "event": event.event_name,
            "state": event.state.value,
        }

    async def _resolve_hook_target_event(self, event: HookEvent) -> HookEvent:
        existing = await self.registry.get(event.session_id)
        if existing is not None:
            return event
        candidates = await self.registry.list_sessions()
        event_workspace = _normalized_workspace(event.workspace)
        for candidate in candidates:
            if candidate.agent_kind is not event.agent_kind:
                continue
            if not candidate.live:
                continue
            if candidate.source_kind not in {"process", "tmux"}:
                continue
            if _normalized_workspace(candidate.workspace) == event_workspace:
                return replace(event, session_id=candidate.session_id)
        return event

    async def _append_hook_transcript_event(self, *, session_id: str, text: str) -> None:
        if self.transcript_store is None:
            return
        event = await self.transcript_store.append(
            session_id=session_id,
            direction="system",
            source="hook_event",
            text=text,
        )
        await self._broadcast_transcript_event(event)

    async def start(self) -> None:
        if self._started:
            return
        self._shutdown_event.clear()
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        assert self.manager is not None
        assert self.ipc_server is not None
        await self.manager.restore_from_store()
        if self.transcript_store is not None:
            await self.transcript_store.initialize()
        await self.ipc_server.start()
        if self.tmux_config is not None and self.tmux_config.enabled:
            stalled_after = timedelta(
                seconds=(
                    self.state_detection_config.stalled_after_sec
                    if self.state_detection_config is not None
                    else 300
                )
            )
            self.tmux_monitor = TmuxMonitorService(
                registry=self.registry,
                manager=self.manager,
                client=self.tmux_client or TmuxClient(),
                transcript_store=self.transcript_store,
                config=self.tmux_config,
                stalled_after=stalled_after,
                on_transcript_event=self._broadcast_transcript_event,
            )
            await self.tmux_monitor.start()
        self._started = True

    async def _broadcast_transcript_event(self, event: TranscriptEvent) -> None:
        assert self.ipc_server is not None
        await self.ipc_server.broadcast_transcript_event(event.model_dump(mode="json"))

    def request_shutdown(self) -> None:
        self._shutdown_event.set()

    async def serve(
        self,
        *,
        oneshot: bool = False,
        shutdown_event: asyncio.Event | None = None,
    ) -> None:
        gate = shutdown_event or self._shutdown_event
        await self.start()
        try:
            if oneshot:
                return
            await gate.wait()
        finally:
            await self.stop()

    async def stop(self) -> None:
        if not self._started:
            return
        assert self.manager is not None
        assert self.ipc_server is not None
        self.request_shutdown()
        if self.tmux_monitor is not None:
            await self.tmux_monitor.stop()
            self.tmux_monitor = None
        await self.manager.stop_all_sessions()
        await self.manager.persist_snapshot()
        await self.ipc_server.stop()
        self._started = False


def _normalized_workspace(value: str) -> str:
    raw = value.strip()
    if not raw:
        return ""
    try:
        return Path(raw).expanduser().resolve(strict=False).as_posix()
    except Exception:  # noqa: BLE001
        return raw
