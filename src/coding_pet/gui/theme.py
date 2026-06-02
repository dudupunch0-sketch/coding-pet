from __future__ import annotations

import json
import os
import re
import shutil
import site
import stat
import struct
import sys
import sysconfig
import tempfile
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Any

from coding_pet.models import AttentionState, SessionStatus


class WidgetMood(StrEnum):
    IDLE = "idle"
    TYPING = "typing"
    CELEBRATE = "celebrate"
    ALERT = "alert"
    THINKING = "thinking"
    SLEEPY = "sleepy"
    SAD = "sad"


OFFICIAL_CODEX_PET_STATE_ROWS: tuple[str, ...] = (
    "idle",
    "running_right",
    "running_left",
    "waving",
    "jumping",
    "failed",
    "waiting",
    "running",
    "review",
)

OFFICIAL_CODEX_PET_ROW_FRAME_COUNTS: dict[int, int] = {
    0: 6,
    1: 8,
    2: 8,
    3: 4,
    4: 5,
    5: 8,
    6: 6,
    7: 6,
    8: 6,
}

OFFICIAL_CODEX_PET_ROW_DURATIONS_MS: dict[int, tuple[int, ...]] = {
    0: (280, 110, 110, 140, 140, 320),
    1: (120, 120, 120, 120, 120, 120, 120, 220),
    2: (120, 120, 120, 120, 120, 120, 120, 220),
    3: (140, 140, 140, 280),
    4: (140, 140, 140, 140, 280),
    5: (140, 140, 140, 140, 140, 140, 140, 240),
    6: (150, 150, 150, 150, 150, 260),
    7: (120, 120, 120, 120, 120, 220),
    8: (150, 150, 150, 150, 150, 280),
}

PETDEX_STATE_ROWS: tuple[str, ...] = (
    "idle",
    "wave",
    "run",
    "failed",
    "review",
    "jump",
    "extra1",
    "extra2",
)

PETDEX_ROW_FRAME_COUNTS: dict[int, int] = {row: 6 for row in range(len(PETDEX_STATE_ROWS))}
PETDEX_DEFAULT_LOOP_MS = 1100

CODEX_PET_STATE_ROWS = OFFICIAL_CODEX_PET_STATE_ROWS

_CODEX_MOOD_STATE_PREFERENCES: dict[WidgetMood, tuple[str, ...]] = {
    WidgetMood.IDLE: ("idle",),
    WidgetMood.TYPING: ("running", "run", "run_right", "running_right"),
    WidgetMood.CELEBRATE: ("jumping", "jump", "waving", "wave"),
    WidgetMood.ALERT: ("waiting", "wait", "permission", "alert", "review", "wave"),
    WidgetMood.THINKING: ("review", "thinking", "waiting"),
    WidgetMood.SLEEPY: ("idle", "waiting"),
    WidgetMood.SAD: ("failed", "fail", "error"),
}

_SAFE_THEME_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
CODEX_PET_MANIFEST_FILENAMES: tuple[str, ...] = ("pet.json", "petjson.json")
REMOVED_LEGACY_THEME_NAMES: frozenset[str] = frozenset({"company-pet"})


class WidgetTheme(StrEnum):
    CLASSIC = "classic"
    CODEX_DEFAULT = "codex-default"
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
    spritesheet: CodexPetSpritesheet | None = None
    asset_root: Path | None = None


@dataclass(slots=True, frozen=True)
class CodexPetSpritesheet:
    path: Path
    columns: int = 8
    rows: int = 9
    frame_width: int = 192
    frame_height: int = 208
    frames_per_state: int = 6
    frame_duration_ms: int = 183
    row_by_mood: dict[WidgetMood, int] = field(default_factory=dict)
    frame_count_by_row: dict[int, int] = field(default_factory=dict)
    frame_duration_by_row: dict[int, tuple[int, ...]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.row_by_mood:
            object.__setattr__(
                self,
                "row_by_mood",
                _row_by_mood_for_codex_states(OFFICIAL_CODEX_PET_STATE_ROWS),
            )
        if not self.frame_count_by_row:
            object.__setattr__(
                self,
                "frame_count_by_row",
                _default_frame_counts_for_layout(
                    OFFICIAL_CODEX_PET_STATE_ROWS,
                    columns=self.columns,
                    rows=self.rows,
                    fallback=self.frames_per_state,
                ),
            )
        if not self.frame_duration_by_row:
            object.__setattr__(
                self,
                "frame_duration_by_row",
                _default_frame_durations_for_layout(
                    OFFICIAL_CODEX_PET_STATE_ROWS,
                    frame_count_by_row=self.frame_count_by_row,
                    fallback=self.frame_duration_ms,
                ),
            )


@dataclass(slots=True, frozen=True)
class CodexPetFrame:
    x: int
    y: int
    width: int
    height: int
    row: int
    column: int
    frame_count: int


@dataclass(slots=True, frozen=True)
class ImageSize:
    width: int
    height: int
    format: str


@dataclass(slots=True, frozen=True)
class CodexPetAtlasValidation:
    ok: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    transparent_rgb_residue_pixels: int = 0


@dataclass(slots=True, frozen=True)
class CodexPetPackage:
    theme_id: str
    display_name: str
    package_root: Path
    manifest_path: Path
    spritesheet_path: Path
    manifest: ThemeManifest
    image_size: tuple[int, int]
    atlas_validation: CodexPetAtlasValidation | None = None


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
    return WidgetTheme.CODEX_DEFAULT


def configured_theme() -> str:
    return os.environ.get("CODING_PET_THEME", default_theme().value)


def default_codex_pets_root() -> Path:
    override = os.environ.get("CODING_PET_CODEX_PETS_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return (Path(os.path.expanduser("~")) / ".codex" / "pets").resolve()


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


def theme_manifest_path(theme: WidgetTheme | str, assets_root: Path | None = None) -> Path:
    root = assets_root or default_assets_root()
    theme_name = theme.value if isinstance(theme, WidgetTheme) else str(theme)
    if theme_name == WidgetTheme.CODEX_DEFAULT.value:
        return default_theme_manifest_path(root)
    return root / theme_name / "theme-manifest.json"


def is_image_sprite(path: Path) -> bool:
    return path.suffix.lower() in {".png", ".webp"}


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
    if (
        "spritesheetPath" in raw
        or "spritesheet" in raw
        or "spriteSheetPath" in raw
        or "atlas" in raw
    ):
        return load_codex_pet_manifest(path)
    sprites = {
        WidgetMood(key): _manifest_asset_path(value) for key, value in raw["sprites"].items()
    }
    audio = {key: _manifest_asset_path(value) for key, value in raw.get("audio", {}).items()}
    return ThemeManifest(name=raw["theme"], sprites=sprites, audio=audio)


def load_codex_pet_manifest(path: Path) -> ThemeManifest:
    raw = json.loads(path.read_text("utf-8"))
    spritesheet_value = (
        raw.get("spritesheetPath")
        or raw.get("spriteSheetPath")
        or raw.get("spritesheet")
        or raw.get("atlas")
    )
    if isinstance(spritesheet_value, dict):
        spritesheet_value = spritesheet_value.get("path")
    if not isinstance(spritesheet_value, str) or not spritesheet_value:
        raise ValueError("Codex pet manifest requires spritesheetPath")
    spritesheet_path = _manifest_asset_path(spritesheet_value)
    frame_width, frame_height = _codex_frame_size(raw)
    states = _codex_state_names(
        raw,
        manifest_path=path,
        spritesheet_path=spritesheet_path,
        frame_width=frame_width,
        frame_height=frame_height,
    )
    columns = _explicit_positive_int(
        raw,
        ("columns",),
        _default_columns_for_states(states),
        "columns",
    )
    rows = _explicit_positive_int(
        raw,
        ("rows",),
        _default_rows_for_states(states),
        "rows",
    )
    frames_per_state = _explicit_positive_int(
        raw,
        ("framesPerState", "frames_per_state"),
        _default_frames_per_state_for_layout(states, columns=columns),
        "framesPerState",
    )
    frame_duration_ms = _explicit_positive_int(
        raw,
        ("frameDurationMs", "frame_duration_ms"),
        183,
        "frameDurationMs",
    )
    frame_count_by_row = _frame_counts_by_row(
        raw,
        states,
        columns=columns,
        rows=rows,
        fallback=frames_per_state,
    )
    frame_duration_by_row = _frame_durations_by_row(
        raw,
        states,
        rows=rows,
        frame_count_by_row=frame_count_by_row,
        fallback=frame_duration_ms,
    )
    spritesheet = CodexPetSpritesheet(
        path=spritesheet_path,
        columns=columns,
        rows=rows,
        frame_width=frame_width,
        frame_height=frame_height,
        frames_per_state=frames_per_state,
        frame_duration_ms=frame_duration_ms,
        row_by_mood=_row_by_mood_for_codex_states(states),
        frame_count_by_row=frame_count_by_row,
        frame_duration_by_row=frame_duration_by_row,
    )
    return ThemeManifest(
        name=str(raw.get("id") or raw.get("slug") or path.parent.name),
        sprites={},
        audio={},
        spritesheet=spritesheet,
    )


def load_manifest_for_theme(
    theme: WidgetTheme | str,
    *,
    assets_root: Path | None = None,
    pets_root: Path | None = None,
) -> ThemeManifest:
    theme_name = theme.value if isinstance(theme, WidgetTheme) else str(theme)
    if theme_name == WidgetTheme.CLASSIC.value:
        return classic_theme_manifest()
    root = assets_root or default_assets_root()
    pets = pets_root or default_codex_pets_root()
    candidate_paths = [
        theme_manifest_path(theme_name, root),
        root / theme_name / "pet.json",
        root / theme_name / "petjson.json",
        pets / theme_name / "pet.json",
        pets / theme_name / "petjson.json",
    ]
    raw_theme_path = Path(theme_name).expanduser()
    if raw_theme_path.suffix == ".json":
        candidate_paths.insert(0, raw_theme_path)
    elif raw_theme_path.exists():
        candidate_paths.insert(0, raw_theme_path / "pet.json")
        candidate_paths.insert(1, raw_theme_path / "petjson.json")
        candidate_paths.insert(2, raw_theme_path / "theme-manifest.json")
    for candidate in candidate_paths:
        if candidate.exists():
            manifest = load_theme_manifest(candidate)
            manifest.asset_root = (
                candidate.parent if candidate.name in CODEX_PET_MANIFEST_FILENAMES else root
            )
            return manifest
    manifest = load_theme_manifest(candidate_paths[0])
    manifest.asset_root = root
    return manifest


def load_theme_registry(path: Path) -> ThemeRegistry:
    raw = json.loads(path.read_text("utf-8"))
    entries = [
        ThemeRegistryEntry(
            theme=entry["theme"],
            display_name=entry["display_name"],
            manifest=(
                None if entry.get("manifest") is None else _manifest_asset_path(entry["manifest"])
            ),
            source=entry["source"],
            license=entry.get("license"),
        )
        for entry in raw["themes"]
    ]
    return ThemeRegistry(default_theme=raw["default_theme"], themes=entries)


def discover_codex_pet_packages(pets_root: Path | None = None) -> list[ThemeRegistryEntry]:
    root = pets_root or default_codex_pets_root()
    if not root.exists() or not root.is_dir():
        return []
    entries: list[ThemeRegistryEntry] = []
    for pet_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        manifest_path = _codex_pet_manifest_path_or_none(pet_dir)
        if manifest_path is None:
            continue
        try:
            package = validate_codex_pet_package(manifest_path)
        except Exception:
            continue
        entries.append(
            ThemeRegistryEntry(
                theme=package.theme_id,
                display_name=package.display_name,
                manifest=Path(pet_dir.name) / package.manifest_path.name,
                source="codex-pet-package",
            )
        )
    return entries


def discover_theme_choices(
    assets_root: Path | None = None,
    *,
    pets_root: Path | None = None,
) -> ThemeRegistry:
    root = assets_root or default_assets_root()
    try:
        registry = load_theme_registry(default_theme_registry_path(root))
    except Exception:
        registry = ThemeRegistry(default_theme=default_theme().value, themes=[])
    seen = {entry.theme for entry in registry.themes}
    for entry in discover_codex_pet_packages(pets_root):
        if entry.theme not in seen:
            registry.themes.append(entry)
            seen.add(entry.theme)
    return registry


def validate_theme_assets(manifest: ThemeManifest, assets_root: Path) -> list[Path]:
    missing: list[Path] = []
    root = manifest.asset_root or assets_root
    if manifest.spritesheet is not None and not (root / manifest.spritesheet.path).exists():
        missing.append(manifest.spritesheet.path)
    for sprite in manifest.sprites.values():
        if not (root / sprite).exists():
            missing.append(sprite)
    return missing


def validate_codex_pet_package(package_path: Path) -> CodexPetPackage:
    manifest_path = _codex_pet_manifest_path(package_path)
    manifest = load_codex_pet_manifest(manifest_path)
    if manifest.spritesheet is None:
        raise ValueError("Codex pet package requires a spritesheet")
    theme_id = _safe_codex_pet_theme_id(manifest.name)
    spritesheet_path = manifest.spritesheet.path
    if not is_image_sprite(spritesheet_path):
        raise ValueError(f"unsupported spritesheet extension: {spritesheet_path}")
    package_root = manifest_path.parent.resolve()
    if symlink := _first_symlink(package_root):
        relative_symlink = symlink.relative_to(package_root)
        raise ValueError(f"pet package must not contain symlinks: {relative_symlink}")
    missing = validate_theme_assets(manifest, package_root)
    if missing:
        missing_summary = ",".join(path.as_posix() for path in missing)
        raise ValueError(f"missing assets: {missing_summary}")
    actual_size = read_image_size(package_root / spritesheet_path)
    expected_size = expected_codex_pet_atlas_size(manifest.spritesheet)
    if (actual_size.width, actual_size.height) != expected_size:
        actual = f"{actual_size.width}x{actual_size.height}"
        expected = f"{expected_size[0]}x{expected_size[1]}"
        raise ValueError(f"spritesheet size {actual} does not match expected {expected}")
    atlas_validation = validate_codex_pet_atlas_pixels(
        package_root / spritesheet_path,
        manifest.spritesheet,
    )
    if not atlas_validation.ok:
        summary = "; ".join(atlas_validation.errors[:5])
        if len(atlas_validation.errors) > 5:
            summary += f"; ... ({len(atlas_validation.errors)} errors total)"
        raise ValueError(f"spritesheet atlas validation failed: {summary}")
    return CodexPetPackage(
        theme_id=theme_id,
        display_name=_codex_pet_display_name(manifest_path),
        package_root=package_root,
        manifest_path=manifest_path,
        spritesheet_path=spritesheet_path,
        manifest=manifest,
        image_size=(actual_size.width, actual_size.height),
        atlas_validation=atlas_validation,
    )


def import_codex_pet_package(
    package_path: Path,
    *,
    pets_root: Path | None = None,
    replace: bool = False,
) -> CodexPetPackage:
    with codex_pet_package_source(package_path) as package_root:
        package = validate_codex_pet_package(package_root)
        root = (pets_root or default_codex_pets_root()).expanduser().resolve()
        target = (root / package.theme_id).resolve()
        if root != target.parent:
            raise ValueError(f"pet target must stay inside pets root: {target}")
        if target == package.package_root:
            return package
        if target.exists():
            if not replace:
                raise FileExistsError(f"pet package already exists: {target}")
            shutil.rmtree(target)
        root.mkdir(parents=True, exist_ok=True)
        shutil.copytree(package.package_root, target, symlinks=False)
        _ensure_codex_pet_manifest_alias(target)
        return validate_codex_pet_package(target)


@contextmanager
def codex_pet_package_source(package_path: Path) -> Iterator[Path]:
    """Yield a pet package directory, safely extracting ZIP downloads if needed."""
    path = package_path.expanduser()
    if path.suffix.lower() != ".zip":
        yield path
        return

    with tempfile.TemporaryDirectory(prefix="coding-pet-package-") as temp_dir:
        extract_root = Path(temp_dir) / "extracted"
        package_root = _extract_codex_pet_zip(path, extract_root)
        yield package_root


def _extract_codex_pet_zip(zip_path: Path, extract_root: Path) -> Path:
    try:
        with zipfile.ZipFile(zip_path) as archive:
            for info in archive.infolist():
                if _zip_member_is_symlink(info):
                    raise ValueError(f"zip pet package must not contain symlinks: {info.filename}")
                relative_path = _safe_zip_member_path(info.filename)
                if relative_path is None:
                    continue
                target = (extract_root / relative_path).resolve()
                root = extract_root.resolve()
                if not target.is_relative_to(root):
                    raise ValueError(f"zip member escapes package root: {info.filename}")
                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as source, target.open("wb") as destination:
                    shutil.copyfileobj(source, destination)
    except zipfile.BadZipFile as exc:
        raise ValueError(f"invalid zip pet package: {zip_path}") from exc

    manifests = sorted(
        path for path in extract_root.rglob("*.json") if path.name in CODEX_PET_MANIFEST_FILENAMES
    )
    if not manifests:
        raise ValueError("zip pet package must contain pet.json or petjson.json")
    if len(manifests) > 1:
        raise ValueError("zip pet package must contain exactly one pet manifest")
    return manifests[0].parent.resolve()


def _safe_zip_member_path(filename: str) -> Path | None:
    normalized = filename.replace("\\", "/")
    pure_path = PurePosixPath(normalized)
    if pure_path.is_absolute():
        raise ValueError(f"zip member must be a relative path: {filename}")
    parts = tuple(part for part in pure_path.parts if part not in {"", "."})
    if not parts:
        return None
    if any(part == ".." for part in parts):
        raise ValueError(f"zip member escapes package root: {filename}")
    if any(":" in part for part in parts):
        raise ValueError(f"zip member must not contain drive or stream syntax: {filename}")
    return Path(*parts)


def _zip_member_is_symlink(info: zipfile.ZipInfo) -> bool:
    mode = info.external_attr >> 16
    return stat.S_IFMT(mode) == stat.S_IFLNK


def codex_pet_frame_count(spritesheet: CodexPetSpritesheet, mood: WidgetMood) -> int:
    row = spritesheet.row_by_mood.get(mood, 0)
    count = spritesheet.frame_count_by_row.get(row, spritesheet.frames_per_state)
    return max(1, min(count, spritesheet.columns))


def codex_pet_frame_duration_ms(
    spritesheet: CodexPetSpritesheet,
    mood: WidgetMood,
    *,
    frame: int,
) -> int:
    row = min(max(spritesheet.row_by_mood.get(mood, 0), 0), spritesheet.rows - 1)
    frame_count = codex_pet_frame_count(spritesheet, mood)
    column = frame % frame_count
    durations = spritesheet.frame_duration_by_row.get(row, ())
    if column < len(durations):
        return max(1, durations[column])
    return max(1, spritesheet.frame_duration_ms)


def expected_codex_pet_atlas_size(spritesheet: CodexPetSpritesheet) -> tuple[int, int]:
    return (
        spritesheet.columns * spritesheet.frame_width,
        spritesheet.rows * spritesheet.frame_height,
    )


def read_image_size(path: Path) -> ImageSize:
    data = path.read_bytes()
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return _read_png_size(data)
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return _read_webp_size(data)
    raise ValueError(f"unsupported image format: {path.name}")


def validate_codex_pet_atlas_pixels(
    path: Path,
    spritesheet: CodexPetSpritesheet,
    *,
    min_used_pixels: int = 50,
    near_opaque_threshold: float = 0.95,
) -> CodexPetAtlasValidation:
    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover - dependency guard for broken installs
        raise ValueError("Pillow is required to validate Codex pet atlas pixels") from exc

    errors: list[str] = []
    warnings: list[str] = []
    expected_size = expected_codex_pet_atlas_size(spritesheet)
    try:
        with Image.open(path) as opened:
            source_format = opened.format
            source_bands = set(opened.getbands())
            image = opened.convert("RGBA")
    except Exception as exc:  # noqa: BLE001
        return CodexPetAtlasValidation(
            ok=False,
            errors=(f"could not open spritesheet: {exc}",),
            warnings=(),
        )

    if source_format not in {"PNG", "WEBP"}:
        errors.append(f"expected PNG or WebP, got {source_format or 'unknown'}")
    if image.size != expected_size:
        errors.append(
            f"expected {expected_size[0]}x{expected_size[1]}, got {image.width}x{image.height}"
        )
    if "A" not in source_bands:
        errors.append("spritesheet does not have an alpha channel")

    transparent_rgb_residue = _transparent_rgb_residue_count(image)
    if transparent_rgb_residue:
        warnings.append(
            "spritesheet has "
            f"{transparent_rgb_residue} fully transparent pixels with non-zero RGB residue"
        )

    cell_area = spritesheet.frame_width * spritesheet.frame_height
    near_opaque_by_row: dict[str, int] = {}
    for row in range(spritesheet.rows):
        frame_count = spritesheet.frame_count_by_row.get(row, spritesheet.frames_per_state)
        frame_count = max(1, min(frame_count, spritesheet.columns))
        row_label = _codex_state_label_for_row(spritesheet, row)
        for column in range(spritesheet.columns):
            left = column * spritesheet.frame_width
            top = row * spritesheet.frame_height
            cell = image.crop(
                (left, top, left + spritesheet.frame_width, top + spritesheet.frame_height)
            )
            nontransparent = _alpha_nonzero_count(cell)
            used = column < frame_count
            if used and nontransparent < min_used_pixels:
                errors.append(
                    f"{row_label} row {row} column {column} is empty or too sparse "
                    f"({nontransparent} pixels)"
                )
            if used and nontransparent > cell_area * near_opaque_threshold:
                near_opaque_by_row[row_label] = near_opaque_by_row.get(row_label, 0) + 1
            if not used and nontransparent != 0:
                errors.append(
                    f"{row_label} row {row} unused column {column} is not transparent "
                    f"({nontransparent} pixels)"
                )

    for row_label, count in near_opaque_by_row.items():
        errors.append(
            f"{row_label} has {count} nearly opaque used cells; "
            "this usually means the sprite has a non-transparent background"
        )

    return CodexPetAtlasValidation(
        ok=not errors,
        errors=tuple(errors),
        warnings=tuple(warnings),
        transparent_rgb_residue_pixels=transparent_rgb_residue,
    )


def codex_pet_frame_rect(
    spritesheet: CodexPetSpritesheet,
    mood: WidgetMood,
    *,
    frame: int,
) -> CodexPetFrame:
    row = min(max(spritesheet.row_by_mood.get(mood, 0), 0), spritesheet.rows - 1)
    frame_count = codex_pet_frame_count(spritesheet, mood)
    column = frame % frame_count
    return CodexPetFrame(
        x=column * spritesheet.frame_width,
        y=row * spritesheet.frame_height,
        width=spritesheet.frame_width,
        height=spritesheet.frame_height,
        row=row,
        column=column,
        frame_count=frame_count,
    )


def resolve_sprite_for_mood(
    manifest: ThemeManifest,
    mood: WidgetMood,
    *,
    assets_root: Path,
    missing: set[Path] | None = None,
) -> Path:
    missing = missing or set()
    if manifest.spritesheet is not None:
        return manifest.spritesheet.path
    preferred = manifest.sprites[mood]
    if preferred not in missing and (assets_root / preferred).exists():
        return preferred
    fallback = manifest.sprites[WidgetMood.IDLE]
    if fallback in missing:
        return preferred
    return fallback


def _codex_pet_manifest_path(package_path: Path) -> Path:
    path = package_path.expanduser()
    manifest_path = _codex_pet_manifest_path_or_none(path) if path.is_dir() else path
    if manifest_path is None:
        raise ValueError(f"Codex pet manifest not found: {path / 'pet.json'}")
    if manifest_path.name not in CODEX_PET_MANIFEST_FILENAMES:
        raise ValueError("Codex pet package path must be a directory, pet.json, or petjson.json")
    if not manifest_path.exists():
        raise ValueError(f"Codex pet manifest not found: {manifest_path}")
    return manifest_path.resolve()


def _codex_pet_manifest_path_or_none(package_dir: Path) -> Path | None:
    for filename in CODEX_PET_MANIFEST_FILENAMES:
        candidate = package_dir / filename
        if candidate.exists():
            return candidate
    return None


def _ensure_codex_pet_manifest_alias(package_dir: Path) -> None:
    canonical = package_dir / "pet.json"
    alternate = package_dir / "petjson.json"
    if not canonical.exists() and alternate.exists():
        canonical.write_bytes(alternate.read_bytes())


def _safe_codex_pet_theme_id(value: str) -> str:
    theme_id = value.strip()
    if theme_id in {"", ".", ".."} or not _SAFE_THEME_ID.fullmatch(theme_id):
        raise ValueError(f"Codex pet id must be a safe directory name: {value}")
    return theme_id


def _first_symlink(root: Path) -> Path | None:
    for path in root.rglob("*"):
        if path.is_symlink():
            return path
    return None


def _read_png_size(data: bytes) -> ImageSize:
    if len(data) < 24 or data[12:16] != b"IHDR":
        raise ValueError("invalid PNG spritesheet header")
    width, height = struct.unpack(">II", data[16:24])
    return ImageSize(width=width, height=height, format="png")


def _alpha_nonzero_count(image: Any) -> int:
    alpha = image.getchannel("A")
    return sum(alpha.histogram()[1:])


def _transparent_rgb_residue_count(image: Any) -> int:
    data = image.tobytes()
    count = 0
    for index in range(0, len(data), 4):
        red, green, blue, alpha = data[index : index + 4]
        if alpha == 0 and (red or green or blue):
            count += 1
    return count


def _codex_state_label_for_row(spritesheet: CodexPetSpritesheet, row: int) -> str:
    if (
        spritesheet.columns == 8
        and spritesheet.rows == 9
        and spritesheet.frame_width == 192
        and spritesheet.frame_height == 208
        and row < len(OFFICIAL_CODEX_PET_STATE_ROWS)
    ):
        return OFFICIAL_CODEX_PET_STATE_ROWS[row].replace("_", "-")
    if (
        spritesheet.columns == 9
        and spritesheet.rows == 8
        and spritesheet.frame_width == 192
        and spritesheet.frame_height == 208
        and row < len(PETDEX_STATE_ROWS)
    ):
        return PETDEX_STATE_ROWS[row]
    return f"row-{row}"


def _read_webp_size(data: bytes) -> ImageSize:
    offset = 12
    while offset + 8 <= len(data):
        chunk_type = data[offset : offset + 4]
        chunk_size = struct.unpack("<I", data[offset + 4 : offset + 8])[0]
        payload_start = offset + 8
        payload_end = payload_start + chunk_size
        if payload_end > len(data):
            raise ValueError("invalid WebP spritesheet chunk")
        payload = data[payload_start:payload_end]
        if chunk_type == b"VP8X":
            return _read_webp_vp8x_size(payload)
        if chunk_type == b"VP8 ":
            return _read_webp_vp8_size(payload)
        if chunk_type == b"VP8L":
            return _read_webp_vp8l_size(payload)
        offset = payload_end + (chunk_size % 2)
    raise ValueError("invalid WebP spritesheet header")


def _read_webp_vp8x_size(payload: bytes) -> ImageSize:
    if len(payload) < 10:
        raise ValueError("invalid WebP VP8X header")
    width = int.from_bytes(payload[4:7], "little") + 1
    height = int.from_bytes(payload[7:10], "little") + 1
    return ImageSize(width=width, height=height, format="webp")


def _read_webp_vp8_size(payload: bytes) -> ImageSize:
    if len(payload) < 10 or payload[3:6] != b"\x9d\x01\x2a":
        raise ValueError("invalid WebP VP8 header")
    width = struct.unpack("<H", payload[6:8])[0] & 0x3FFF
    height = struct.unpack("<H", payload[8:10])[0] & 0x3FFF
    return ImageSize(width=width, height=height, format="webp")


def _read_webp_vp8l_size(payload: bytes) -> ImageSize:
    if len(payload) < 5 or payload[0] != 0x2F:
        raise ValueError("invalid WebP VP8L header")
    bits = int.from_bytes(payload[1:5], "little")
    width = (bits & 0x3FFF) + 1
    height = ((bits >> 14) & 0x3FFF) + 1
    return ImageSize(width=width, height=height, format="webp")


def _normalize_state_name(value: str) -> str:
    return value.strip().lower().replace("-", "_").replace(" ", "_")


def _normalized_states(states: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(_normalize_state_name(state) for state in states)


def _codex_state_names(
    raw: dict[str, object],
    *,
    manifest_path: Path,
    spritesheet_path: Path,
    frame_width: int,
    frame_height: int,
) -> tuple[str, ...]:
    explicit = _explicit_codex_state_names(raw)
    if explicit:
        return explicit
    explicit_columns = _optional_positive_int(raw.get("columns"))
    explicit_rows = _optional_positive_int(raw.get("rows"))
    if explicit_columns == 9 and explicit_rows == 8:
        return PETDEX_STATE_ROWS
    if explicit_columns == 8 and explicit_rows == 9:
        return OFFICIAL_CODEX_PET_STATE_ROWS
    if explicit_columns is None and explicit_rows is None:
        inferred = _infer_codex_state_names_from_atlas_size(
            manifest_path=manifest_path,
            spritesheet_path=spritesheet_path,
            frame_width=frame_width,
            frame_height=frame_height,
        )
        if inferred:
            return inferred
    return OFFICIAL_CODEX_PET_STATE_ROWS


def _explicit_codex_state_names(raw: dict[str, object]) -> tuple[str, ...]:
    states = raw.get("states") or raw.get("animations") or raw.get("animationStates")
    if isinstance(states, list):
        names = [_normalize_state_name(_state_entry_name(item)) for item in states]
        return tuple(name for name in names if name)
    if isinstance(states, dict):
        return tuple(_normalize_state_name(name) for name in states)
    return ()


def _infer_codex_state_names_from_atlas_size(
    *,
    manifest_path: Path,
    spritesheet_path: Path,
    frame_width: int,
    frame_height: int,
) -> tuple[str, ...]:
    atlas_path = manifest_path.parent / spritesheet_path
    if not atlas_path.is_file():
        return ()
    try:
        image_size = read_image_size(atlas_path)
    except (OSError, ValueError):
        return ()
    if image_size.width == 9 * frame_width and image_size.height == 8 * frame_height:
        return PETDEX_STATE_ROWS
    if image_size.width == 8 * frame_width and image_size.height == 9 * frame_height:
        return OFFICIAL_CODEX_PET_STATE_ROWS
    return ()


def _state_entry_name(item: object) -> str:
    if not isinstance(item, dict):
        return str(item)
    for key in ("name", "id", "key", "state", "slug"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return ""


def _default_columns_for_states(states: tuple[str, ...]) -> int:
    if _normalized_states(states) == _normalized_states(PETDEX_STATE_ROWS):
        return 9
    return 8


def _default_rows_for_states(states: tuple[str, ...]) -> int:
    return len(states) if states else 9


def _default_frames_per_state_for_layout(states: tuple[str, ...], *, columns: int) -> int:
    if _normalized_states(states) == _normalized_states(PETDEX_STATE_ROWS):
        return min(6, columns)
    return min(6, columns)


def _frame_counts_by_row(
    raw: dict[str, object],
    states: tuple[str, ...],
    *,
    columns: int,
    rows: int,
    fallback: int,
) -> dict[int, int]:
    explicit = _explicit_frame_counts_by_row(raw, states)
    if explicit:
        return {row: max(1, min(count, columns)) for row, count in explicit.items()}
    return _default_frame_counts_for_layout(states, columns=columns, rows=rows, fallback=fallback)


def _default_frame_counts_for_layout(
    states: tuple[str, ...],
    *,
    columns: int,
    rows: int,
    fallback: int,
) -> dict[int, int]:
    normalized = _normalized_states(states)
    if normalized == _normalized_states(OFFICIAL_CODEX_PET_STATE_ROWS):
        return {
            row: max(1, min(OFFICIAL_CODEX_PET_ROW_FRAME_COUNTS.get(row, fallback), columns))
            for row in range(rows)
        }
    if normalized == _normalized_states(PETDEX_STATE_ROWS):
        return {
            row: max(1, min(PETDEX_ROW_FRAME_COUNTS.get(row, fallback), columns))
            for row in range(rows)
        }
    return {row: max(1, min(fallback, columns)) for row in range(rows)}


def _frame_durations_by_row(
    raw: dict[str, object],
    states: tuple[str, ...],
    *,
    rows: int,
    frame_count_by_row: dict[int, int],
    fallback: int,
) -> dict[int, tuple[int, ...]]:
    default_durations = _default_frame_durations_for_layout(
        states,
        frame_count_by_row=frame_count_by_row,
        fallback=fallback,
    )
    explicit = _explicit_frame_durations_by_row(raw, states)
    if explicit:
        for row, durations in explicit.items():
            if row < 0 or row >= rows:
                continue
            default_durations[row] = _normalize_frame_durations(
                durations,
                count=frame_count_by_row.get(row, 1),
                fallback=fallback,
            )
    return default_durations


def _default_frame_durations_for_layout(
    states: tuple[str, ...],
    *,
    frame_count_by_row: dict[int, int],
    fallback: int,
) -> dict[int, tuple[int, ...]]:
    normalized = _normalized_states(states)
    if normalized == _normalized_states(OFFICIAL_CODEX_PET_STATE_ROWS):
        return {
            row: _normalize_frame_durations(
                OFFICIAL_CODEX_PET_ROW_DURATIONS_MS.get(row),
                count=count,
                fallback=fallback,
            )
            for row, count in frame_count_by_row.items()
        }
    if normalized == _normalized_states(PETDEX_STATE_ROWS):
        return {
            row: _even_loop_durations(PETDEX_DEFAULT_LOOP_MS, count=count)
            for row, count in frame_count_by_row.items()
        }
    return {
        row: _normalize_frame_durations(None, count=count, fallback=fallback)
        for row, count in frame_count_by_row.items()
    }


def _even_loop_durations(total_ms: int, *, count: int) -> tuple[int, ...]:
    safe_count = max(1, count)
    safe_total = max(safe_count, total_ms)
    base = safe_total // safe_count
    remainder = safe_total % safe_count
    return tuple(base + 1 if index < remainder else base for index in range(safe_count))


def _explicit_frame_durations_by_row(
    raw: dict[str, object],
    states: tuple[str, ...],
) -> dict[int, tuple[int, ...]]:
    durations: dict[int, tuple[int, ...]] = {}
    raw_durations = (
        raw.get("frameDurations") or raw.get("frame_durations") or raw.get("rowFrameDurations")
    )
    if isinstance(raw_durations, list):
        for row, value in enumerate(raw_durations):
            parsed = _duration_tuple(value)
            if parsed:
                durations[row] = parsed
    if isinstance(raw_durations, dict):
        normalized_index = {
            _normalize_state_name(state): index for index, state in enumerate(states)
        }
        for key, value in raw_durations.items():
            parsed = _duration_tuple(value)
            if not parsed:
                continue
            if isinstance(key, str) and key.isdecimal():
                durations[int(key)] = parsed
                continue
            if isinstance(key, str):
                state_row = normalized_index.get(_normalize_state_name(key))
                if state_row is not None:
                    durations[state_row] = parsed
    state_entries = raw.get("states") or raw.get("animations") or raw.get("animationStates")
    if isinstance(state_entries, list):
        for row, item in enumerate(state_entries):
            if not isinstance(item, dict):
                continue
            value = (
                item.get("frameDurations")
                or item.get("frame_durations")
                or item.get("durations")
                or item.get("durationMs")
                or item.get("frameDurationMs")
            )
            parsed = _duration_tuple(value)
            if parsed:
                durations[row] = parsed
    return durations


def _duration_tuple(value: object) -> tuple[int, ...]:
    if isinstance(value, int) and value > 0:
        return (value,)
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, int) and item > 0)


def _normalize_frame_durations(
    durations: tuple[int, ...] | None,
    *,
    count: int,
    fallback: int,
) -> tuple[int, ...]:
    safe_count = max(1, count)
    safe_fallback = max(1, fallback)
    if not durations:
        return tuple(safe_fallback for _ in range(safe_count))
    if len(durations) >= safe_count:
        return tuple(max(1, value) for value in durations[:safe_count])
    tail = durations[-1]
    return tuple(max(1, value) for value in durations) + tuple(
        max(1, tail) for _ in range(safe_count - len(durations))
    )


def _explicit_frame_counts_by_row(
    raw: dict[str, object],
    states: tuple[str, ...],
) -> dict[int, int]:
    counts: dict[int, int] = {}
    raw_counts = raw.get("frameCounts") or raw.get("frame_counts") or raw.get("rowFrameCounts")
    if isinstance(raw_counts, list):
        for row, value in enumerate(raw_counts):
            if isinstance(value, int) and value > 0:
                counts[row] = value
    if isinstance(raw_counts, dict):
        normalized_index = {
            _normalize_state_name(state): index for index, state in enumerate(states)
        }
        for key, value in raw_counts.items():
            if not isinstance(value, int) or value <= 0:
                continue
            if isinstance(key, str) and key.isdecimal():
                counts[int(key)] = value
                continue
            if isinstance(key, str):
                state_row = normalized_index.get(_normalize_state_name(key))
                if state_row is not None:
                    counts[state_row] = value
    state_entries = raw.get("states") or raw.get("animations") or raw.get("animationStates")
    if isinstance(state_entries, list):
        for row, item in enumerate(state_entries):
            if not isinstance(item, dict):
                continue
            value = item.get("frameCount") or item.get("frames") or item.get("frame_count")
            if isinstance(value, int) and value > 0:
                counts[row] = value
    return counts


def _codex_pet_display_name(manifest_path: Path) -> str:
    raw = json.loads(manifest_path.read_text("utf-8"))
    value = raw.get("displayName") or raw.get("name") or raw.get("id") or manifest_path.parent.name
    return str(value)


def _codex_frame_size(raw: dict[str, object]) -> tuple[int, int]:
    frame = raw.get("frame")
    if isinstance(frame, dict):
        return (
            _explicit_positive_int(frame, ("width",), 192, "frame.width"),
            _explicit_positive_int(frame, ("height",), 208, "frame.height"),
        )
    return (
        _explicit_positive_int(raw, ("frameWidth", "frame_width"), 192, "frameWidth"),
        _explicit_positive_int(raw, ("frameHeight", "frame_height"), 208, "frameHeight"),
    )


def _explicit_positive_int(
    raw: dict[str, object],
    keys: tuple[str, ...],
    default: int,
    label: str,
) -> int:
    for key in keys:
        if key not in raw:
            continue
        value = raw[key]
        if isinstance(value, int) and value > 0:
            return value
        raise ValueError(f"{label} must be a positive integer")
    return default


def _positive_int(value: object, default: int) -> int:
    if isinstance(value, int) and value > 0:
        return value
    return default


def _optional_positive_int(value: object) -> int | None:
    if isinstance(value, int) and value > 0:
        return value
    return None


def _row_by_mood_for_codex_states(states: tuple[str, ...]) -> dict[WidgetMood, int]:
    normalized = [_normalize_state_name(state) for state in states]
    row_by_mood: dict[WidgetMood, int] = {}
    for mood, preferred_states in _CODEX_MOOD_STATE_PREFERENCES.items():
        for state in preferred_states:
            if state in normalized:
                row_by_mood[mood] = normalized.index(state)
                break
        else:
            row_by_mood[mood] = 0
    return row_by_mood


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
