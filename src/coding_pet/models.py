from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator


class AgentKind(StrEnum):
    CODEX = "codex"
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


class ActionOutcome(StrEnum):
    ACCEPTED = "accepted"
    LOCAL_UPDATED = "local_updated"
    REJECTED = "rejected"
    TIMED_OUT = "timed_out"
    UNSUPPORTED = "unsupported"
    BACKEND_FAILED = "backend_failed"


_SUCCESS_ACTION_OUTCOMES = {
    ActionOutcome.ACCEPTED,
    ActionOutcome.LOCAL_UPDATED,
}

_UNSUPPORTED_ACTION_REASONS = {
    "unsupported_action",
    "action_not_supported",
}

_REJECTED_ACTION_REASONS = {
    "invalid_action_request",
    "session_not_found",
    "session_not_live",
    "session_live",
    "no_live_control_channel",
    "tmux_target_missing",
    "unsupported_agent",
}


def _parse_action_outcome(value: object) -> ActionOutcome | None:
    if isinstance(value, ActionOutcome):
        return value
    if isinstance(value, str):
        try:
            return ActionOutcome(value)
        except ValueError:
            return None
    return None


def action_outcome_ok(outcome: ActionOutcome | str) -> bool:
    parsed = _parse_action_outcome(outcome)
    return parsed in _SUCCESS_ACTION_OUTCOMES


def infer_action_outcome(*, ok: object, reason: object = None) -> ActionOutcome:
    if isinstance(reason, str):
        if reason in _UNSUPPORTED_ACTION_REASONS:
            return ActionOutcome.UNSUPPORTED
        if reason in _REJECTED_ACTION_REASONS:
            return ActionOutcome.REJECTED
        if "timeout" in reason or "timed_out" in reason:
            return ActionOutcome.TIMED_OUT
    if ok is True:
        return ActionOutcome.ACCEPTED
    if ok is False:
        return ActionOutcome.BACKEND_FAILED
    return ActionOutcome.BACKEND_FAILED


def normalize_action_result_message(message: dict[str, object]) -> dict[str, object]:
    normalized = dict(message)
    explicit_outcome = _parse_action_outcome(normalized.get("outcome"))
    if explicit_outcome is None:
        outcome = infer_action_outcome(
            ok=normalized.get("ok"),
            reason=normalized.get("reason"),
        )
    else:
        outcome = explicit_outcome
    normalized["outcome"] = outcome.value
    normalized["ok"] = action_outcome_ok(outcome)
    return normalized


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


AGENT_LIVE_ACTIONS = (
    "send_reply",
    "send_without_enter",
    "approve",
    "reject",
)
TMUX_LIVE_ACTIONS = (
    *AGENT_LIVE_ACTIONS,
    "attach",
    "mark_read",
    "manual_state_override",
)
INACTIVE_SESSION_ACTIONS = (
    "hide_pet",
    "mark_read",
    "manual_state_override",
)


class ActionCapability(BaseModel):
    action: str
    transport: str = "local"
    requires_text: bool = False
    press_enter_default: bool | None = None
    semantics: str = "local_state"

    @field_validator("action", "transport", "semantics")
    @classmethod
    def _normalize_nonempty_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must be non-empty")
        return normalized


def action_capability_for(action: str, *, source_kind: str = "process") -> ActionCapability:
    if action in {"send_reply", "send_without_enter"}:
        return ActionCapability(
            action=action,
            transport="tmux_buffer" if source_kind == "tmux" else "process_stdin",
            requires_text=True,
            press_enter_default=action == "send_reply",
            semantics="agent_reply",
        )
    if action in {"approve", "reject"}:
        return ActionCapability(
            action=action,
            transport="tmux_buffer" if source_kind == "tmux" else "process_stdin",
            requires_text=False,
            press_enter_default=True,
            semantics="agent_control",
        )
    if action == "attach":
        return ActionCapability(
            action=action,
            transport="tmux_attach",
            requires_text=False,
            press_enter_default=None,
            semantics="operator_attach",
        )
    if action == "manual_state_override":
        return ActionCapability(
            action=action,
            transport="local",
            requires_text=False,
            press_enter_default=None,
            semantics="manual_state_override",
        )
    return ActionCapability(
        action=action,
        transport="local",
        requires_text=False,
        press_enter_default=None,
        semantics="local_state",
    )


def action_capabilities_for(
    actions: list[str] | tuple[str, ...],
    *,
    source_kind: str = "process",
) -> list[ActionCapability]:
    capabilities: list[ActionCapability] = []
    seen: set[str] = set()
    for action in actions:
        if action in seen:
            continue
        seen.add(action)
        capabilities.append(action_capability_for(action, source_kind=source_kind))
    return capabilities


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
    supported_actions: list[str] = Field(default_factory=list)
    action_capabilities: list[ActionCapability] = Field(default_factory=list)

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

    @field_validator("supported_actions", mode="before")
    @classmethod
    def _normalize_supported_actions(cls, value: object) -> object:
        if value is None:
            return []
        if not isinstance(value, list | tuple | set):
            return value
        normalized: list[str] = []
        for item in value:
            if isinstance(item, str) and item not in normalized:
                normalized.append(item)
        return normalized

    def model_post_init(self, __context: object) -> None:
        if self.attention_score == 0 and self.state is not AttentionState.IDLE:
            self.attention_score = attention_priority(self.state)
        self._normalize_action_contract()

    def _normalize_action_contract(self) -> None:
        if self.action_capabilities:
            normalized_capabilities: list[ActionCapability] = []
            seen: set[str] = set()
            for capability in self.action_capabilities:
                if capability.action in seen:
                    continue
                seen.add(capability.action)
                normalized_capabilities.append(capability)
            self.action_capabilities = normalized_capabilities
            if not self.supported_actions:
                self.supported_actions = [
                    capability.action for capability in normalized_capabilities
                ]
            return
        if self.supported_actions:
            self.action_capabilities = action_capabilities_for(
                self.supported_actions,
                source_kind=self.source_kind,
            )

    def has_action_restrictions(self) -> bool:
        return bool(self.action_capabilities or self.supported_actions)

    def capability_for(self, action: str) -> ActionCapability | None:
        for capability in self.action_capabilities:
            if capability.action == action:
                return capability
        return None

    def supports_action(self, action: str) -> bool:
        if self.action_capabilities:
            return self.capability_for(action) is not None
        if self.supported_actions:
            return action in self.supported_actions
        return True
