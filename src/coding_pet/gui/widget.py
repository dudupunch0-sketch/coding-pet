from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from coding_pet.gui.bubble import bubble_text_for_status
from coding_pet.gui.runtime import has_graphical_session
from coding_pet.gui.session_panel import PanelAction, SessionPanelViewModel
from coding_pet.gui.theme import (
    ThemeManifest,
    WidgetMood,
    WidgetTheme,
    codex_pet_frame_count,
    codex_pet_frame_duration_ms,
    codex_pet_frame_rect,
    default_assets_root,
    is_image_sprite,
    load_manifest_for_theme,
    mood_for_status,
    resolve_sprite_for_mood,
)
from coding_pet.models import SessionStatus
from coding_pet.transcripts.model import TranscriptEvent


@dataclass(slots=True)
class WidgetPresentation:
    mood: str
    bubble_text: str


class CodingPetWidgetShell:
    def __init__(
        self,
        *,
        status: SessionStatus,
        theme: WidgetTheme | str,
        on_detail_opened: Callable[[str], None] | None = None,
        on_action_request: Callable[[dict[str, object]], None] | None = None,
    ) -> None:
        self.theme = theme
        self.status = status
        self._on_detail_opened = on_detail_opened
        self._on_action_request = on_action_request
        self.panel = SessionPanelViewModel()
        self.assets_root = default_assets_root()
        self._theme_manifest = self._load_theme_manifest()
        self.x = 0
        self.y = 0
        self._feedback_text: str | None = None
        self._widget: Any | None = None
        self._pet_label: Any | None = None
        self._bubble_label: Any | None = None
        self._detail_popup: Any | None = None
        self._transcript_events: list[TranscriptEvent] = []
        self._drag_origin: Any | None = None
        self._animation_timer: Any | None = None
        self._animation_frame = 0
        self._animation_mood: str | None = None
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
            self._set_pet_sprite(presentation.mood)
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

    def open_detail_popup(self, events: list[TranscriptEvent] | None = None) -> Any:
        from coding_pet.gui.detail_popup import DetailPopupShell

        updated = self.open_detail_panel()
        popup_events = list(self._transcript_events if events is None else events)
        if self._detail_popup is None:
            self._detail_popup = DetailPopupShell(
                status=updated,
                events=popup_events,
                on_action_request=self._on_action_request,
            )
        else:
            self._detail_popup.update(updated, events=popup_events)
        self._detail_popup.show()
        if self._on_detail_opened is not None:
            self._on_detail_opened(updated.session_id)
        return self._detail_popup

    def update_detail_events(self, events: list[TranscriptEvent]) -> None:
        self._transcript_events = list(events)
        if self._detail_popup is not None:
            self._detail_popup.update(self.status, events=self._transcript_events)

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

    def _load_theme_manifest(self) -> ThemeManifest | None:
        try:
            return load_manifest_for_theme(self.theme, assets_root=self.assets_root)
        except Exception:
            return None

    def _setup_qt_widget(self) -> None:
        if not has_graphical_session():
            return
        try:
            from PySide6.QtCore import Qt
            from PySide6.QtGui import QFont
            from PySide6.QtWidgets import (
                QApplication,
                QLabel,
                QVBoxLayout,
                QWidget,
            )
        except ImportError:
            return
        if QApplication.instance() is None:
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
                was_dragging = shell._drag_origin is not None
                shell._drag_origin = None
                if was_dragging and event.button() is Qt.MouseButton.LeftButton:
                    shell.open_detail_popup()
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

    def sprite_asset_path(self, mood: str) -> Path | None:
        if self._theme_manifest is None:
            return None
        try:
            sprite_mood = WidgetMood(mood)
        except ValueError:
            return None
        asset_root = self._theme_manifest.asset_root or self.assets_root
        if self._theme_manifest.spritesheet is not None:
            asset_file = asset_root / self._theme_manifest.spritesheet.path
            return asset_file.resolve() if asset_file.exists() else None
        sprite_path = resolve_sprite_for_mood(
            self._theme_manifest,
            mood=sprite_mood,
            assets_root=asset_root,
        )
        asset_file = asset_root / sprite_path
        if asset_file.exists():
            return asset_file.resolve()
        return None

    def _set_pet_sprite(self, mood: str) -> None:
        asset_file = self.sprite_asset_path(mood)
        if asset_file is not None and is_image_sprite(asset_file):
            if self._set_pet_pixmap(asset_file, mood=mood):
                return
        if self._pet_label is not None:
            self._stop_animation()
            self._pet_label.setText(self._pet_glyph(mood, asset_file))

    def _set_pet_pixmap(self, asset_file: Path, *, mood: str) -> bool:
        if self._pet_label is None:
            return False
        try:
            from PySide6.QtCore import Qt
            from PySide6.QtGui import QPixmap
        except ImportError:
            return False
        pixmap = QPixmap(str(asset_file))
        if pixmap.isNull():
            return False
        source = self._atlas_frame(pixmap, mood=mood, frame=0)
        scaled = pixmap.scaled(
            96,
            96,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.FastTransformation,
        )
        if source is not None:
            scaled = source.scaled(
                96,
                96,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.FastTransformation,
            )
        self._pet_label.setText("")
        self._pet_label.setPixmap(scaled)
        self._start_animation(asset_file, mood=mood)
        return True

    def _atlas_frame(self, pixmap: Any, *, mood: str, frame: int) -> Any | None:
        if self._theme_manifest is None or self._theme_manifest.spritesheet is None:
            return None
        try:
            sprite_mood = WidgetMood(mood)
        except ValueError:
            return None
        sheet = self._theme_manifest.spritesheet
        rect = codex_pet_frame_rect(sheet, sprite_mood, frame=frame)
        return pixmap.copy(
            rect.x,
            rect.y,
            rect.width,
            rect.height,
        )

    def _start_animation(self, asset_file: Path, *, mood: str) -> None:
        if self._theme_manifest is None or self._theme_manifest.spritesheet is None:
            self._stop_animation()
            return
        if self._animation_timer is not None and self._animation_mood == mood:
            return
        self._stop_animation()
        try:
            from PySide6.QtCore import Qt, QTimer
            from PySide6.QtGui import QPixmap
        except ImportError:
            return
        sheet = self._theme_manifest.spritesheet
        try:
            sprite_mood = WidgetMood(mood)
        except ValueError:
            return
        frame_count = codex_pet_frame_count(sheet, sprite_mood)
        pixmap = QPixmap(str(asset_file))
        if pixmap.isNull():
            return
        self._animation_mood = mood
        self._animation_frame = 0
        timer = QTimer()

        def tick() -> None:
            if self._pet_label is None:
                return
            self._animation_frame = (self._animation_frame + 1) % frame_count
            frame = self._atlas_frame(pixmap, mood=mood, frame=self._animation_frame)
            if frame is None:
                return
            timer.setInterval(
                codex_pet_frame_duration_ms(
                    sheet,
                    sprite_mood,
                    frame=self._animation_frame,
                )
            )
            self._pet_label.setPixmap(
                frame.scaled(
                    96,
                    96,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.FastTransformation,
                )
            )

        timer.timeout.connect(tick)
        timer.start(codex_pet_frame_duration_ms(sheet, sprite_mood, frame=0))
        self._animation_timer = timer

    def _stop_animation(self) -> None:
        if self._animation_timer is not None:
            self._animation_timer.stop()
        self._animation_timer = None
        self._animation_mood = None

    def _pet_glyph(self, mood: str, asset_file: Path | None = None) -> str:
        if asset_file is not None and not is_image_sprite(asset_file):
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
