from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any

from coding_pet.gui.theme import WidgetTheme, default_theme
from coding_pet.models import SessionStatus


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
    widgets: dict[str, Any] = field(default_factory=dict)

    def ensure_app(self) -> Any:
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is None:
            app = QApplication([])
        return app

    def show_sessions(self, sessions: list[SessionStatus]) -> None:
        app = self.ensure_app()
        screen = app.primaryScreen()
        geometry = screen.availableGeometry() if screen is not None else None
        width = geometry.width() if geometry is not None else 1280
        height = geometry.height() if geometry is not None else 720
        positions = layout_sessions(
            sessions,
            screen_width=width,
            screen_height=height,
            pet_size=(96, 96),
        )
        for status in sessions:
            widget = self.widgets.get(status.session_id)
            if widget is None:
                from coding_pet.gui.widget import CodingPetWidgetShell

                widget = CodingPetWidgetShell(status=status, theme=self.theme)
                self.widgets[status.session_id] = widget
            widget.update_status(status)
            x, y = positions[status.session_id]
            widget.move(x, y)
            widget.show()
