from __future__ import annotations

import json
from pathlib import Path

from coding_pet.gui.theme import (
    load_theme_manifest,
    load_theme_registry,
    validate_theme_assets,
)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    assets_root = root / "assets" / "sprites"
    default_manifest_path = assets_root / "theme-manifest.json"
    default_manifest = load_theme_manifest(default_manifest_path)
    default_missing = validate_theme_assets(default_manifest, assets_root)
    registry = load_theme_registry(assets_root / "theme-registry.json")
    missing_by_theme: dict[str, list[str]] = {}
    for entry in registry.themes:
        if entry.manifest is None:
            continue
        manifest = load_theme_manifest(assets_root / entry.manifest)
        missing = validate_theme_assets(manifest, assets_root)
        if missing:
            missing_by_theme[entry.theme] = [path.as_posix() for path in missing]

    spritecollab_themes = sum(1 for entry in registry.themes if entry.theme.startswith("pmd-"))
    output = {
        "theme": default_manifest.name,
        "missing": [path.as_posix() for path in default_missing],
        "audio_files": {key: value.as_posix() for key, value in default_manifest.audio.items()},
        "registered_themes": len(registry.themes),
        "spritecollab_themes": spritecollab_themes,
        "missing_by_theme": missing_by_theme,
    }
    print(json.dumps(output, indent=2))
    if default_missing or missing_by_theme:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
