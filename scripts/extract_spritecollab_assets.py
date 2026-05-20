from __future__ import annotations

import json
import struct
import urllib.request
import zlib
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree

RAW_BASE = "https://raw.githubusercontent.com/PMDCollab/SpriteCollab/master"
MAX_SPRITE_SIZE = 96
CANVAS_SIZE = 128

MOOD_TO_ACTION = {
    "idle": "Idle",
    "typing": "Walk",
    "celebrate": "Pose",
    "alert": "Cringe",
    "thinking": "LookUp",
    "sleepy": "Sleep",
    "sad": "Pain",
}


@dataclass(frozen=True, slots=True)
class SpriteSpec:
    pokedex_id: str
    slug: str
    display_name: str


SPRITES = (
    SpriteSpec("0001", "bulbasaur", "Bulbasaur"),
    SpriteSpec("0004", "charmander", "Charmander"),
    SpriteSpec("0007", "squirtle", "Squirtle"),
    SpriteSpec("0025", "pikachu", "Pikachu"),
    SpriteSpec("0039", "jigglypuff", "Jigglypuff"),
    SpriteSpec("0052", "meowth", "Meowth"),
    SpriteSpec("0066", "machop", "Machop"),
    SpriteSpec("0133", "eevee", "Eevee"),
    SpriteSpec("0152", "chikorita", "Chikorita"),
    SpriteSpec("0155", "cyndaquil", "Cyndaquil"),
    SpriteSpec("0158", "totodile", "Totodile"),
    SpriteSpec("0172", "pichu", "Pichu"),
    SpriteSpec("0197", "umbreon", "Umbreon"),
    SpriteSpec("0198", "murkrow", "Murkrow"),
    SpriteSpec("0215", "sneasel", "Sneasel"),
    SpriteSpec("0252", "treecko", "Treecko"),
    SpriteSpec("0255", "torchic", "Torchic"),
    SpriteSpec("0258", "mudkip", "Mudkip"),
    SpriteSpec("0280", "ralts", "Ralts"),
    SpriteSpec("0300", "skitty", "Skitty"),
)

Pixel = tuple[int, int, int, int]
Image = tuple[int, int, list[Pixel]]


def url_bytes(path: str) -> bytes:
    with urllib.request.urlopen(f"{RAW_BASE}/{path}", timeout=30) as response:
        return response.read()


def url_text(path: str) -> str:
    return url_bytes(path).decode("utf-8", errors="replace")


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + kind
        + payload
        + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
    )


def write_png_rgba(path: Path, image: Image) -> None:
    width, height, pixels = image
    rows = []
    for y in range(height):
        start = y * width
        row = bytearray([0])
        for r, g, b, a in pixels[start : start + width]:
            row.extend((r, g, b, a))
        rows.append(bytes(row))
    payload = b"".join(
        [
            b"\x89PNG\r\n\x1a\n",
            _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)),
            _png_chunk(b"IDAT", zlib.compress(b"".join(rows), level=9)),
            _png_chunk(b"IEND", b""),
        ]
    )
    path.write_bytes(payload)


def _paeth(left: int, up: int, up_left: int) -> int:
    estimate = left + up - up_left
    left_distance = abs(estimate - left)
    up_distance = abs(estimate - up)
    up_left_distance = abs(estimate - up_left)
    if left_distance <= up_distance and left_distance <= up_left_distance:
        return left
    if up_distance <= up_left_distance:
        return up
    return up_left


def _unfilter_row(filter_type: int, row: bytes, previous: bytes, bpp: int) -> bytes:
    out = bytearray(row)
    for index, value in enumerate(row):
        left = out[index - bpp] if index >= bpp else 0
        up = previous[index] if previous else 0
        up_left = previous[index - bpp] if previous and index >= bpp else 0
        if filter_type == 0:
            out[index] = value
        elif filter_type == 1:
            out[index] = (value + left) & 0xFF
        elif filter_type == 2:
            out[index] = (value + up) & 0xFF
        elif filter_type == 3:
            out[index] = (value + ((left + up) // 2)) & 0xFF
        elif filter_type == 4:
            out[index] = (value + _paeth(left, up, up_left)) & 0xFF
        else:
            raise ValueError(f"unsupported PNG filter: {filter_type}")
    return bytes(out)


def _unpack_samples(row: bytes, bit_depth: int, width: int) -> list[int]:
    if bit_depth == 8:
        return list(row[:width])
    samples: list[int] = []
    mask = (1 << bit_depth) - 1
    for byte in row:
        for shift in range(8 - bit_depth, -1, -bit_depth):
            samples.append((byte >> shift) & mask)
            if len(samples) == width:
                return samples
    return samples


def read_png_rgba(data: bytes) -> Image:
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("not a PNG file")

    position = 8
    width = height = bit_depth = color_type = interlace = 0
    palette: list[tuple[int, int, int]] = []
    alpha_palette: list[int] = []
    transparent_gray: int | None = None
    transparent_rgb: tuple[int, int, int] | None = None
    idat = bytearray()

    while position < len(data):
        length = struct.unpack(">I", data[position : position + 4])[0]
        position += 4
        kind = data[position : position + 4]
        position += 4
        payload = data[position : position + length]
        position += length + 4
        if kind == b"IHDR":
            width, height, bit_depth, color_type, _, _, interlace = struct.unpack(
                ">IIBBBBB", payload
            )
        elif kind == b"PLTE":
            palette = [
                (payload[i], payload[i + 1], payload[i + 2])
                for i in range(0, len(payload), 3)
            ]
        elif kind == b"tRNS":
            if color_type == 3:
                alpha_palette = list(payload)
            elif color_type == 0 and len(payload) >= 2:
                transparent_gray = struct.unpack(">H", payload[:2])[0]
            elif color_type == 2 and len(payload) >= 6:
                transparent_rgb = struct.unpack(">HHH", payload[:6])
        elif kind == b"IDAT":
            idat.extend(payload)
        elif kind == b"IEND":
            break

    if interlace != 0:
        raise ValueError("interlaced PNG files are not supported")

    channels_by_type = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}
    channels = channels_by_type[color_type]
    bits_per_pixel = channels * bit_depth
    row_length = (width * bits_per_pixel + 7) // 8
    bpp = max(1, (bits_per_pixel + 7) // 8)
    raw = zlib.decompress(bytes(idat))

    rows: list[bytes] = []
    previous = b""
    offset = 0
    for _ in range(height):
        filter_type = raw[offset]
        offset += 1
        encoded = raw[offset : offset + row_length]
        offset += row_length
        decoded = _unfilter_row(filter_type, encoded, previous, bpp)
        rows.append(decoded)
        previous = decoded

    pixels: list[Pixel] = []
    for row in rows:
        if color_type == 3:
            for index in _unpack_samples(row, bit_depth, width):
                r, g, b = palette[index]
                a = alpha_palette[index] if index < len(alpha_palette) else 255
                pixels.append((r, g, b, a))
        elif color_type == 6 and bit_depth == 8:
            for index in range(0, width * 4, 4):
                pixels.append((row[index], row[index + 1], row[index + 2], row[index + 3]))
        elif color_type == 2 and bit_depth == 8:
            for index in range(0, width * 3, 3):
                r, g, b = row[index : index + 3]
                alpha = 255
                if transparent_rgb == (r, g, b):
                    alpha = 0
                pixels.append((r, g, b, alpha))
        elif color_type == 0 and bit_depth in {1, 2, 4, 8}:
            max_sample = (1 << bit_depth) - 1
            for gray in _unpack_samples(row, bit_depth, width):
                value = gray * 255 // max_sample
                alpha = 0 if transparent_gray == gray else 255
                pixels.append((value, value, value, alpha))
        elif color_type == 4 and bit_depth == 8:
            for index in range(0, width * 2, 2):
                gray, alpha = row[index : index + 2]
                pixels.append((gray, gray, gray, alpha))
        else:
            raise ValueError(f"unsupported PNG color type/depth: {color_type}/{bit_depth}")

    return width, height, pixels


def crop_rgba(image: Image, left: int, top: int, width: int, height: int) -> Image:
    source_width, _, source_pixels = image
    cropped: list[Pixel] = []
    for y in range(top, top + height):
        start = y * source_width + left
        cropped.extend(source_pixels[start : start + width])
    return width, height, cropped


def alpha_pixels(image: Image) -> int:
    return sum(1 for _, _, _, alpha in image[2] if alpha > 0)


def first_visible_frame(sheet: Image, frame_width: int, frame_height: int) -> Image:
    sheet_width, sheet_height, _ = sheet
    if frame_width > sheet_width or frame_height > sheet_height:
        raise ValueError("animation frame is larger than its sprite sheet")
    for left in range(0, sheet_width - frame_width + 1, frame_width):
        frame = crop_rgba(sheet, left, 0, frame_width, frame_height)
        if alpha_pixels(frame) > 0:
            return frame
    return crop_rgba(sheet, 0, 0, frame_width, frame_height)


def trim_transparent(image: Image) -> Image:
    width, height, pixels = image
    visible = [index for index, pixel in enumerate(pixels) if pixel[3] > 0]
    if not visible:
        return image
    min_x = min(index % width for index in visible)
    max_x = max(index % width for index in visible)
    min_y = min(index // width for index in visible)
    max_y = max(index // width for index in visible)
    return crop_rgba(image, min_x, min_y, max_x - min_x + 1, max_y - min_y + 1)


def resize_nearest(image: Image, max_size: int = MAX_SPRITE_SIZE) -> Image:
    width, height, pixels = image
    if width <= max_size and height <= max_size:
        scale = max(1, min(max_size // width, max_size // height))
        new_width = width * scale
        new_height = height * scale
    else:
        scale_factor = min(max_size / width, max_size / height)
        new_width = max(1, int(round(width * scale_factor)))
        new_height = max(1, int(round(height * scale_factor)))
    if new_width == width and new_height == height:
        return image
    resized: list[Pixel] = []
    for y in range(new_height):
        source_y = min(height - 1, y * height // new_height)
        for x in range(new_width):
            source_x = min(width - 1, x * width // new_width)
            resized.append(pixels[source_y * width + source_x])
    return new_width, new_height, resized


def center_on_canvas(image: Image, canvas_size: int = CANVAS_SIZE) -> Image:
    width, height, pixels = image
    canvas: list[Pixel] = [(0, 0, 0, 0)] * (canvas_size * canvas_size)
    left = (canvas_size - width) // 2
    top = (canvas_size - height) // 2
    for y in range(height):
        for x in range(width):
            canvas[(top + y) * canvas_size + left + x] = pixels[y * width + x]
    return canvas_size, canvas_size, canvas


def parse_frame_sizes(xml_text: str) -> dict[str, tuple[int, int]]:
    root = ElementTree.fromstring(xml_text)
    entries: dict[str, dict[str, str]] = {}
    for anim in root.findall(".//Anim"):
        name = anim.findtext("Name")
        if not name:
            continue
        entries[name] = {
            child.tag: child.text or ""
            for child in anim
            if child.tag in {"FrameWidth", "FrameHeight", "CopyOf"}
        }

    resolved: dict[str, tuple[int, int]] = {}

    def resolve(name: str) -> tuple[int, int]:
        if name in resolved:
            return resolved[name]
        entry = entries[name]
        if "CopyOf" in entry:
            resolved[name] = resolve(entry["CopyOf"])
            return resolved[name]
        resolved[name] = (int(entry["FrameWidth"]), int(entry["FrameHeight"]))
        return resolved[name]

    return {name: resolve(name) for name in entries}


def extract_mood_sprite(spec: SpriteSpec, mood: str, action: str, output_path: Path) -> None:
    frames = parse_frame_sizes(url_text(f"sprite/{spec.pokedex_id}/AnimData.xml"))
    frame_width, frame_height = frames[action]
    sheet = read_png_rgba(url_bytes(f"sprite/{spec.pokedex_id}/{action}-Anim.png"))
    frame = first_visible_frame(sheet, frame_width, frame_height)
    sprite = center_on_canvas(resize_nearest(trim_transparent(frame)))
    write_png_rgba(output_path / f"{mood}.png", sprite)


def theme_manifest(theme_name: str) -> dict[str, object]:
    return {
        "theme": theme_name,
        "sprites": {mood: f"{theme_name}/{mood}.png" for mood in MOOD_TO_ACTION},
        "audio": {},
    }


def write_theme_readme(spec: SpriteSpec, output_path: Path) -> None:
    mapping = "\n".join(
        f"- `{mood}`: `{action}-Anim.png`" for mood, action in MOOD_TO_ACTION.items()
    )
    output_path.joinpath("README.md").write_text(
        f"# PMD SpriteCollab {spec.display_name} sample theme\n\n"
        "This directory contains 128x128 static PNG extracts generated from "
        "PMD SpriteCollab animation sheets for use as coding-pet sample characters.\n\n"
        f"- Source directory: `{RAW_BASE}/sprite/{spec.pokedex_id}/`\n"
        f"- Theme id: `pmd-{spec.slug}`\n"
        "- Upstream project: https://github.com/PMDCollab/SpriteCollab\n"
        "- License: CC BY-NC 4.0; see `../PMDCOLLAB_LICENSE.md` and the upstream "
        "SpriteCollab license. Do not treat these as company-owned production art.\n"
        "- Credits: preserved in `credits.txt`.\n\n"
        "Mood mapping:\n"
        f"{mapping}\n",
        encoding="utf-8",
    )


def write_sprite_registry(assets_root: Path) -> None:
    registry = {
        "default_theme": "company-pet",
        "themes": [
            {
                "theme": "company-pet",
                "display_name": "Company Pet",
                "manifest": "theme-manifest.json",
                "source": "internal-pilot-art",
            },
            {
                "theme": "classic",
                "display_name": "Classic Text",
                "manifest": None,
                "source": "bundled-text-fallback",
            },
        ],
    }
    for spec in SPRITES:
        registry["themes"].append(
            {
                "theme": f"pmd-{spec.slug}",
                "display_name": spec.display_name,
                "manifest": f"pmd-{spec.slug}/theme-manifest.json",
                "pokedex_id": spec.pokedex_id,
                "source": "PMDCollab/SpriteCollab",
                "source_url": f"{RAW_BASE}/sprite/{spec.pokedex_id}/",
                "license": "CC BY-NC 4.0",
            }
        )
    assets_root.joinpath("theme-registry.json").write_text(
        json.dumps(registry, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    assets_root = root / "assets" / "sprites"
    assets_root.mkdir(parents=True, exist_ok=True)
    assets_root.joinpath("PMDCOLLAB_LICENSE.md").write_text(
        url_text("LICENSE.md"),
        encoding="utf-8",
    )

    for spec in SPRITES:
        theme_name = f"pmd-{spec.slug}"
        output_path = assets_root / theme_name
        output_path.mkdir(parents=True, exist_ok=True)
        for mood, action in MOOD_TO_ACTION.items():
            extract_mood_sprite(spec, mood, action, output_path)
        output_path.joinpath("credits.txt").write_text(
            url_text(f"sprite/{spec.pokedex_id}/credits.txt"),
            encoding="utf-8",
        )
        output_path.joinpath("theme-manifest.json").write_text(
            json.dumps(theme_manifest(theme_name), indent=2) + "\n",
            encoding="utf-8",
        )
        write_theme_readme(spec, output_path)
        print(f"generated {theme_name}")

    write_sprite_registry(assets_root)


if __name__ == "__main__":
    main()
