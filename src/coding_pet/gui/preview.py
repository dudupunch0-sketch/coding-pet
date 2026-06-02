from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from coding_pet.gui.theme import (
    OFFICIAL_CODEX_PET_STATE_ROWS,
    PETDEX_STATE_ROWS,
    CodexPetFrame,
    CodexPetSpritesheet,
    WidgetMood,
    codex_pet_frame_duration_ms,
    codex_pet_frame_rect,
    default_assets_root,
    default_codex_pets_root,
    expected_codex_pet_atlas_size,
    is_image_sprite,
    load_manifest_for_theme,
    resolve_sprite_for_mood,
    validate_theme_assets,
)


class PreviewRenderError(RuntimeError):
    pass


@dataclass(slots=True, frozen=True)
class PetFramePreview:
    theme: str
    mood: WidgetMood
    output_path: Path
    output_size: tuple[int, int]
    source_path: Path
    source_rect: CodexPetFrame | None


@dataclass(slots=True, frozen=True)
class PetContactSheetPreview:
    theme: str
    output_path: Path
    output_size: tuple[int, int]
    source_path: Path
    rows: int
    columns: int
    used_frames: int


@dataclass(slots=True, frozen=True)
class PetAnimationPreviews:
    theme: str
    output_dir: Path
    source_path: Path
    preview_paths: tuple[Path, ...]
    rows: int
    columns: int


def render_pet_frame_preview(
    theme: str,
    *,
    mood: WidgetMood,
    output_path: Path,
    assets_root: Path | None = None,
    pets_root: Path | None = None,
    size: int = 96,
) -> PetFramePreview:
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QColor, QImage, QPainter
    except Exception as exc:  # pragma: no cover - exercised on target envs without Qt
        raise PreviewRenderError("PySide6 is required to render pet frame previews") from exc

    root = assets_root or default_assets_root()
    manifest = load_manifest_for_theme(
        theme,
        assets_root=root,
        pets_root=pets_root or default_codex_pets_root(),
    )
    asset_root = manifest.asset_root or root
    missing = validate_theme_assets(manifest, asset_root)
    if missing:
        missing_summary = ",".join(path.as_posix() for path in missing)
        raise PreviewRenderError(f"theme missing assets: {missing_summary}")

    source_rect: CodexPetFrame | None = None
    if manifest.spritesheet is not None:
        source_path = asset_root / manifest.spritesheet.path
        source_rect = codex_pet_frame_rect(manifest.spritesheet, mood, frame=0)
        source_image = QImage(str(source_path))
        if source_image.isNull():
            raise PreviewRenderError(f"could not decode spritesheet: {source_path}")
        frame_image = source_image.copy(
            source_rect.x,
            source_rect.y,
            source_rect.width,
            source_rect.height,
        )
    else:
        sprite_path = resolve_sprite_for_mood(manifest, mood, assets_root=asset_root)
        source_path = asset_root / sprite_path
        if not is_image_sprite(source_path):
            raise PreviewRenderError(f"theme mood is not an image sprite: {sprite_path}")
        frame_image = QImage(str(source_path))
        if frame_image.isNull():
            raise PreviewRenderError(f"could not decode sprite: {source_path}")

    canvas = QImage(size, size, QImage.Format.Format_ARGB32)
    canvas.fill(QColor(0, 0, 0, 0))
    scaled = frame_image.scaled(
        size,
        size,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.FastTransformation,
    )
    x = (size - scaled.width()) // 2
    y = (size - scaled.height()) // 2
    painter = QPainter(canvas)
    painter.drawImage(x, y, scaled)
    painter.end()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not canvas.save(str(output_path)):
        raise PreviewRenderError(f"could not write preview: {output_path}")
    return PetFramePreview(
        theme=manifest.name,
        mood=mood,
        output_path=output_path,
        output_size=(canvas.width(), canvas.height()),
        source_path=source_path,
        source_rect=source_rect,
    )


def render_pet_contact_sheet(
    theme: str,
    *,
    output_path: Path,
    assets_root: Path | None = None,
    pets_root: Path | None = None,
    cell_width: int = 96,
) -> PetContactSheetPreview:
    try:
        from PIL import Image, ImageDraw
    except ImportError as exc:  # pragma: no cover - dependency guard for broken installs
        raise PreviewRenderError("Pillow is required to render pet contact sheets") from exc

    root = assets_root or default_assets_root()
    manifest = load_manifest_for_theme(
        theme,
        assets_root=root,
        pets_root=pets_root or default_codex_pets_root(),
    )
    asset_root = manifest.asset_root or root
    missing = validate_theme_assets(manifest, asset_root)
    if missing:
        missing_summary = ",".join(path.as_posix() for path in missing)
        raise PreviewRenderError(f"theme missing assets: {missing_summary}")
    if manifest.spritesheet is None:
        raise PreviewRenderError("contact sheets require a Codex pet spritesheet")

    sheet = manifest.spritesheet
    source_path = asset_root / sheet.path
    try:
        with Image.open(source_path) as opened:
            source = opened.convert("RGBA")
    except Exception as exc:  # noqa: BLE001
        raise PreviewRenderError(f"could not decode spritesheet: {source_path}") from exc

    expected_size = expected_codex_pet_atlas_size(sheet)
    if source.size != expected_size:
        raise PreviewRenderError(
            f"spritesheet size {source.width}x{source.height} "
            f"does not match expected {expected_size[0]}x{expected_size[1]}"
        )

    target_cell_width = max(16, cell_width)
    target_cell_height = max(16, round(target_cell_width * sheet.frame_height / sheet.frame_width))
    label_width = max(120, target_cell_width)
    header_height = 28
    gap = 6
    canvas_width = label_width + gap + sheet.columns * (target_cell_width + gap)
    canvas_height = header_height + gap + sheet.rows * (target_cell_height + gap)
    canvas = Image.new("RGBA", (canvas_width, canvas_height), (245, 247, 250, 255))
    draw = ImageDraw.Draw(canvas)
    used_frames = 0

    for column in range(sheet.columns):
        x = label_width + gap + column * (target_cell_width + gap)
        draw.text((x + 4, 6), str(column), fill=(46, 52, 64, 255))

    for row in range(sheet.rows):
        y = header_height + gap + row * (target_cell_height + gap)
        row_label = _contact_sheet_row_label(sheet, row)
        draw.text((8, y + 6), row_label, fill=(46, 52, 64, 255))
        frame_count = max(
            1,
            min(sheet.frame_count_by_row.get(row, sheet.frames_per_state), sheet.columns),
        )
        for column in range(sheet.columns):
            x = label_width + gap + column * (target_cell_width + gap)
            cell = source.crop(
                (
                    column * sheet.frame_width,
                    row * sheet.frame_height,
                    (column + 1) * sheet.frame_width,
                    (row + 1) * sheet.frame_height,
                )
            )
            preview = Image.new("RGBA", (target_cell_width, target_cell_height), (0, 0, 0, 0))
            preview.alpha_composite(_checkerboard(preview.size))
            resized = cell.resize((target_cell_width, target_cell_height), Image.Resampling.NEAREST)
            preview.alpha_composite(resized)
            canvas.alpha_composite(preview, (x, y))
            used = column < frame_count
            used_frames += 1 if used else 0
            outline = (94, 129, 172, 255) if used else (191, 97, 106, 255)
            draw.rectangle(
                (x, y, x + target_cell_width - 1, y + target_cell_height - 1),
                outline=outline,
            )
            if not used:
                draw.line(
                    (x, y, x + target_cell_width - 1, y + target_cell_height - 1),
                    fill=outline,
                )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path, "PNG")
    return PetContactSheetPreview(
        theme=manifest.name,
        output_path=output_path,
        output_size=canvas.size,
        source_path=source_path,
        rows=sheet.rows,
        columns=sheet.columns,
        used_frames=used_frames,
    )


def render_pet_animation_previews(
    theme: str,
    *,
    output_dir: Path,
    assets_root: Path | None = None,
    pets_root: Path | None = None,
    size: int = 96,
) -> PetAnimationPreviews:
    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover - dependency guard for broken installs
        raise PreviewRenderError("Pillow is required to render pet animation previews") from exc

    manifest, asset_root = _load_preview_theme(
        theme,
        assets_root=assets_root,
        pets_root=pets_root,
    )
    if manifest.spritesheet is None:
        raise PreviewRenderError("animation previews require a Codex pet spritesheet")

    sheet = manifest.spritesheet
    source_path = asset_root / sheet.path
    source = _load_spritesheet_image(source_path, sheet)
    frame_size = max(16, size)
    output_dir.mkdir(parents=True, exist_ok=True)
    preview_paths: list[Path] = []

    for row in range(sheet.rows):
        frames = []
        frame_count = max(
            1,
            min(sheet.frame_count_by_row.get(row, sheet.frames_per_state), sheet.columns),
        )
        mood = _mood_for_preview_row(sheet, row)
        durations = [
            _preview_row_frame_duration_ms(sheet, row=row, mood=mood, frame=column)
            for column in range(frame_count)
        ]
        for column in range(frame_count):
            cell = source.crop(
                (
                    column * sheet.frame_width,
                    row * sheet.frame_height,
                    (column + 1) * sheet.frame_width,
                    (row + 1) * sheet.frame_height,
                )
            )
            frame = Image.new("RGBA", (frame_size, frame_size), (0, 0, 0, 0))
            frame.alpha_composite(_checkerboard(frame.size))
            resized = cell.resize((frame_size, frame_size), Image.Resampling.NEAREST)
            frame.alpha_composite(resized)
            frames.append(frame.convert("P", palette=Image.Palette.ADAPTIVE))
        row_label = _contact_sheet_row_label(sheet, row)
        output_path = output_dir / f"{_safe_preview_filename(row_label)}.gif"
        frames[0].save(
            output_path,
            save_all=True,
            append_images=frames[1:],
            duration=durations,
            loop=0,
            disposal=2,
        )
        preview_paths.append(output_path)

    return PetAnimationPreviews(
        theme=manifest.name,
        output_dir=output_dir,
        source_path=source_path,
        preview_paths=tuple(preview_paths),
        rows=sheet.rows,
        columns=sheet.columns,
    )


def _load_preview_theme(
    theme: str,
    *,
    assets_root: Path | None = None,
    pets_root: Path | None = None,
) -> tuple[Any, Path]:
    root = assets_root or default_assets_root()
    manifest = load_manifest_for_theme(
        theme,
        assets_root=root,
        pets_root=pets_root or default_codex_pets_root(),
    )
    asset_root = manifest.asset_root or root
    missing = validate_theme_assets(manifest, asset_root)
    if missing:
        missing_summary = ",".join(path.as_posix() for path in missing)
        raise PreviewRenderError(f"theme missing assets: {missing_summary}")
    return manifest, asset_root


def _load_spritesheet_image(source_path: Path, sheet: CodexPetSpritesheet) -> Any:
    from PIL import Image

    try:
        with Image.open(source_path) as opened:
            source = opened.convert("RGBA")
    except Exception as exc:  # noqa: BLE001
        raise PreviewRenderError(f"could not decode spritesheet: {source_path}") from exc

    expected_size = expected_codex_pet_atlas_size(sheet)
    if source.size != expected_size:
        raise PreviewRenderError(
            f"spritesheet size {source.width}x{source.height} "
            f"does not match expected {expected_size[0]}x{expected_size[1]}"
        )
    return source


def _checkerboard(size: tuple[int, int], *, square: int = 8) -> Any:
    from PIL import Image, ImageDraw

    image = Image.new("RGBA", size, (238, 238, 238, 255))
    draw = ImageDraw.Draw(image)
    for y in range(0, size[1], square):
        for x in range(0, size[0], square):
            if (x // square + y // square) % 2:
                draw.rectangle((x, y, x + square - 1, y + square - 1), fill=(210, 210, 210, 255))
    return image


def _safe_preview_filename(value: str) -> str:
    safe = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in value)
    return safe.strip("-_") or "row"


def _contact_sheet_row_label(spritesheet: CodexPetSpritesheet, row: int) -> str:
    if (
        spritesheet.columns == 8
        and spritesheet.rows == 9
        and row < len(OFFICIAL_CODEX_PET_STATE_ROWS)
    ):
        return OFFICIAL_CODEX_PET_STATE_ROWS[row].replace("_", "-")
    if (
        spritesheet.columns == 9
        and spritesheet.rows == 8
        and row < len(PETDEX_STATE_ROWS)
    ):
        return PETDEX_STATE_ROWS[row]
    return f"row-{row}"


def _mood_for_preview_row(spritesheet: CodexPetSpritesheet, row: int) -> WidgetMood | None:
    for mood, mood_row in spritesheet.row_by_mood.items():
        if mood_row == row:
            return mood
    return None


def _preview_row_frame_duration_ms(
    spritesheet: CodexPetSpritesheet,
    *,
    row: int,
    mood: WidgetMood | None,
    frame: int,
) -> int:
    if mood is not None:
        return codex_pet_frame_duration_ms(spritesheet, mood, frame=frame)
    durations = spritesheet.frame_duration_by_row.get(row, ())
    if frame < len(durations):
        return max(1, durations[frame])
    return max(1, spritesheet.frame_duration_ms)
