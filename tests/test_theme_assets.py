from __future__ import annotations

from pathlib import Path

from coding_pet.gui.theme import (
    WidgetMood,
    load_theme_manifest,
    resolve_sprite_for_mood,
    validate_theme_assets,
)


def test_theme_manifest_loads_correctly() -> None:
    manifest = load_theme_manifest(Path("assets/sprites/theme-manifest.json"))

    assert manifest.name == "classic"
    assert manifest.sprites[WidgetMood.ALERT].as_posix().endswith("classic/alert.txt")


def test_required_mood_assets_exist_for_all_production_states() -> None:
    manifest = load_theme_manifest(Path("assets/sprites/theme-manifest.json"))

    missing = validate_theme_assets(manifest, Path("assets/sprites"))

    assert missing == []


def test_widget_falls_back_gracefully_if_single_asset_is_missing() -> None:
    manifest = load_theme_manifest(Path("assets/sprites/theme-manifest.json"))
    sprite = resolve_sprite_for_mood(
        manifest,
        WidgetMood.ALERT,
        assets_root=Path("assets/sprites"),
        missing={Path("classic/alert.txt")},
    )

    assert sprite.name == "idle.txt"
