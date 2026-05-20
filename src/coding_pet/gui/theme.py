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
    PMD_BULBASAUR = "pmd-bulbasaur"
    PMD_CHARMANDER = "pmd-charmander"
    PMD_SQUIRTLE = "pmd-squirtle"
    PMD_PIKACHU = "pmd-pikachu"
    PMD_JIGGLYPUFF = "pmd-jigglypuff"
    PMD_MEOWTH = "pmd-meowth"
    PMD_MACHOP = "pmd-machop"
    PMD_EEVEE = "pmd-eevee"
    PMD_CHIKORITA = "pmd-chikorita"
    PMD_CYNDAQUIL = "pmd-cyndaquil"
    PMD_TOTODILE = "pmd-totodile"
    PMD_PICHU = "pmd-pichu"
    PMD_UMBREON = "pmd-umbreon"
    PMD_MURKROW = "pmd-murkrow"
    PMD_SNEASEL = "pmd-sneasel"
    PMD_TREECKO = "pmd-treecko"
    PMD_TORCHIC = "pmd-torchic"
    PMD_MUDKIP = "pmd-mudkip"
    PMD_RALTS = "pmd-ralts"
    PMD_SKITTY = "pmd-skitty"


PMD_SPRITE_THEMES: tuple[WidgetTheme, ...] = (
    WidgetTheme.PMD_BULBASAUR,
    WidgetTheme.PMD_CHARMANDER,
    WidgetTheme.PMD_SQUIRTLE,
    WidgetTheme.PMD_PIKACHU,
    WidgetTheme.PMD_JIGGLYPUFF,
    WidgetTheme.PMD_MEOWTH,
    WidgetTheme.PMD_MACHOP,
    WidgetTheme.PMD_EEVEE,
    WidgetTheme.PMD_CHIKORITA,
    WidgetTheme.PMD_CYNDAQUIL,
    WidgetTheme.PMD_TOTODILE,
    WidgetTheme.PMD_PICHU,
    WidgetTheme.PMD_UMBREON,
    WidgetTheme.PMD_MURKROW,
    WidgetTheme.PMD_SNEASEL,
    WidgetTheme.PMD_TREECKO,
    WidgetTheme.PMD_TORCHIC,
    WidgetTheme.PMD_MUDKIP,
    WidgetTheme.PMD_RALTS,
    WidgetTheme.PMD_SKITTY,
)


@dataclass(slots=True)
class ThemeManifest:
    name: str
    sprites: dict[WidgetMood, Path]
    audio: dict[str, Path]


@dataclass(slots=True, frozen=True)
class ThemeRegistryEntry:
    theme: str
    display_name: str
    manifest: Path | None
    source: str
    license: str | None = None


@dataclass(slots=True)
class ThemeRegistry:
    default_theme: str
    themes: list[ThemeRegistryEntry]


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


def default_theme_registry_path(assets_root: Path | None = None) -> Path:
    return (assets_root or default_assets_root()) / "theme-registry.json"


def theme_manifest_path(theme: WidgetTheme, assets_root: Path | None = None) -> Path:
    root = assets_root or default_assets_root()
    if theme is WidgetTheme.COMPANY_PET:
        return default_theme_manifest_path(root)
    return root / theme.value / "theme-manifest.json"


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


def load_manifest_for_theme(
    theme: WidgetTheme,
    *,
    assets_root: Path | None = None,
) -> ThemeManifest:
    if theme is WidgetTheme.CLASSIC:
        return classic_theme_manifest()
    return load_theme_manifest(theme_manifest_path(theme, assets_root))


def load_theme_registry(path: Path) -> ThemeRegistry:
    raw = json.loads(path.read_text("utf-8"))
    entries = [
        ThemeRegistryEntry(
            theme=entry["theme"],
            display_name=entry["display_name"],
            manifest=(
                None
                if entry.get("manifest") is None
                else _manifest_asset_path(entry["manifest"])
            ),
            source=entry["source"],
            license=entry.get("license"),
        )
        for entry in raw["themes"]
    ]
    return ThemeRegistry(default_theme=raw["default_theme"], themes=entries)


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
