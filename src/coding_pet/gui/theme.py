from __future__ import annotations

import json
import os
import site
import sys
import sysconfig
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
    COMPANY_PET = "company-pet"


@dataclass(slots=True)
class ThemeManifest:
    name: str
    sprites: dict[WidgetMood, Path]
    audio: dict[str, Path]


def default_theme() -> WidgetTheme:
    return WidgetTheme.COMPANY_PET


def default_assets_root() -> Path:
    override = os.environ.get("CODING_PET_ASSETS_DIR")
    if override:
        return Path(override).expanduser().resolve()

    source_root = Path(__file__).resolve().parents[3] / "assets" / "sprites"
    if source_root.exists():
        return source_root

    candidates = [
        Path(sysconfig.get_path("data")) / "share" / "coding-pet" / "assets" / "sprites",
        Path(site.getuserbase()) / "share" / "coding-pet" / "assets" / "sprites",
        Path(sys.prefix) / "share" / "coding-pet" / "assets" / "sprites",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def default_theme_manifest_path(assets_root: Path | None = None) -> Path:
    return (assets_root or default_assets_root()) / "theme-manifest.json"


def is_image_sprite(path: Path) -> bool:
    return path.suffix.lower() == ".png"


def _manifest_asset_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"theme asset path must stay within assets root: {value}")
    return path


def classic_theme_manifest() -> ThemeManifest:
    return ThemeManifest(
        name=WidgetTheme.CLASSIC.value,
        sprites={mood: Path(f"classic/{mood.value}.txt") for mood in WidgetMood},
        audio={
            "alert": Path("classic/alert.txt"),
            "celebrate": Path("classic/celebrate.txt"),
        },
    )


def load_theme_manifest(path: Path) -> ThemeManifest:
    raw = json.loads(path.read_text("utf-8"))
    sprites = {
        WidgetMood(key): _manifest_asset_path(value)
        for key, value in raw["sprites"].items()
    }
    audio = {key: _manifest_asset_path(value) for key, value in raw.get("audio", {}).items()}
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
