from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator


class AgentKind(StrEnum):
    CLAUDE_CODE = "claude_code"
    OPENCODE = "opencode"


class AttentionState(StrEnum):
    UNKNOWN = "unknown"
    IDLE = "idle"
    RUNNING = "running"
    NEEDS_PERMISSION = "needs_permission"
    NEEDS_CHOICE = "needs_choice"
    NEEDS_INPUT = "needs_input"
    REVIEW_NEEDED = "review_needed"
    STALLED = "stalled"
    COMPLETED = "completed"
    FAILED = "failed"


_ATTENTION_PRIORITY = {
    AttentionState.UNKNOWN: 0,
    AttentionState.IDLE: 0,
    AttentionState.RUNNING: 10,
    AttentionState.STALLED: 20,
    AttentionState.COMPLETED: 30,
    AttentionState.REVIEW_NEEDED: 40,
    AttentionState.NEEDS_INPUT: 50,
    AttentionState.NEEDS_CHOICE: 55,
    AttentionState.NEEDS_PERMISSION: 60,
    AttentionState.FAILED: 70,
}


def attention_priority(state: AttentionState) -> int:
    return _ATTENTION_PRIORITY[state]


class SessionStatus(BaseModel):
    session_id: str
    agent_kind: AgentKind
    title: str
    workspace: str
    state: AttentionState
    summary: str
    last_event_at: datetime
    pid: int | None = None
    last_output_snippet: str = ""
    attention_score: int = Field(default=0)
    unread: bool = False
    live: bool = True

    # Session source metadata. Existing launched-process sessions keep the default.
    source_kind: str = "process"
    tmux_pane_id: str | None = None
    tmux_session_name: str | None = None
    tmux_window_pane: str | None = None
    tmux_current_command: str | None = None

    # Console activity metadata.
    last_activity_at: datetime | None = None
    last_input_at: datetime | None = None
    last_output_at: datetime | None = None
    last_dashboard_input: str | None = None
    estimated_current_request: str | None = None
    agent_waiting_message: str | None = None
    state_reason: str | None = None
    output_hash: str | None = None

    @field_validator("attention_score", mode="before")
    @classmethod
    def _default_attention_score(cls, value: int | None) -> int | None:
        return value

    def model_post_init(self, __context: object) -> None:
        if self.attention_score == 0 and self.state is not AttentionState.IDLE:
            self.attention_score = attention_priority(self.state)
