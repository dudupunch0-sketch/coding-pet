from __future__ import annotations

import json
import tomllib
from datetime import UTC, datetime
from pathlib import Path

import pytest

import coding_pet.gui.theme as theme_module
from coding_pet.gui.theme import (
    WidgetMood,
    WidgetTheme,
    default_assets_root,
    default_theme_manifest_path,
    is_image_sprite,
    load_theme_manifest,
    resolve_sprite_for_mood,
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


def test_theme_manifest_loads_company_safe_png_theme() -> None:
    assets_root = default_assets_root()
    manifest = load_theme_manifest(default_theme_manifest_path(assets_root))

    assert manifest.name == WidgetTheme.COMPANY_PET.value
    assert manifest.sprites[WidgetMood.ALERT].as_posix().endswith("company-pet/alert.png")
    assert is_image_sprite(manifest.sprites[WidgetMood.ALERT]) is True


def test_theme_manifest_rejects_paths_outside_assets_root(tmp_path: Path) -> None:
    manifest_path = tmp_path / "theme-manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "theme": "company-pet",
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


def test_required_mood_assets_exist_for_all_production_states() -> None:
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
        missing={Path("company-pet/alert.png")},
    )

    assert sprite.name == "idle.png"


def test_packaging_includes_sprite_assets_for_installed_runtime() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text("utf-8"))
    hatch = pyproject["tool"]["hatch"]["build"]["targets"]

    assert "/assets" in hatch["sdist"]["include"]
    assert hatch["wheel"]["shared-data"]["assets"] == "share/coding-pet/assets"


def test_widget_shell_resolves_png_sprite_without_qt_runtime() -> None:
    shell = CodingPetWidgetShell(
        status=build_status("needs-input", AttentionState.NEEDS_INPUT),
        theme=WidgetTheme.COMPANY_PET,
    )

    sprite = shell.sprite_asset_path("alert")

    assert sprite is not None
    assert sprite.is_absolute()
    assert sprite.name == "alert.png"
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
        theme=WidgetTheme.COMPANY_PET,
    )

    assert shell.presentation().mood == "idle"
    assert shell.sprite_asset_path("idle") is None
