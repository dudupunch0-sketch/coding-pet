from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from coding_pet.classifiers.patterns import (
    CHOICE_PATTERNS,
    COMPLETED_PATTERNS,
    FAILED_PATTERNS,
    INPUT_PATTERNS,
    PERMISSION_PATTERNS,
    RUNNING_PATTERNS,
)
from coding_pet.models import AttentionState


@dataclass(frozen=True, slots=True)
class AgentStateDecision:
    state: AttentionState
    summary: str
    reason: str
    agent_waiting_message: str | None = None
    estimated_current_request: str | None = None


@dataclass(frozen=True, slots=True)
class _SignalCandidate:
    state: AttentionState
    reason: str
    line: str
    start_line: int
    end_line: int
    priority: int


class AgentStateClassifier:
    def __init__(self, *, stalled_after: timedelta = timedelta(seconds=300)) -> None:
        self.stalled_after = stalled_after

    def classify_snapshot(
        self,
        snapshot: str,
        *,
        snapshot_changed: bool,
        last_output_at: datetime,
        observed_at: datetime,
    ) -> AgentStateDecision:
        text = snapshot.strip()
        if not text:
            return AgentStateDecision(
                state=AttentionState.UNKNOWN,
                summary="No tmux output captured",
                reason="empty_capture",
            )

        signal = self._latest_signal(text)
        last_line = self._last_nonempty_line_index(text)
        if signal is not None and signal.end_line >= last_line:
            return self._decision_for_signal(signal)
        if signal is not None and snapshot_changed:
            return AgentStateDecision(
                state=AttentionState.RUNNING,
                summary="Working...",
                reason="snapshot_changed",
            )

        if not snapshot_changed and observed_at - last_output_at >= self.stalled_after:
            return AgentStateDecision(
                state=AttentionState.STALLED,
                summary="Session appears stalled",
                reason="idle_timeout",
            )

        if snapshot_changed:
            return AgentStateDecision(
                state=AttentionState.RUNNING,
                summary="Working...",
                reason="snapshot_changed",
            )

        return AgentStateDecision(
            state=AttentionState.IDLE,
            summary="Waiting",
            reason="unchanged_below_stall_threshold",
        )

    def _latest_signal(self, text: str) -> _SignalCandidate | None:
        lines = text.splitlines()
        candidates: list[_SignalCandidate] = []
        signal_specs = (
            (AttentionState.FAILED, "failed_pattern", FAILED_PATTERNS),
            (AttentionState.NEEDS_PERMISSION, "permission_pattern", PERMISSION_PATTERNS),
            (AttentionState.NEEDS_CHOICE, "choice_pattern", CHOICE_PATTERNS),
            (AttentionState.NEEDS_INPUT, "input_pattern", INPUT_PATTERNS),
            (AttentionState.COMPLETED, "completed_pattern", COMPLETED_PATTERNS),
            (AttentionState.RUNNING, "running_pattern", RUNNING_PATTERNS),
        )
        for priority, (state, reason, patterns) in enumerate(signal_specs):
            for pattern in patterns:
                for match in pattern.finditer(text):
                    start_line = text.count("\n", 0, match.start())
                    end_index = max(match.end() - 1, match.start())
                    end_line = text.count("\n", 0, end_index)
                    display_line_index = min(end_line, len(lines) - 1)
                    candidates.append(
                        _SignalCandidate(
                            state=state,
                            reason=reason,
                            line=lines[display_line_index].strip(),
                            start_line=start_line,
                            end_line=end_line,
                            priority=priority,
                        )
                    )
        if not candidates:
            return None
        return max(candidates, key=lambda item: (item.end_line, -item.priority))

    def _last_nonempty_line_index(self, text: str) -> int:
        lines = text.splitlines()
        for index in range(len(lines) - 1, -1, -1):
            if lines[index].strip():
                return index
        return 0

    def _decision_for_signal(self, signal: _SignalCandidate) -> AgentStateDecision:
        waiting_message = None
        if signal.state in {
            AttentionState.NEEDS_PERMISSION,
            AttentionState.NEEDS_CHOICE,
            AttentionState.NEEDS_INPUT,
        }:
            waiting_message = signal.line
        return AgentStateDecision(
            state=signal.state,
            summary=self._summary_for(signal.state),
            reason=signal.reason,
            agent_waiting_message=waiting_message,
            estimated_current_request=waiting_message,
        )

    def _summary_for(self, state: AttentionState) -> str:
        return {
            AttentionState.FAILED: "Error detected",
            AttentionState.NEEDS_PERMISSION: "Approval needed",
            AttentionState.NEEDS_CHOICE: "Choice needed",
            AttentionState.NEEDS_INPUT: "Input needed",
            AttentionState.COMPLETED: "Completed",
            AttentionState.RUNNING: "Working...",
        }[state]
