from __future__ import annotations

import asyncio
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from coding_pet.gui.session_panel import PanelAction
from coding_pet.gui.theme import WidgetTheme, default_theme
from coding_pet.ipc.client import IpcClient
from coding_pet.models import AttentionState, SessionStatus
from coding_pet.state_store import StateStore
from coding_pet.transcripts.model import TranscriptEvent

ActionResult = dict[str, object]


def layout_sessions(
    sessions: list[SessionStatus],
    *,
    screen_width: int,
    screen_height: int,
    pet_size: tuple[int, int],
    margin: int = 24,
    gap: int = 12,
) -> OrderedDict[str, tuple[int, int]]:
    ordered = sorted(sessions, key=lambda status: status.session_id)
    x = screen_width - pet_size[0] - margin
    y = screen_height - pet_size[1] - margin
    layout: OrderedDict[str, tuple[int, int]] = OrderedDict()
    for index, status in enumerate(ordered):
        layout[status.session_id] = (x, y - index * (pet_size[1] + gap))
    return layout


@dataclass(slots=True)
class CodingPetWidgetApp:
    theme: WidgetTheme = field(default_factory=default_theme)
    socket_path: Path | None = None
    state_store: StateStore | None = None
    widgets: dict[str, Any] = field(default_factory=dict)
    transcripts: dict[str, list[TranscriptEvent]] = field(default_factory=dict)
    last_action_result: ActionResult | None = None
    _client: IpcClient | None = field(init=False, default=None)
    _listen_task: asyncio.Task[None] | None = field(init=False, default=None)
    _ready: asyncio.Event = field(init=False, default_factory=asyncio.Event)

    def ensure_app(self) -> Any:
        from PySide6.QtWidgets import QApplication  # type: ignore[import-not-found]

        app = QApplication.instance()
        if app is None:
            app = QApplication([])
        return app

    def show_sessions(self, sessions: list[SessionStatus]) -> None:
        width = 1280
        height = 720
        try:
            app = self.ensure_app()
        except Exception:
            app = None
        if app is not None:
            screen = app.primaryScreen()
            geometry = screen.availableGeometry() if screen is not None else None
            width = geometry.width() if geometry is not None else width
            height = geometry.height() if geometry is not None else height
        positions = layout_sessions(
            sessions,
            screen_width=width,
            screen_height=height,
            pet_size=(96, 96),
        )
        active_ids = set(positions)
        for removed in list(self.widgets):
            if removed not in active_ids:
                self.widgets.pop(removed)
        for status in sessions:
            widget = self.widgets.get(status.session_id)
            if widget is None:
                from coding_pet.gui.widget import CodingPetWidgetShell

                widget = CodingPetWidgetShell(
                    status=status,
                    theme=self.theme,
                    on_detail_opened=self._on_widget_detail_opened,
                )
                self.widgets[status.session_id] = widget
            widget.update_status(status)
            x, y = positions[status.session_id]
            widget.move(x, y)
            widget.show()

    async def load_snapshot(self) -> None:
        if self.state_store is None:
            return
        sessions = await self.state_store.restore_sessions()
        self.show_sessions(sessions)

    async def connect_to_daemon(self, *, message_limit: int | None = None) -> None:
        if self.socket_path is None:
            raise RuntimeError("socket_path is required for daemon connectivity")
        self._ready.clear()
        self.last_action_result = None
        self._client = IpcClient(self.socket_path)
        await self._client.connect()
        self._listen_task = asyncio.create_task(self._listen_to_daemon(message_limit=message_limit))
        await self._ready.wait()

    async def disconnect_from_daemon(self) -> None:
        if self._listen_task is not None:
            self._listen_task.cancel()
            try:
                await self._listen_task
            except asyncio.CancelledError:
                pass
            self._listen_task = None
        if self._client is not None:
            await self._client.close()
            self._client = None

    async def _listen_to_daemon(self, *, message_limit: int | None) -> None:
        assert self._client is not None
        processed = 0
        async for message in self._client.stream_messages():
            await self.apply_daemon_message(message)
            if not self._ready.is_set():
                self._ready.set()
            processed += 1
            if message_limit is not None and processed >= message_limit:
                break

    async def send_panel_action(
        self,
        *,
        session_id: str,
        action: str | Any,
        reply_text: str | None = None,
    ) -> None:
        if self._client is None:
            raise RuntimeError("widget is not connected to the daemon")
        action_value = action.value if hasattr(action, "value") else str(action)
        payload: dict[str, str] = {
            "type": "action_request",
            "session_id": session_id,
            "action": action_value,
        }
        if reply_text is not None:
            payload["reply_text"] = reply_text
        await self._client.send(payload)

    async def request_transcript(self, session_id: str, *, limit: int = 100) -> None:
        if self._client is None:
            raise RuntimeError("widget is not connected to the daemon")
        await self._client.send({
            "type": "transcript_request",
            "session_id": session_id,
            "limit": limit,
        })

    async def apply_daemon_message(self, message: dict[str, Any]) -> None:
        message_type = message.get("type")
        if message_type == "snapshot":
            self.last_action_result = None
            sessions = [SessionStatus.model_validate(item) for item in message.get("sessions", [])]
            self.show_sessions(sessions)
            return
        if message_type == "session_updated":
            session_data = message.get("session")
            if isinstance(session_data, dict):
                status = SessionStatus.model_validate(session_data)
                current = [
                    widget.status
                    for widget in self.widgets.values()
                    if widget.status.session_id != status.session_id
                ]
                current.append(status)
                self.show_sessions(current)
            return
        if message_type == "session_removed":
            session_id = message.get("session_id")
            if isinstance(session_id, str) and session_id in self.widgets:
                self.widgets.pop(session_id)
                self.show_sessions([widget.status for widget in self.widgets.values()])
            return
        if message_type == "action_result":
            self.last_action_result = message
            session_id = message.get("session_id")
            detail = message.get("detail")
            if (
                isinstance(session_id, str)
                and isinstance(detail, str)
                and session_id in self.widgets
            ):
                widget = self.widgets[session_id]
                updated = widget.status.model_copy(update={
                    "state": self._state_after_action_result(widget.status, message),
                    "unread": self._unread_after_action_result(widget.status, message),
                })
                widget.update_status(updated, clear_feedback=False)
                widget.apply_action_feedback(
                    detail=detail,
                    ok=message.get("ok") is True,
                )
            return
        if message_type == "transcript_snapshot":
            session_id = message.get("session_id")
            if isinstance(session_id, str):
                events = [
                    TranscriptEvent.model_validate(item)
                    for item in message.get("events", [])
                    if isinstance(item, dict)
                ]
                self.transcripts[session_id] = events
                self._update_widget_transcript(session_id)
            return
        if message_type == "transcript_appended":
            event_data = message.get("event")
            if isinstance(event_data, dict):
                event = TranscriptEvent.model_validate(event_data)
                self.transcripts.setdefault(event.session_id, []).append(event)
                self._update_widget_transcript(event.session_id)

    def _update_widget_transcript(self, session_id: str) -> None:
        widget = self.widgets.get(session_id)
        if widget is not None:
            widget.update_detail_events(self.transcripts.get(session_id, []))

    def _on_widget_detail_opened(self, session_id: str) -> None:
        if self._client is None:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(self._send_detail_opened_requests(session_id))

    async def _send_detail_opened_requests(self, session_id: str) -> None:
        if self._client is None:
            return
        await self.request_transcript(session_id)
        await self.send_panel_action(
            session_id=session_id,
            action=PanelAction.MARK_READ,
        )

    def _state_after_action_result(
        self,
        status: SessionStatus,
        message: dict[str, Any],
    ) -> AttentionState:
        if message.get("ok") is not True:
            return status.state
        if message.get("action") in {"send_reply", "send_without_enter", "approve", "reject"}:
            return AttentionState.RUNNING
        return status.state

    def _unread_after_action_result(
        self,
        status: SessionStatus,
        message: dict[str, Any],
    ) -> bool:
        if message.get("ok") is True and message.get("action") == "mark_read":
            return False
        return status.unread
