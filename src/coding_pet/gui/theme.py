from __future__ import annotations

from enum import StrEnum

from coding_pet.models import AttentionState, SessionStatus


class WidgetMood(StrEnum):
    IDLE = "idle"
    TYPING = "typing"
    CELEBRATE = "celebrate"
    ALERT = "alert"
    THINKING = "thinking"
    SLEEPY = "sleepy"
    SAD = "sad"


class WidgetTheme(StrEnum):
    CLASSIC = "classic"


def default_theme() -> WidgetTheme:
    return WidgetTheme.CLASSIC


def mood_for_status(status: SessionStatus) -> WidgetMood:
    if status.state is AttentionState.IDLE:
        return WidgetMood.IDLE
    if status.state is AttentionState.RUNNING:
        return WidgetMood.TYPING
    if status.state in {AttentionState.NEEDS_PERMISSION, AttentionState.NEEDS_INPUT}:
        return WidgetMood.ALERT
    if status.state is AttentionState.REVIEW_NEEDED:
        return WidgetMood.THINKING
    if status.state is AttentionState.STALLED:
        return WidgetMood.SLEEPY
    if status.state is AttentionState.COMPLETED:
        return WidgetMood.CELEBRATE
    return WidgetMood.SAD
