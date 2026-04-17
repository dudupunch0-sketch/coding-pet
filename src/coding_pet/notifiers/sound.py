from __future__ import annotations

from dataclasses import dataclass, field

from coding_pet.notifiers.base import Notification


@dataclass(slots=True)
class SoundNotifier:
    played: list[str] = field(default_factory=list)

    async def notify(self, notification: Notification) -> None:
        self.played.append(notification.session_id)
