from __future__ import annotations

import json
from pathlib import Path

from coding_pet.gui.theme import load_theme_manifest, validate_theme_assets


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    manifest_path = root / "assets/sprites/theme-manifest.json"
    manifest = load_theme_manifest(manifest_path)
    missing = validate_theme_assets(manifest, manifest_path.parent)
    output = {
        "theme": manifest.name,
        "missing": [path.as_posix() for path in missing],
        "audio_files": {key: value.as_posix() for key, value in manifest.audio.items()},
    }
    print(json.dumps(output, indent=2))
    if missing:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
