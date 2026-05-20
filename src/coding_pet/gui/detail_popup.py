from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from coding_pet.gui.detail_view_model import DetailViewModel, build_detail_view_model
from coding_pet.gui.reply_box import ReplyBoxModel
from coding_pet.gui.session_panel import PanelAction
from coding_pet.models import SessionStatus
from coding_pet.transcripts.model import TranscriptEvent


@dataclass(slots=True)
class DetailPopupShell:
    """Headless-safe detail popup facade.

    The real Qt widget is optional and created lazily. Tests and daemon/IPC
    wiring use the same public API without importing PySide6 at module import
    time.
    """

    status: SessionStatus
    events: list[TranscriptEvent] = field(default_factory=list)
    _widget: Any | None = field(init=False, default=None)
    _reply_box: ReplyBoxModel = field(init=False)

    def __post_init__(self) -> None:
        self._reply_box = ReplyBoxModel(self.status.session_id)

    def view_model(self) -> DetailViewModel:
        return build_detail_view_model(self.status, self.events)

    def update(self, status: SessionStatus, events: list[TranscriptEvent] | None = None) -> None:
        self.status = status
        self._reply_box = ReplyBoxModel(status.session_id)
        if events is not None:
            self.events = list(events)
        self._update_qt_labels()

    def build_send_request(self, text: str, *, press_enter: bool = True) -> dict[str, object]:
        return self._reply_box.build_request(text, press_enter=press_enter)

    def build_attach_request(self) -> dict[str, object]:
        return {
            "type": "action_request",
            "session_id": self.status.session_id,
            "action": PanelAction.ATTACH.value,
        }

    def build_mark_read_request(self) -> dict[str, object]:
        return {
            "type": "action_request",
            "session_id": self.status.session_id,
            "action": PanelAction.MARK_READ.value,
        }

    def show(self) -> None:
        self._ensure_qt_widget()
        if self._widget is not None:
            self._widget.show()

    def _ensure_qt_widget(self) -> None:
        if self._widget is not None:
            return
        try:
            from PySide6.QtWidgets import (
                QLabel,
                QPlainTextEdit,
                QPushButton,
                QVBoxLayout,
                QWidget,
            )
        except Exception:
            return
        widget = QWidget()
        layout = QVBoxLayout()
        vm = self.view_model()
        header = QLabel(f"{vm.title} · {vm.state}")
        target = QLabel(vm.target_label)
        request = QLabel(vm.agent_request)
        transcript = QPlainTextEdit("\n".join(row.text for row in vm.transcript_rows))
        transcript.setReadOnly(True)
        reply = QPlainTextEdit()
        send = QPushButton("Send")
        send_no_enter = QPushButton("Send without Enter")
        attach = QPushButton("Attach")
        for child in (header, target, request, transcript, reply, send, send_no_enter, attach):
            layout.addWidget(child)
        widget.setLayout(layout)
        self._widget = widget

    def _update_qt_labels(self) -> None:
        # The minimal shell rebuilds labels when reopened. Keeping this as a
        # no-op avoids storing Qt objects in the pure data path.
        return
