from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

TranscriptDirection = Literal["in", "out", "system"]
TranscriptSource = Literal["tmux_capture", "dashboard_input", "system"]


class TranscriptEvent(BaseModel):
    event_id: str
    session_id: str
    ts: datetime
    direction: TranscriptDirection
    source: TranscriptSource
    text: str
