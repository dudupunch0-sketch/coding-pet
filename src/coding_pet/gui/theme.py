from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

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


@dataclass(slots=True)
class ThemeManifest:
    name: str
    sprites: dict[WidgetMood, Path]
    audio: dict[str, Path]


def default_theme() -> WidgetTheme:
    return WidgetTheme.CLASSIC


def load_theme_manifest(path: Path) -> ThemeManifest:
    raw = json.loads(path.read_text("utf-8"))
    sprites = {WidgetMood(key): Path(value) for key, value in raw["sprites"].items()}
    audio = {key: Path(value) for key, value in raw.get("audio", {}).items()}
    return ThemeManifest(name=raw["theme"], sprites=sprites, audio=audio)


def validate_theme_assets(manifest: ThemeManifest, assets_root: Path) -> list[Path]:
    missing: list[Path] = []
    for sprite in manifest.sprites.values():
        if not (assets_root / sprite).exists():
            missing.append(sprite)
    return missing


def resolve_sprite_for_mood(
    manifest: ThemeManifest,
    mood: WidgetMood,
    *,
    assets_root: Path,
    missing: set[Path] | None = None,
) -> Path:
    missing = missing or set()
    preferred = manifest.sprites[mood]
    if preferred not in missing and (assets_root / preferred).exists():
        return preferred
    fallback = manifest.sprites[WidgetMood.IDLE]
    if fallback in missing:
        return preferred
    return fallback


def mood_for_status(status: SessionStatus) -> WidgetMood:
    if status.state is AttentionState.IDLE:
        return WidgetMood.IDLE
    if status.state is AttentionState.RUNNING:
        return WidgetMood.TYPING
    if status.state in {AttentionState.NEEDS_PERMISSION, AttentionState.NEEDS_INPUT}:
        return WidgetMood.ALERT
    if status.state in {AttentionState.NEEDS_CHOICE, AttentionState.REVIEW_NEEDED}:
        return WidgetMood.THINKING
    if status.state is AttentionState.STALLED:
        return WidgetMood.SLEEPY
    if status.state is AttentionState.COMPLETED:
        return WidgetMood.CELEBRATE
    return WidgetMood.SAD
