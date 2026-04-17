from __future__ import annotations

from datetime import UTC, datetime, timedelta

from coding_pet.daemon.classifier import ClassifierInput, OutputClassifier
from coding_pet.events import SessionEventType
from coding_pet.models import AgentKind, AttentionState


def test_classifier_detects_completion_from_claude_code_output() -> None:
    classifier = OutputClassifier()

    event = classifier.classify(
        ClassifierInput(
            agent_kind=AgentKind.CLAUDE_CODE,
            line="Task completed successfully.",
            observed_at=datetime.now(UTC),
        )
    )

    assert event is not None
    assert event.event_type is SessionEventType.STATE_CHANGED
    assert event.state is AttentionState.COMPLETED


def test_classifier_detects_permission_request() -> None:
    classifier = OutputClassifier()

    event = classifier.classify(
        ClassifierInput(
            agent_kind=AgentKind.OPENCODE,
            line="Need approval before deleting files.",
            observed_at=datetime.now(UTC),
        )
    )

    assert event is not None
    assert event.state is AttentionState.NEEDS_PERMISSION


def test_classifier_detects_input_request() -> None:
    classifier = OutputClassifier()

    event = classifier.classify(
        ClassifierInput(
            agent_kind=AgentKind.CLAUDE_CODE,
            line="Waiting for your input to continue.",
            observed_at=datetime.now(UTC),
        )
    )

    assert event is not None
    assert event.state is AttentionState.NEEDS_INPUT


def test_classifier_detects_review_needed() -> None:
    classifier = OutputClassifier()

    event = classifier.classify(
        ClassifierInput(
            agent_kind=AgentKind.OPENCODE,
            line="Please review the generated patch.",
            observed_at=datetime.now(UTC),
        )
    )

    assert event is not None
    assert event.state is AttentionState.REVIEW_NEEDED


def test_classifier_treats_unmatched_lines_as_running() -> None:
    classifier = OutputClassifier()

    event = classifier.classify(
        ClassifierInput(
            agent_kind=AgentKind.CLAUDE_CODE,
            line="Editing src/app.py...",
            observed_at=datetime.now(UTC),
        )
    )

    assert event is not None
    assert event.state is AttentionState.RUNNING


def test_classifier_detects_stall_after_timeout() -> None:
    classifier = OutputClassifier(stall_timeout=timedelta(seconds=5))
    now = datetime.now(UTC)

    event = classifier.classify_stall(
        last_output_at=now - timedelta(seconds=10),
        observed_at=now,
    )

    assert event is not None
    assert event.state is AttentionState.STALLED


def test_classifier_ignores_stall_before_timeout() -> None:
    classifier = OutputClassifier(stall_timeout=timedelta(seconds=5))
    now = datetime.now(UTC)

    event = classifier.classify_stall(
        last_output_at=now - timedelta(seconds=3),
        observed_at=now,
    )

    assert event is None


def test_classifier_detects_failed_exit() -> None:
    classifier = OutputClassifier()

    event = classifier.classify_exit(exit_code=2, observed_at=datetime.now(UTC))

    assert event is not None
    assert event.state is AttentionState.FAILED
    assert event.event_type is SessionEventType.PROCESS_EXITED
