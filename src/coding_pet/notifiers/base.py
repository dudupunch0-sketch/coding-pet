from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from coding_pet.models import AttentionState


@dataclass(slots=True)
class Notification:
    session_id: str
    title: str
    body: str
    state: AttentionState


class Notifier(Protocol):
    async def notify(self, notification: Notification) -> None: ...
