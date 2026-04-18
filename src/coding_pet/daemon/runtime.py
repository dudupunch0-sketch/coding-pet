from __future__ import annotations

import asyncio
import hashlib
import os
import tempfile
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path

from coding_pet.daemon.action_router import SessionActionRouter
from coding_pet.daemon.manager import MonitorManager
from coding_pet.daemon.session_registry import SessionRegistry
from coding_pet.ipc.server import IpcServer
from coding_pet.notifiers.base import Notifier
from coding_pet.state_store import StateStore

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
    action_router: SessionActionRouter | None = None
    ipc_server: IpcServer | None = None
    manager: MonitorManager | None = None
    _started: bool = field(init=False, default=False)
    _shutdown_event: asyncio.Event = field(init=False, default_factory=asyncio.Event)

    def __post_init__(self) -> None:
        if self.manager is None:
            self.manager = MonitorManager(
                registry=self.registry,
                stall_timeout=self.stall_timeout,
                notifier=self.notifier,
                notification_cooldown=self.notification_cooldown,
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
            )
        self.ipc_server.action_handler = self.action_router.handle_message

    @property
    def socket_path(self) -> Path:
        assert self.ipc_server is not None
        return self.ipc_server.socket_path

    async def start(self) -> None:
        if self._started:
            return
        self._shutdown_event.clear()
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        assert self.manager is not None
        assert self.ipc_server is not None
        await self.manager.restore_from_store()
        await self.ipc_server.start()
        self._started = True

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
        await self.manager.stop_all_sessions()
        await self.manager.persist_snapshot()
        await self.ipc_server.stop()
        self._started = False
