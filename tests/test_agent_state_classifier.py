from __future__ import annotations

from datetime import UTC, datetime, timedelta

from coding_pet.classifiers.agent_state import AgentStateClassifier
from coding_pet.models import AttentionState

NOW = datetime(2026, 5, 15, 10, 0, tzinfo=UTC)


def decide(text: str, *, changed: bool = True, last_output_delta: int = 0) -> AttentionState:
    classifier = AgentStateClassifier(stalled_after=timedelta(seconds=300))
    return classifier.classify_snapshot(
        text,
        snapshot_changed=changed,
        last_output_at=NOW - timedelta(seconds=last_output_delta),
        observed_at=NOW,
    ).state


def test_classifier_detects_permission_before_choice_or_input() -> None:
    assert (
        decide("Do you want to proceed? Approve this command [1] yes/no")
        is AttentionState.NEEDS_PERMISSION
    )


def test_classifier_detects_numbered_choices() -> None:
    assert decide("Choose an option:\n1) Continue\n2) Cancel") is AttentionState.NEEDS_CHOICE


def test_classifier_detects_korean_input_prompt() -> None:
    assert decide("dev / stage / prod 중 어떤 환경 기준으로 볼까요?") is AttentionState.NEEDS_INPUT


def test_classifier_detects_failures_with_highest_priority() -> None:
    assert decide("Need clarification but Error: command not found") is AttentionState.FAILED


def test_classifier_uses_latest_relevant_scrollback_signal() -> None:
    snapshot = "Do you want to proceed?\nreading files...\nrunning tests"

    assert decide(snapshot) is AttentionState.RUNNING


def test_classifier_allows_later_completion_to_override_stale_prompt() -> None:
    snapshot = "Need clarification: which env?\nprocessing...\ntask completed"

    assert decide(snapshot, changed=False, last_output_delta=301) is AttentionState.COMPLETED


def test_classifier_detects_stalled_only_after_idle_threshold() -> None:
    assert decide("still screen", changed=False, last_output_delta=301) is AttentionState.STALLED
    assert decide("still screen", changed=False, last_output_delta=10) is AttentionState.IDLE


def test_classifier_keeps_completed_snapshots_completed_after_idle_threshold() -> None:
    assert (
        decide("task completed", changed=False, last_output_delta=301)
        is AttentionState.COMPLETED
    )


def test_classifier_returns_waiting_message() -> None:
    classifier = AgentStateClassifier(stalled_after=timedelta(seconds=300))
    decision = classifier.classify_snapshot(
        "logs\nNeed clarification: which env?",
        snapshot_changed=True,
        last_output_at=NOW,
        observed_at=NOW,
    )

    assert decision.state is AttentionState.NEEDS_INPUT
    assert decision.agent_waiting_message == "Need clarification: which env?"
