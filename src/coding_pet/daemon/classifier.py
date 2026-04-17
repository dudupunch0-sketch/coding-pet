from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from coding_pet.events import SessionEvent, SessionEventType
from coding_pet.models import AgentKind, AttentionState


@dataclass(slots=True)
class ClassifierInput:
    agent_kind: AgentKind
    line: str
    observed_at: datetime


class OutputClassifier:
    def __init__(self, *, stall_timeout: timedelta = timedelta(minutes=5)) -> None:
        self.stall_timeout = stall_timeout
        self._patterns: dict[AttentionState, tuple[re.Pattern[str], ...]] = {
            AttentionState.COMPLETED: (
                re.compile(r"(?i)task completed"),
                re.compile(r"(?i)done\b"),
            ),
            AttentionState.NEEDS_PERMISSION: (
                re.compile(r"(?i)need approval"),
                re.compile(r"(?i)permission required"),
            ),
            AttentionState.NEEDS_INPUT: (
                re.compile(r"(?i)waiting for your input"),
                re.compile(r"(?i)awaiting input"),
            ),
            AttentionState.REVIEW_NEEDED: (
                re.compile(r"(?i)please review"),
                re.compile(r"(?i)review the generated"),
            ),
            AttentionState.FAILED: (
                re.compile(r"(?i)failed"),
                re.compile(r"(?i)error:"),
            ),
        }

    def classify(self, event_input: ClassifierInput) -> SessionEvent | None:
        stripped = event_input.line.strip()
        if not stripped:
            return None

        for state, patterns in self._patterns.items():
            if any(pattern.search(stripped) for pattern in patterns):
                return SessionEvent(
                    session_id="",
                    event_type=SessionEventType.STATE_CHANGED,
                    occurred_at=event_input.observed_at,
                    summary=stripped,
                    state=state,
                )

        return SessionEvent(
            session_id="",
            event_type=SessionEventType.OUTPUT_RECEIVED,
            occurred_at=event_input.observed_at,
            summary=stripped,
            state=AttentionState.RUNNING,
        )

    def classify_stall(
        self,
        *,
        last_output_at: datetime,
        observed_at: datetime,
    ) -> SessionEvent | None:
        if observed_at - last_output_at < self.stall_timeout:
            return None
        return SessionEvent(
            session_id="",
            event_type=SessionEventType.STATE_CHANGED,
            occurred_at=observed_at,
            summary="Session appears stalled",
            state=AttentionState.STALLED,
        )

    def classify_exit(self, *, exit_code: int, observed_at: datetime) -> SessionEvent | None:
        if exit_code == 0:
            return SessionEvent(
                session_id="",
                event_type=SessionEventType.PROCESS_EXITED,
                occurred_at=observed_at,
                summary="Process exited successfully",
                state=AttentionState.COMPLETED,
            )
        return SessionEvent(
            session_id="",
            event_type=SessionEventType.PROCESS_EXITED,
            occurred_at=observed_at,
            summary=f"Process exited with code {exit_code}",
            state=AttentionState.FAILED,
        )
