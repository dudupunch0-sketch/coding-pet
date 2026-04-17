from __future__ import annotations

import asyncio
import logging
import shutil
from dataclasses import dataclass, field

from coding_pet.logging import get_logger
from coding_pet.notifiers.base import Notification


@dataclass(slots=True)
class DesktopNotifier:
    notify_send_bin: str | None = field(default=None)
    _logger: logging.LoggerAdapter[logging.Logger] = field(init=False)

    def __post_init__(self) -> None:
        if self.notify_send_bin is None:
            self.notify_send_bin = shutil.which("notify-send")
        self._logger = get_logger("notifiers.desktop")

    async def notify(self, notification: Notification) -> None:
        if self.notify_send_bin is None:
            self._logger.info(
                "Desktop notification fallback",
                extra={
                    "event_type": "desktop_notification",
                    "session_id": notification.session_id,
                    "notification_state": notification.state.value,
                },
            )
            return

        process = await asyncio.create_subprocess_exec(
            self.notify_send_bin,
            notification.title,
            notification.body,
        )
        await process.wait()
