from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from coding_pet.gui.bubble import bubble_text_for_status
from coding_pet.gui.session_panel import PanelAction, SessionPanelViewModel
from coding_pet.gui.theme import (
    WidgetTheme,
    load_theme_manifest,
    mood_for_status,
    resolve_sprite_for_mood,
)
from coding_pet.models import SessionStatus


@dataclass(slots=True)
class WidgetPresentation:
    mood: str
    bubble_text: str


class CodingPetWidgetShell:
    def __init__(self, *, status: SessionStatus, theme: WidgetTheme) -> None:
        self.theme = theme
        self.status = status
        self.panel = SessionPanelViewModel()
        self.x = 0
        self.y = 0
        self._feedback_text: str | None = None
        self._widget: Any | None = None
        self._pet_label: Any | None = None
        self._bubble_label: Any | None = None
        self._drag_origin: Any | None = None
        self._setup_qt_widget()
        self.update_status(status)

    def presentation(self) -> WidgetPresentation:
        mood = mood_for_status(self.status)
        bubble_text = self._feedback_text or bubble_text_for_status(self.status)
        return WidgetPresentation(mood=mood.value, bubble_text=bubble_text)

    def update_status(self, status: SessionStatus, *, clear_feedback: bool = True) -> None:
        self.status = status
        if clear_feedback:
            self._feedback_text = None
        presentation = self.presentation()
        if self._pet_label is not None:
            self._pet_label.setText(self._pet_glyph(presentation.mood))
        if self._bubble_label is not None:
            self._bubble_label.setText(presentation.bubble_text)
        if self._widget is not None:
            self._widget.setWindowTitle(f"Coding Pet - {status.title}")

    def move(self, x: int, y: int) -> None:
        self.x = x
        self.y = y
        if self._widget is not None:
            self._widget.move(x, y)

    def show(self) -> None:
        if self._widget is not None:
            self._widget.show()

    def open_detail_panel(self) -> SessionStatus:
        updated = self.panel.open_session(self.status)
        self.update_status(updated)
        return updated

    def available_panel_actions(self) -> list[str]:
        return [action.value for action in self.panel.actions_for(self.status)]

    def available_reply_shortcuts(self) -> list[str]:
        return self.panel.reply_shortcuts_for(self.status)

    def apply_action_feedback(self, *, detail: str, ok: bool) -> None:
        prefix = "Action sent" if ok else "Action failed"
        self._feedback_text = f"{prefix}: {detail}"
        self.update_status(self.status, clear_feedback=False)

    def build_reply_shortcut_request(self, shortcut: str) -> dict[str, str]:
        return {
            "session_id": self.status.session_id,
            "action": PanelAction.SEND_REPLY.value,
            "reply_text": shortcut,
        }

    def _setup_qt_widget(self) -> None:
        try:
            from PySide6.QtCore import Qt
            from PySide6.QtGui import QFont
            from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget
        except ImportError:
            return

        shell = self

        class _Widget(QWidget):
            def mousePressEvent(self, event: Any) -> None:  # noqa: N802
                if event.button() is Qt.MouseButton.LeftButton:
                    shell._drag_origin = (
                        event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                    )
                super().mousePressEvent(event)

            def mouseMoveEvent(self, event: Any) -> None:  # noqa: N802
                if shell._drag_origin is not None and event.buttons() & Qt.MouseButton.LeftButton:
                    self.move(event.globalPosition().toPoint() - shell._drag_origin)
                super().mouseMoveEvent(event)

            def mouseReleaseEvent(self, event: Any) -> None:  # noqa: N802
                shell._drag_origin = None
                super().mouseReleaseEvent(event)

        widget = _Widget()
        widget.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        widget.setMinimumSize(96, 96)

        pet_label = QLabel(widget)
        pet_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pet_label.setFont(QFont("Sans Serif", 16, QFont.Weight.Bold))

        bubble_label = QLabel(widget)
        bubble_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bubble_label.setWordWrap(True)
        bubble_label.setFont(QFont("Sans Serif", 9))
        bubble_label.setStyleSheet(
            "background: rgba(255,255,255,220); border-radius: 12px; padding: 8px;"
        )

        layout = QVBoxLayout()
        layout.addWidget(bubble_label)
        layout.addWidget(pet_label)
        widget.setLayout(layout)

        self._widget = widget
        self._pet_label = pet_label
        self._bubble_label = bubble_label

    def _pet_glyph(self, mood: str) -> str:
        manifest = load_theme_manifest(Path("assets/sprites/theme-manifest.json"))
        sprite_path = resolve_sprite_for_mood(
            manifest,
            mood=type(next(iter(manifest.sprites.keys())))(mood),
            assets_root=Path("assets/sprites"),
        )
        asset_file = Path("assets/sprites") / sprite_path
        if asset_file.exists():
            return asset_file.read_text("utf-8").strip()
        return {
            "idle": "(=^･ω･^=)",
            "typing": "(=^･o･^=)ﾉ⌨",
            "celebrate": "\u2728(=^･^=)\u2728",
            "alert": "(=｀ω´=)!",
            "thinking": "(=･.･=)?",
            "sleepy": "(=-ω-=) zZ",
            "sad": "(=TωT=)",
        }[mood]
