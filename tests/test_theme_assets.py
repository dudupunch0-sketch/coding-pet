from __future__ import annotations

import json
import tomllib
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

import coding_pet.gui.theme as theme_module
from coding_pet.gui.theme import (
    PMD_SPRITE_THEMES,
    WidgetMood,
    WidgetTheme,
    codex_pet_frame_count,
    codex_pet_frame_duration_ms,
    codex_pet_frame_rect,
    codex_pet_package_source,
    configured_theme,
    default_assets_root,
    default_theme,
    default_theme_manifest_path,
    default_theme_registry_path,
    discover_codex_pet_packages,
    discover_theme_choices,
    expected_codex_pet_atlas_size,
    import_codex_pet_package,
    is_image_sprite,
    load_codex_pet_manifest,
    load_manifest_for_theme,
    load_theme_manifest,
    load_theme_registry,
    resolve_sprite_for_mood,
    validate_codex_pet_atlas_pixels,
    validate_codex_pet_package,
    validate_theme_assets,
)
from coding_pet.gui.widget import CodingPetWidgetShell
from coding_pet.models import AgentKind, AttentionState, SessionStatus


def build_status(session_id: str, state: AttentionState) -> SessionStatus:
    return SessionStatus(
        session_id=session_id,
        agent_kind=AgentKind.CLAUDE_CODE,
        title=session_id,
        workspace=f"/tmp/{session_id}",
        state=state,
        summary=f"{session_id}:{state.value}",
        last_event_at=datetime(2026, 5, 20, tzinfo=UTC),
    )


def write_png_header(path: Path, *, width: int = 1536, height: int = 1872) -> None:
    write_atlas_image(path, width=width, height=height)


def write_webp_header(path: Path, *, width: int = 1536, height: int = 1872) -> None:
    write_atlas_image(path, width=width, height=height)


def write_atlas_image(
    path: Path,
    *,
    width: int = 1536,
    height: int = 1872,
    fill_unused: bool = False,
    opaque_background: bool = False,
) -> None:
    from PIL import Image, ImageDraw

    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    columns = max(1, width // 192)
    rows = max(1, height // 208)
    row_counts = _atlas_test_row_counts(columns=columns, rows=rows)
    for row in range(rows):
        used_columns = columns if fill_unused else row_counts.get(row, min(6, columns))
        for column in range(used_columns):
            if opaque_background:
                left = column * 192
                top = row * 208
                draw.rectangle((left, top, left + 191, top + 207), fill=(24, 24, 24, 255))
            else:
                left = column * 192 + 72
                top = row * 208 + 80
                draw.rectangle((left, top, left + 40, top + 40), fill=(255, 96, 32, 255))
    if path.suffix.lower() == ".webp":
        image.save(path, "WEBP", lossless=True, exact=True)
    else:
        image.save(path, "PNG")


def write_pet_zip(source_dir: Path, archive_path: Path, *, top_level: str | None = None) -> None:
    with zipfile.ZipFile(archive_path, "w") as archive:
        for path in sorted(source_dir.rglob("*")):
            if path.is_dir():
                continue
            relative = path.relative_to(source_dir)
            archive_name = relative.as_posix()
            if top_level is not None:
                archive_name = f"{top_level}/{archive_name}"
            archive.write(path, archive_name)


def _atlas_test_row_counts(*, columns: int, rows: int) -> dict[int, int]:
    if columns == 8 and rows == 9:
        return {
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
    if columns == 9 and rows == 8:
        return {row: 6 for row in range(rows)}
    return {row: min(6, columns) for row in range(rows)}


def test_theme_manifest_loads_codex_default_png_theme() -> None:
    assets_root = default_assets_root()
    manifest = load_theme_manifest(default_theme_manifest_path(assets_root))

    assert manifest.name == WidgetTheme.CODEX_DEFAULT.value
    assert default_theme().value == manifest.name
    assert manifest.sprites[WidgetMood.ALERT].as_posix().endswith("codex-default/alert.png")
    assert is_image_sprite(manifest.sprites[WidgetMood.ALERT]) is True


def test_removed_legacy_company_pet_assets_are_not_bundled() -> None:
    assets_root = default_assets_root()
    registry = load_theme_registry(default_theme_registry_path(assets_root))

    assert not (assets_root / "company-pet").exists()
    assert "company-pet" not in {entry.theme for entry in registry.themes}


def test_theme_registry_includes_twenty_spritecollab_character_choices() -> None:
    assets_root = default_assets_root()
    registry = load_theme_registry(default_theme_registry_path(assets_root))
    pmd_entries = [entry for entry in registry.themes if entry.theme.startswith("pmd-")]

    assert registry.default_theme == WidgetTheme.CODEX_DEFAULT.value
    assert len(pmd_entries) == 20
    assert {entry.theme for entry in pmd_entries} == {theme.value for theme in PMD_SPRITE_THEMES}
    assert all(WidgetTheme(entry.theme) in PMD_SPRITE_THEMES for entry in pmd_entries)
    assert all(entry.license == "CC BY-NC 4.0" for entry in pmd_entries)


@pytest.mark.parametrize("widget_theme", PMD_SPRITE_THEMES)
def test_spritecollab_character_theme_assets_exist_for_all_moods(
    widget_theme: WidgetTheme,
) -> None:
    assets_root = default_assets_root()
    manifest = load_manifest_for_theme(widget_theme, assets_root=assets_root)

    assert manifest.name == widget_theme.value
    assert set(manifest.sprites) == set(WidgetMood)
    assert all(is_image_sprite(sprite) for sprite in manifest.sprites.values())
    assert validate_theme_assets(manifest, assets_root) == []


def test_theme_manifest_rejects_paths_outside_assets_root(tmp_path: Path) -> None:
    manifest_path = tmp_path / "theme-manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "theme": "codex-default",
                "sprites": {"idle": "../outside.png"},
                "audio": {"alert": "/tmp/outside.wav"},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="must stay within assets root"):
        load_theme_manifest(manifest_path)


def test_default_assets_root_resolves_checked_in_manifest() -> None:
    assets_root = default_assets_root()

    assert assets_root.is_absolute()
    assert default_theme_manifest_path(assets_root).exists()
    assert default_theme_registry_path(assets_root).exists()


def test_default_assets_root_checks_userbase_shared_data(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source_root = Path(theme_module.__file__).resolve().parents[3] / "assets" / "sprites"
    userbase_assets = tmp_path / "userbase" / "share" / "coding-pet" / "assets" / "sprites"
    userbase_assets.mkdir(parents=True)
    real_exists = Path.exists

    def fake_exists(path: Path) -> bool:
        if path == source_root:
            return False
        return real_exists(path)

    monkeypatch.delenv("CODING_PET_ASSETS_DIR", raising=False)
    monkeypatch.setattr(
        "coding_pet.gui.theme.sysconfig.get_path",
        lambda _name: str(tmp_path / "sys"),
    )
    monkeypatch.setattr("coding_pet.gui.theme.site.getuserbase", lambda: str(tmp_path / "userbase"))
    monkeypatch.setattr(Path, "exists", fake_exists)

    assert default_assets_root() == userbase_assets


def test_required_mood_assets_exist_for_default_production_theme() -> None:
    assets_root = default_assets_root()
    manifest = load_theme_manifest(default_theme_manifest_path(assets_root))

    missing = validate_theme_assets(manifest, assets_root)

    assert missing == []


def test_widget_falls_back_gracefully_if_single_asset_is_missing() -> None:
    assets_root = default_assets_root()
    manifest = load_theme_manifest(default_theme_manifest_path(assets_root))
    sprite = resolve_sprite_for_mood(
        manifest,
        WidgetMood.ALERT,
        assets_root=assets_root,
        missing={Path("codex-default/alert.png")},
    )

    assert sprite.name == "idle.png"


def test_packaging_includes_sprite_assets_for_installed_runtime() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text("utf-8"))
    hatch = pyproject["tool"]["hatch"]["build"]["targets"]

    assert "/assets" in hatch["sdist"]["include"]
    assert hatch["wheel"]["shared-data"]["assets"] == "share/coding-pet/assets"
    assert hatch["wheel"]["shared-data"]["docs"] == "share/coding-pet/docs"
    assert hatch["wheel"]["shared-data"]["requirements"] == "share/coding-pet/requirements"


def test_widget_shell_resolves_codex_default_png_sprite_without_qt_runtime() -> None:
    shell = CodingPetWidgetShell(
        status=build_status("needs-input", AttentionState.NEEDS_INPUT),
        theme=WidgetTheme.CODEX_DEFAULT,
    )

    sprite = shell.sprite_asset_path("alert")

    assert sprite is not None
    assert sprite.is_absolute()
    assert sprite.parts[-2:] == ("codex-default", "alert.png")
    assert is_image_sprite(sprite) is True


def test_widget_shell_resolves_selected_spritecollab_character_without_qt_runtime() -> None:
    shell = CodingPetWidgetShell(
        status=build_status("thinking", AttentionState.NEEDS_CHOICE),
        theme=WidgetTheme.PMD_PIKACHU,
    )

    sprite = shell.sprite_asset_path("thinking")

    assert sprite is not None
    assert sprite.is_absolute()
    assert sprite.parts[-2:] == ("pmd-pikachu", "thinking.png")
    assert is_image_sprite(sprite) is True


def test_widget_shell_respects_classic_text_theme() -> None:
    shell = CodingPetWidgetShell(
        status=build_status("idle", AttentionState.IDLE),
        theme=WidgetTheme.CLASSIC,
    )

    sprite = shell.sprite_asset_path("idle")

    assert sprite is not None
    assert sprite.is_absolute()
    assert sprite.name == "idle.txt"
    assert is_image_sprite(sprite) is False


def test_widget_shell_keeps_text_fallback_when_asset_dir_is_invalid(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("CODING_PET_ASSETS_DIR", str(tmp_path / "missing-assets"))

    shell = CodingPetWidgetShell(
        status=build_status("idle", AttentionState.IDLE),
        theme=WidgetTheme.CODEX_DEFAULT,
    )

    assert shell.presentation().mood == "idle"
    assert shell.sprite_asset_path("idle") is None


def test_codex_pet_manifest_loads_spritesheet_package(tmp_path: Path) -> None:
    pet_dir = tmp_path / "boba"
    pet_dir.mkdir()
    write_webp_header(pet_dir / "spritesheet.webp")
    manifest_path = pet_dir / "pet.json"
    manifest_path.write_text(
        json.dumps(
            {
                "id": "boba",
                "displayName": "Boba",
                "description": "A tiny companion.",
                "spritesheetPath": "spritesheet.webp",
            }
        ),
        encoding="utf-8",
    )

    manifest = load_codex_pet_manifest(manifest_path)

    assert manifest.name == "boba"
    assert manifest.spritesheet is not None
    assert manifest.spritesheet.path == Path("spritesheet.webp")
    assert manifest.spritesheet.columns == 8
    assert manifest.spritesheet.rows == 9
    assert manifest.spritesheet.frame_width == 192
    assert manifest.spritesheet.frame_height == 208
    assert manifest.spritesheet.row_by_mood[WidgetMood.IDLE] == 0
    assert manifest.spritesheet.row_by_mood[WidgetMood.TYPING] == 7
    assert manifest.spritesheet.row_by_mood[WidgetMood.SAD] == 5
    assert manifest.spritesheet.row_by_mood[WidgetMood.ALERT] == 6
    assert manifest.spritesheet.row_by_mood[WidgetMood.THINKING] == 8
    assert manifest.spritesheet.row_by_mood[WidgetMood.CELEBRATE] == 4
    assert codex_pet_frame_count(manifest.spritesheet, WidgetMood.CELEBRATE) == 5
    assert is_image_sprite(manifest.spritesheet.path) is True


def test_codex_pet_frame_rect_uses_official_row_frame_counts(tmp_path: Path) -> None:
    pet_dir = tmp_path / "boba"
    pet_dir.mkdir()
    write_webp_header(pet_dir / "spritesheet.webp")
    (pet_dir / "pet.json").write_text(
        json.dumps({"id": "boba", "displayName": "Boba", "spritesheetPath": "spritesheet.webp"}),
        encoding="utf-8",
    )
    manifest = load_codex_pet_manifest(pet_dir / "pet.json")
    assert manifest.spritesheet is not None

    waiting = codex_pet_frame_rect(manifest.spritesheet, WidgetMood.ALERT, frame=7)
    jumping = codex_pet_frame_rect(manifest.spritesheet, WidgetMood.CELEBRATE, frame=6)

    assert (waiting.x, waiting.y, waiting.width, waiting.height) == (192, 1248, 192, 208)
    assert (waiting.row, waiting.column, waiting.frame_count) == (6, 1, 6)
    assert (jumping.x, jumping.y, jumping.width, jumping.height) == (192, 832, 192, 208)
    assert (jumping.row, jumping.column, jumping.frame_count) == (4, 1, 5)


def test_codex_pet_frame_duration_uses_official_row_timing(tmp_path: Path) -> None:
    pet_dir = tmp_path / "boba"
    pet_dir.mkdir()
    write_webp_header(pet_dir / "spritesheet.webp")
    (pet_dir / "pet.json").write_text(
        json.dumps({"id": "boba", "displayName": "Boba", "spritesheetPath": "spritesheet.webp"}),
        encoding="utf-8",
    )
    manifest = load_codex_pet_manifest(pet_dir / "pet.json")
    assert manifest.spritesheet is not None

    assert codex_pet_frame_duration_ms(manifest.spritesheet, WidgetMood.IDLE, frame=0) == 280
    assert codex_pet_frame_duration_ms(manifest.spritesheet, WidgetMood.IDLE, frame=5) == 320
    assert codex_pet_frame_duration_ms(manifest.spritesheet, WidgetMood.TYPING, frame=5) == 220
    assert codex_pet_frame_duration_ms(manifest.spritesheet, WidgetMood.ALERT, frame=5) == 260
    assert codex_pet_frame_duration_ms(manifest.spritesheet, WidgetMood.THINKING, frame=5) == 280
    assert codex_pet_frame_duration_ms(manifest.spritesheet, WidgetMood.SAD, frame=7) == 240


def test_codex_pet_manifest_accepts_explicit_frame_durations(tmp_path: Path) -> None:
    pet_dir = tmp_path / "timed"
    pet_dir.mkdir()
    write_webp_header(pet_dir / "spritesheet.webp")
    (pet_dir / "pet.json").write_text(
        json.dumps(
            {
                "id": "timed",
                "spritesheetPath": "spritesheet.webp",
                "frameDurations": {
                    "idle": [10, 20, 30],
                    "running": 77,
                },
            }
        ),
        encoding="utf-8",
    )
    manifest = load_codex_pet_manifest(pet_dir / "pet.json")
    assert manifest.spritesheet is not None

    assert [
        codex_pet_frame_duration_ms(manifest.spritesheet, WidgetMood.IDLE, frame=frame)
        for frame in range(6)
    ] == [10, 20, 30, 30, 30, 30]
    assert [
        codex_pet_frame_duration_ms(manifest.spritesheet, WidgetMood.TYPING, frame=frame)
        for frame in range(6)
    ] == [77, 77, 77, 77, 77, 77]
    assert codex_pet_frame_duration_ms(manifest.spritesheet, WidgetMood.ALERT, frame=5) == 260


def test_codex_pet_manifest_accepts_petdex_eight_state_row_contract(tmp_path: Path) -> None:
    pet_dir = tmp_path / "petdex-boba"
    pet_dir.mkdir()
    write_webp_header(pet_dir / "spritesheet.webp", width=1728, height=1664)
    (pet_dir / "pet.json").write_text(
        json.dumps(
            {
                "id": "petdex-boba",
                "displayName": "Petdex Boba",
                "spritesheetPath": "spritesheet.webp",
                "states": [
                    "idle",
                    "wave",
                    "run",
                    "failed",
                    "review",
                    "jump",
                    "extra1",
                    "extra2",
                ],
            }
        ),
        encoding="utf-8",
    )

    manifest = load_codex_pet_manifest(pet_dir / "pet.json")
    assert manifest.spritesheet is not None
    frame = codex_pet_frame_rect(manifest.spritesheet, WidgetMood.TYPING, frame=8)

    assert manifest.spritesheet.columns == 9
    assert manifest.spritesheet.rows == 8
    assert manifest.spritesheet.row_by_mood[WidgetMood.TYPING] == 2
    assert manifest.spritesheet.row_by_mood[WidgetMood.ALERT] == 4
    assert manifest.spritesheet.row_by_mood[WidgetMood.CELEBRATE] == 5
    assert codex_pet_frame_count(manifest.spritesheet, WidgetMood.TYPING) == 6
    assert [
        codex_pet_frame_duration_ms(manifest.spritesheet, WidgetMood.TYPING, frame=frame)
        for frame in range(6)
    ] == [184, 184, 183, 183, 183, 183]
    assert (frame.x, frame.y, frame.width, frame.height) == (384, 416, 192, 208)
    assert (frame.row, frame.column, frame.frame_count) == (2, 2, 6)


def test_codex_pet_manifest_infers_petdex_layout_from_real_atlas_size(
    tmp_path: Path,
) -> None:
    pet_dir = tmp_path / "boba"
    pet_dir.mkdir()
    write_webp_header(pet_dir / "spritesheet.webp", width=1728, height=1664)
    (pet_dir / "pet.json").write_text(
        json.dumps(
            {
                "id": "boba",
                "displayName": "Boba",
                "description": "A Petdex package without explicit state metadata.",
                "spritesheetPath": "spritesheet.webp",
            }
        ),
        encoding="utf-8",
    )

    manifest = load_codex_pet_manifest(pet_dir / "pet.json")

    assert manifest.spritesheet is not None
    assert manifest.spritesheet.columns == 9
    assert manifest.spritesheet.rows == 8
    assert manifest.spritesheet.row_by_mood[WidgetMood.TYPING] == 2
    assert manifest.spritesheet.row_by_mood[WidgetMood.ALERT] == 4
    assert manifest.spritesheet.row_by_mood[WidgetMood.CELEBRATE] == 5
    assert expected_codex_pet_atlas_size(manifest.spritesheet) == (1728, 1664)
    assert [
        codex_pet_frame_duration_ms(manifest.spritesheet, WidgetMood.TYPING, frame=frame)
        for frame in range(codex_pet_frame_count(manifest.spritesheet, WidgetMood.TYPING))
    ] == [184, 184, 183, 183, 183, 183]


def test_codex_pet_manifest_accepts_petdex_state_objects_with_key_fields(
    tmp_path: Path,
) -> None:
    pet_dir = tmp_path / "petdex-object-states"
    pet_dir.mkdir()
    write_webp_header(pet_dir / "spritesheet.webp", width=1728, height=1664)
    (pet_dir / "pet.json").write_text(
        json.dumps(
            {
                "slug": "petdex-object-states",
                "displayName": "Petdex Object States",
                "spritesheetPath": "spritesheet.webp",
                "animationStates": [
                    {"key": "idle"},
                    {"id": "wave"},
                    {"state": "run"},
                    {"slug": "failed"},
                    {"name": "review"},
                    {"key": "jump"},
                    {"key": "extra1"},
                    {"key": "extra2"},
                ],
                "frameDurations": {"run": [99]},
            }
        ),
        encoding="utf-8",
    )

    manifest = load_codex_pet_manifest(pet_dir / "pet.json")

    assert manifest.name == "petdex-object-states"
    assert manifest.spritesheet is not None
    assert manifest.spritesheet.columns == 9
    assert manifest.spritesheet.rows == 8
    assert manifest.spritesheet.row_by_mood[WidgetMood.TYPING] == 2
    assert manifest.spritesheet.row_by_mood[WidgetMood.ALERT] == 4
    assert [
        codex_pet_frame_duration_ms(manifest.spritesheet, WidgetMood.TYPING, frame=frame)
        for frame in range(6)
    ] == [99, 99, 99, 99, 99, 99]


def test_petdex_default_frame_durations_sum_to_1100ms_loop(tmp_path: Path) -> None:
    pet_dir = tmp_path / "petdex-boba"
    pet_dir.mkdir()
    write_webp_header(pet_dir / "spritesheet.webp", width=1728, height=1664)
    (pet_dir / "pet.json").write_text(
        json.dumps(
            {
                "id": "petdex-boba",
                "displayName": "Petdex Boba",
                "spritesheetPath": "spritesheet.webp",
                "states": [
                    "idle",
                    "wave",
                    "run",
                    "failed",
                    "review",
                    "jump",
                    "extra1",
                    "extra2",
                ],
            }
        ),
        encoding="utf-8",
    )

    manifest = load_codex_pet_manifest(pet_dir / "pet.json")

    assert manifest.spritesheet is not None
    durations = [
        codex_pet_frame_duration_ms(manifest.spritesheet, WidgetMood.TYPING, frame=frame)
        for frame in range(codex_pet_frame_count(manifest.spritesheet, WidgetMood.TYPING))
    ]
    assert durations == [184, 184, 183, 183, 183, 183]
    assert sum(durations) == 1100


def test_validate_codex_pet_package_requires_existing_spritesheet(tmp_path: Path) -> None:
    pet_dir = tmp_path / "boba"
    pet_dir.mkdir()
    (pet_dir / "pet.json").write_text(
        json.dumps({"id": "boba", "displayName": "Boba", "spritesheetPath": "missing.webp"}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="missing assets: missing.webp"):
        validate_codex_pet_package(pet_dir)


def test_validate_codex_pet_package_reports_ready_package(tmp_path: Path) -> None:
    pet_dir = tmp_path / "boba"
    pet_dir.mkdir()
    write_webp_header(pet_dir / "spritesheet.webp")
    (pet_dir / "pet.json").write_text(
        json.dumps({"id": "boba", "displayName": "Boba", "spritesheetPath": "spritesheet.webp"}),
        encoding="utf-8",
    )

    package = validate_codex_pet_package(pet_dir)

    assert package.theme_id == "boba"
    assert package.display_name == "Boba"
    assert package.package_root == pet_dir.resolve()
    assert package.manifest_path == (pet_dir / "pet.json").resolve()
    assert package.spritesheet_path == Path("spritesheet.webp")
    assert package.atlas_validation is not None
    assert package.atlas_validation.ok is True


def test_validate_codex_pet_package_accepts_petdex_petjson_filename(
    tmp_path: Path,
) -> None:
    pet_dir = tmp_path / "boba"
    pet_dir.mkdir()
    write_webp_header(pet_dir / "spritesheet.webp")
    (pet_dir / "petjson.json").write_text(
        json.dumps(
            {
                "slug": "boba",
                "displayName": "Boba",
                "spritesheetPath": "spritesheet.webp",
            }
        ),
        encoding="utf-8",
    )

    package = validate_codex_pet_package(pet_dir)

    assert package.theme_id == "boba"
    assert package.manifest_path == (pet_dir / "petjson.json").resolve()
    assert package.display_name == "Boba"


def test_validate_codex_pet_package_warns_for_transparent_rgb_residue(
    tmp_path: Path,
) -> None:
    pet_dir = tmp_path / "boba"
    pet_dir.mkdir()
    write_atlas_image(pet_dir / "spritesheet.png")
    (pet_dir / "pet.json").write_text(
        json.dumps({"id": "boba", "displayName": "Boba", "spritesheetPath": "spritesheet.png"}),
        encoding="utf-8",
    )
    from PIL import Image

    with Image.open(pet_dir / "spritesheet.png") as opened:
        image = opened.convert("RGBA")
    image.putpixel((0, 0), (255, 64, 32, 0))
    image.save(pet_dir / "spritesheet.png", "PNG")

    package = validate_codex_pet_package(pet_dir)

    assert package.atlas_validation is not None
    assert package.atlas_validation.ok is True
    assert package.atlas_validation.transparent_rgb_residue_pixels == 1
    assert any("non-zero RGB residue" in warning for warning in package.atlas_validation.warnings)


def test_validate_codex_pet_package_rejects_sparse_used_cell(tmp_path: Path) -> None:
    pet_dir = tmp_path / "boba"
    pet_dir.mkdir()
    write_atlas_image(pet_dir / "spritesheet.webp")
    (pet_dir / "pet.json").write_text(
        json.dumps({"id": "boba", "displayName": "Boba", "spritesheetPath": "spritesheet.webp"}),
        encoding="utf-8",
    )
    from PIL import Image

    with Image.open(pet_dir / "spritesheet.webp") as opened:
        image = opened.convert("RGBA")
    for y in range(208):
        for x in range(192):
            image.putpixel((x, y), (0, 0, 0, 0))
    image.save(pet_dir / "spritesheet.webp", "WEBP", lossless=True, exact=True)

    with pytest.raises(ValueError, match="idle row 0 column 0 is empty or too sparse"):
        validate_codex_pet_package(pet_dir)


def test_validate_codex_pet_package_rejects_nontransparent_unused_cell(
    tmp_path: Path,
) -> None:
    pet_dir = tmp_path / "boba"
    pet_dir.mkdir()
    write_atlas_image(pet_dir / "spritesheet.webp", fill_unused=True)
    (pet_dir / "pet.json").write_text(
        json.dumps({"id": "boba", "displayName": "Boba", "spritesheetPath": "spritesheet.webp"}),
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="idle row 0 unused column 6 is not transparent",
    ):
        validate_codex_pet_package(pet_dir)


def test_validate_codex_pet_package_rejects_opaque_background(tmp_path: Path) -> None:
    pet_dir = tmp_path / "boba"
    pet_dir.mkdir()
    write_atlas_image(pet_dir / "spritesheet.png", opaque_background=True)
    (pet_dir / "pet.json").write_text(
        json.dumps({"id": "boba", "displayName": "Boba", "spritesheetPath": "spritesheet.png"}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="nearly opaque used cells"):
        validate_codex_pet_package(pet_dir)


def test_validate_codex_pet_atlas_pixels_reports_official_contract_errors(
    tmp_path: Path,
) -> None:
    pet_dir = tmp_path / "boba"
    pet_dir.mkdir()
    write_atlas_image(pet_dir / "spritesheet.png", fill_unused=True)
    (pet_dir / "pet.json").write_text(
        json.dumps({"id": "boba", "displayName": "Boba", "spritesheetPath": "spritesheet.png"}),
        encoding="utf-8",
    )
    manifest = load_codex_pet_manifest(pet_dir / "pet.json")
    assert manifest.spritesheet is not None

    validation = validate_codex_pet_atlas_pixels(
        pet_dir / "spritesheet.png",
        manifest.spritesheet,
    )

    assert validation.ok is False
    assert any("unused column 6 is not transparent" in error for error in validation.errors)


def test_expected_codex_pet_atlas_size_follows_manifest_layout(tmp_path: Path) -> None:
    pet_dir = tmp_path / "boba"
    pet_dir.mkdir()
    write_webp_header(pet_dir / "spritesheet.webp")
    (pet_dir / "pet.json").write_text(
        json.dumps({"id": "boba", "displayName": "Boba", "spritesheetPath": "spritesheet.webp"}),
        encoding="utf-8",
    )
    manifest = load_codex_pet_manifest(pet_dir / "pet.json")
    assert manifest.spritesheet is not None

    assert expected_codex_pet_atlas_size(manifest.spritesheet) == (1536, 1872)


def test_validate_codex_pet_package_rejects_wrong_atlas_size(tmp_path: Path) -> None:
    pet_dir = tmp_path / "boba"
    pet_dir.mkdir()
    write_webp_header(pet_dir / "spritesheet.webp", width=512, height=512)
    (pet_dir / "pet.json").write_text(
        json.dumps({"id": "boba", "displayName": "Boba", "spritesheetPath": "spritesheet.webp"}),
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="spritesheet size 512x512 does not match expected 1536x1872",
    ):
        validate_codex_pet_package(pet_dir)


def test_validate_codex_pet_package_accepts_petdex_atlas_size(tmp_path: Path) -> None:
    pet_dir = tmp_path / "petdex-boba"
    pet_dir.mkdir()
    write_webp_header(pet_dir / "spritesheet.webp", width=1728, height=1664)
    (pet_dir / "pet.json").write_text(
        json.dumps(
            {
                "id": "petdex-boba",
                "displayName": "Petdex Boba",
                "spritesheetPath": "spritesheet.webp",
                "states": [
                    "idle",
                    "wave",
                    "run",
                    "failed",
                    "review",
                    "jump",
                    "extra1",
                    "extra2",
                ],
            }
        ),
        encoding="utf-8",
    )

    package = validate_codex_pet_package(pet_dir)

    assert package.theme_id == "petdex-boba"
    assert package.image_size == (1728, 1664)


def test_validate_codex_pet_package_accepts_petdex_atlas_without_states(
    tmp_path: Path,
) -> None:
    pet_dir = tmp_path / "boba"
    pet_dir.mkdir()
    write_webp_header(pet_dir / "spritesheet.webp", width=1728, height=1664)
    (pet_dir / "pet.json").write_text(
        json.dumps(
            {
                "id": "boba",
                "displayName": "Boba",
                "spritesheetPath": "spritesheet.webp",
            }
        ),
        encoding="utf-8",
    )

    package = validate_codex_pet_package(pet_dir)

    assert package.theme_id == "boba"
    assert package.image_size == (1728, 1664)
    assert package.manifest.spritesheet is not None
    assert package.manifest.spritesheet.columns == 9
    assert package.manifest.spritesheet.rows == 8
    assert package.atlas_validation is not None
    assert package.atlas_validation.ok is True


def test_validate_codex_pet_package_rejects_invalid_explicit_layout_numbers(
    tmp_path: Path,
) -> None:
    pet_dir = tmp_path / "broken-layout"
    pet_dir.mkdir()
    write_webp_header(pet_dir / "spritesheet.webp")
    (pet_dir / "pet.json").write_text(
        json.dumps(
            {
                "id": "broken-layout",
                "displayName": "Broken Layout",
                "spritesheetPath": "spritesheet.webp",
                "columns": 0,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="columns must be a positive integer"):
        validate_codex_pet_package(pet_dir)


def test_validate_codex_pet_package_rejects_invalid_explicit_frame_size(
    tmp_path: Path,
) -> None:
    pet_dir = tmp_path / "broken-frame"
    pet_dir.mkdir()
    write_webp_header(pet_dir / "spritesheet.webp")
    (pet_dir / "pet.json").write_text(
        json.dumps(
            {
                "id": "broken-frame",
                "displayName": "Broken Frame",
                "spritesheetPath": "spritesheet.webp",
                "frame": {"width": 0, "height": 208},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="frame.width must be a positive integer"):
        validate_codex_pet_package(pet_dir)


def test_import_codex_pet_package_copies_valid_package_to_theme_id_dir(tmp_path: Path) -> None:
    source = tmp_path / "download" / "boba"
    source.mkdir(parents=True)
    write_webp_header(source / "spritesheet.webp")
    (source / "README.txt").write_text("download metadata", encoding="utf-8")
    (source / "pet.json").write_text(
        json.dumps({"id": "boba", "displayName": "Boba", "spritesheetPath": "spritesheet.webp"}),
        encoding="utf-8",
    )
    pets_root = tmp_path / "installed"

    imported = import_codex_pet_package(source, pets_root=pets_root)

    assert imported.theme_id == "boba"
    assert imported.package_root == (pets_root / "boba").resolve()
    assert (pets_root / "boba" / "pet.json").exists()
    assert (pets_root / "boba" / "spritesheet.webp").exists()
    assert (pets_root / "boba" / "README.txt").exists()


def test_import_codex_pet_package_accepts_zip_with_single_top_level_dir(tmp_path: Path) -> None:
    source = tmp_path / "download" / "boba"
    source.mkdir(parents=True)
    write_webp_header(source / "spritesheet.webp")
    (source / "pet.json").write_text(
        json.dumps({"id": "boba", "displayName": "Boba", "spritesheetPath": "spritesheet.webp"}),
        encoding="utf-8",
    )
    archive = tmp_path / "boba.zip"
    write_pet_zip(source, archive, top_level="boba")
    pets_root = tmp_path / "installed"

    imported = import_codex_pet_package(archive, pets_root=pets_root)

    assert imported.theme_id == "boba"
    assert imported.package_root == (pets_root / "boba").resolve()
    assert (pets_root / "boba" / "pet.json").exists()
    assert (pets_root / "boba" / "spritesheet.webp").exists()


def test_import_codex_pet_package_normalizes_petdex_petjson_zip(
    tmp_path: Path,
) -> None:
    source = tmp_path / "boba-source"
    source.mkdir()
    write_webp_header(source / "spritesheet.webp")
    (source / "petjson.json").write_text(
        json.dumps(
            {
                "slug": "boba",
                "displayName": "Boba",
                "spritesheetPath": "spritesheet.webp",
            }
        ),
        encoding="utf-8",
    )
    archive = tmp_path / "boba.zip"
    write_pet_zip(source, archive, top_level="boba")
    pets_root = tmp_path / "pets"

    imported = import_codex_pet_package(archive, pets_root=pets_root)

    assert imported.theme_id == "boba"
    assert imported.manifest_path == (pets_root / "boba" / "pet.json").resolve()
    assert (pets_root / "boba" / "pet.json").exists()
    assert (pets_root / "boba" / "petjson.json").exists()


def test_codex_pet_package_source_rejects_zip_path_traversal(tmp_path: Path) -> None:
    archive = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive, "w") as package_zip:
        package_zip.writestr("../pet.json", "{}")

    with pytest.raises(ValueError, match="zip member escapes package root"):
        with codex_pet_package_source(archive):
            pass


def test_import_codex_pet_package_refuses_existing_target_without_replace(
    tmp_path: Path,
) -> None:
    source = tmp_path / "download" / "boba"
    source.mkdir(parents=True)
    write_webp_header(source / "spritesheet.webp")
    (source / "pet.json").write_text(
        json.dumps({"id": "boba", "displayName": "Boba", "spritesheetPath": "spritesheet.webp"}),
        encoding="utf-8",
    )
    target = tmp_path / "installed" / "boba"
    target.mkdir(parents=True)
    (target / "pet.json").write_text("existing", encoding="utf-8")

    with pytest.raises(FileExistsError, match="already exists"):
        import_codex_pet_package(source, pets_root=target.parent)


def test_codex_pet_manifest_accepts_spritesheet_object(tmp_path: Path) -> None:
    pet_dir = tmp_path / "pixel"
    pet_dir.mkdir()
    write_png_header(pet_dir / "atlas.png", width=1536, height=832)
    manifest_path = pet_dir / "pet.json"
    manifest_path.write_text(
        json.dumps(
            {
                "id": "pixel",
                "spritesheet": {"path": "atlas.png"},
                "states": ["idle", "review", "running", "failed"],
            }
        ),
        encoding="utf-8",
    )

    manifest = load_theme_manifest(manifest_path)

    assert manifest.spritesheet is not None
    assert manifest.spritesheet.path == Path("atlas.png")
    assert manifest.spritesheet.row_by_mood[WidgetMood.TYPING] == 2
    assert manifest.spritesheet.row_by_mood[WidgetMood.ALERT] == 1
    assert manifest.spritesheet.row_by_mood[WidgetMood.SAD] == 3


def test_load_manifest_for_theme_discovers_codex_pet_package(tmp_path: Path) -> None:
    pet_dir = tmp_path / "socksy"
    pet_dir.mkdir()
    write_webp_header(pet_dir / "spritesheet.webp")
    (pet_dir / "pet.json").write_text(
        json.dumps(
            {
                "id": "socksy",
                "displayName": "Socksy",
                "description": "A tiny companion.",
                "spritesheetPath": "spritesheet.webp",
            }
        ),
        encoding="utf-8",
    )

    manifest = load_manifest_for_theme("socksy", pets_root=tmp_path)

    assert manifest.name == "socksy"
    assert manifest.asset_root == pet_dir
    assert validate_theme_assets(manifest, pet_dir) == []
    assert resolve_sprite_for_mood(manifest, WidgetMood.TYPING, assets_root=pet_dir) == Path(
        "spritesheet.webp"
    )


def test_load_manifest_for_theme_discovers_petdex_petjson_package(tmp_path: Path) -> None:
    pet_dir = tmp_path / "socksy"
    pet_dir.mkdir()
    write_webp_header(pet_dir / "spritesheet.webp")
    (pet_dir / "petjson.json").write_text(
        json.dumps(
            {
                "slug": "socksy",
                "displayName": "Socksy",
                "spritesheetPath": "spritesheet.webp",
            }
        ),
        encoding="utf-8",
    )

    manifest = load_manifest_for_theme("socksy", pets_root=tmp_path)

    assert manifest.name == "socksy"
    assert manifest.asset_root == pet_dir
    assert validate_theme_assets(manifest, pet_dir) == []


def test_widget_shell_resolves_codex_pet_package_without_qt_runtime(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pet_dir = tmp_path / "tater"
    pet_dir.mkdir()
    write_webp_header(pet_dir / "spritesheet.webp")
    (pet_dir / "pet.json").write_text(
        json.dumps(
            {
                "id": "tater",
                "displayName": "Tater",
                "description": "A tiny companion.",
                "spritesheetPath": "spritesheet.webp",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CODING_PET_CODEX_PETS_DIR", str(tmp_path))

    shell = CodingPetWidgetShell(
        status=build_status("needs-input", AttentionState.NEEDS_INPUT),
        theme="tater",
    )

    sprite = shell.sprite_asset_path("alert")

    assert sprite == (pet_dir / "spritesheet.webp").resolve()


def test_configured_theme_reads_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CODING_PET_THEME", "socksy")

    assert configured_theme() == "socksy"


def test_discover_codex_pet_packages_lists_valid_packages(tmp_path: Path) -> None:
    valid = tmp_path / "boba"
    valid.mkdir()
    write_webp_header(valid / "spritesheet.webp")
    (valid / "pet.json").write_text(
        json.dumps({"id": "boba", "displayName": "Boba", "spritesheetPath": "spritesheet.webp"}),
        encoding="utf-8",
    )
    invalid = tmp_path / "broken"
    invalid.mkdir()
    (invalid / "pet.json").write_text(json.dumps({"id": "broken"}), encoding="utf-8")

    entries = discover_codex_pet_packages(tmp_path)

    assert [(entry.theme, entry.display_name, entry.source) for entry in entries] == [
        ("boba", "Boba", "codex-pet-package")
    ]
    assert entries[0].manifest == Path("boba/pet.json")


def test_discover_theme_choices_merges_bundled_and_codex_pets(tmp_path: Path) -> None:
    pet_dir = tmp_path / "socksy"
    pet_dir.mkdir()
    write_webp_header(pet_dir / "spritesheet.webp")
    (pet_dir / "pet.json").write_text(
        json.dumps(
            {
                "id": "socksy",
                "displayName": "Socksy",
                "spritesheetPath": "spritesheet.webp",
            }
        ),
        encoding="utf-8",
    )

    registry = discover_theme_choices(default_assets_root(), pets_root=tmp_path)

    assert registry.default_theme == WidgetTheme.CODEX_DEFAULT.value
    assert any(entry.theme == WidgetTheme.CODEX_DEFAULT.value for entry in registry.themes)
    assert any(
        entry.theme == "socksy" and entry.source == "codex-pet-package" for entry in registry.themes
    )
