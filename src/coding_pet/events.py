from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from coding_pet.models import AttentionState


class SessionEventType(StrEnum):
    STATE_CHANGED = "state_changed"
    OUTPUT_RECEIVED = "output_received"
    PROCESS_EXITED = "process_exited"


class SessionEvent(BaseModel):
    session_id: str
    event_type: SessionEventType
    occurred_at: datetime
    summary: str
    state: AttentionState | None = None
    metadata: dict[str, str] = Field(default_factory=dict)
