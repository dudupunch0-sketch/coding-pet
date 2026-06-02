from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "assets" / "sprites" / "codex-default"
SIZE = 128
SCALE = 4
CANVAS_SIZE = SIZE * SCALE


def scaled(draw_fn: Callable[[ImageDraw.ImageDraw], None]) -> Image.Image:
    image = Image.new("RGBA", (CANVAS_SIZE, CANVAS_SIZE), (0, 0, 0, 0))
    draw_fn(ImageDraw.Draw(image))
    return image.resize((SIZE, SIZE), Image.Resampling.LANCZOS)


def p(value: int) -> int:
    return value * SCALE


def box(x1: int, y1: int, x2: int, y2: int) -> tuple[int, int, int, int]:
    return (p(x1), p(y1), p(x2), p(y2))


def line(
    draw: ImageDraw.ImageDraw,
    points: list[tuple[int, int]],
    *,
    fill: tuple[int, int, int, int],
    width: int,
) -> None:
    draw.line([(p(x), p(y)) for x, y in points], fill=fill, width=p(width), joint="curve")


def rounded(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int, int, int],
    *,
    radius: int,
    fill: tuple[int, int, int, int],
    outline: tuple[int, int, int, int] | None = None,
    width: int = 1,
) -> None:
    draw.rounded_rectangle(
        box(*xy),
        radius=p(radius),
        fill=fill,
        outline=outline,
        width=p(width),
    )


def base(draw: ImageDraw.ImageDraw) -> None:
    draw.ellipse(box(31, 98, 97, 113), fill=(0, 0, 0, 54))
    line(draw, [(64, 31), (64, 22)], fill=(95, 235, 194, 255), width=4)
    draw.ellipse(box(59, 15, 69, 25), fill=(95, 235, 194, 255))
    rounded(
        draw,
        (31, 30, 97, 103),
        radius=17,
        fill=(31, 36, 46, 255),
        outline=(117, 176, 255, 255),
        width=3,
    )
    rounded(
        draw,
        (41, 42, 87, 75),
        radius=8,
        fill=(8, 12, 18, 255),
        outline=(95, 235, 194, 255),
        width=2,
    )
    rounded(
        draw, (43, 82, 85, 97), radius=5, fill=(16, 22, 31, 255), outline=(68, 81, 96, 255), width=1
    )
    line(draw, [(49, 89), (55, 85), (49, 81)], fill=(95, 235, 194, 220), width=2)
    line(draw, [(75, 81), (81, 85), (75, 89)], fill=(95, 235, 194, 220), width=2)
    draw.rounded_rectangle(box(61, 83, 69, 91), radius=p(2), fill=(117, 176, 255, 200))


def arms(
    draw: ImageDraw.ImageDraw,
    *,
    left: list[tuple[int, int]],
    right: list[tuple[int, int]],
    color: tuple[int, int, int, int] = (117, 176, 255, 255),
) -> None:
    line(draw, left, fill=color, width=5)
    line(draw, right, fill=color, width=5)
    lx, ly = left[-1]
    rx, ry = right[-1]
    draw.ellipse(box(lx - 3, ly - 3, lx + 3, ly + 3), fill=color)
    draw.ellipse(box(rx - 3, ry - 3, rx + 3, ry + 3), fill=color)


def eyes(draw: ImageDraw.ImageDraw, *, mood: str) -> None:
    cyan = (95, 235, 194, 255)
    dim = (95, 235, 194, 180)
    if mood == "sleepy":
        line(draw, [(51, 57), (58, 57)], fill=dim, width=3)
        line(draw, [(70, 57), (77, 57)], fill=dim, width=3)
    elif mood == "sad":
        line(draw, [(51, 56), (57, 59)], fill=cyan, width=3)
        line(draw, [(71, 59), (77, 56)], fill=cyan, width=3)
    elif mood == "alert":
        draw.ellipse(box(51, 53, 59, 61), fill=(255, 178, 84, 255))
        draw.ellipse(box(69, 53, 77, 61), fill=(255, 178, 84, 255))
    else:
        rounded(draw, (50, 53, 59, 62), radius=2, fill=cyan)
        rounded(draw, (69, 53, 78, 62), radius=2, fill=cyan)


def mouth(draw: ImageDraw.ImageDraw, *, mood: str) -> None:
    cyan = (95, 235, 194, 230)
    if mood == "celebrate":
        line(draw, [(58, 66), (64, 70), (70, 66)], fill=cyan, width=2)
    elif mood == "sad":
        line(draw, [(58, 70), (64, 66), (70, 70)], fill=cyan, width=2)
    elif mood == "sleepy":
        line(draw, [(60, 67), (68, 67)], fill=cyan, width=2)
    else:
        line(draw, [(58, 67), (70, 67)], fill=cyan, width=2)


def draw_idle(draw: ImageDraw.ImageDraw) -> None:
    base(draw)
    arms(draw, left=[(31, 60), (22, 70), (25, 82)], right=[(97, 60), (106, 70), (103, 82)])
    eyes(draw, mood="idle")
    mouth(draw, mood="idle")


def draw_typing(draw: ImageDraw.ImageDraw) -> None:
    base(draw)
    arms(draw, left=[(31, 66), (22, 78), (32, 90)], right=[(97, 66), (108, 78), (98, 90)])
    eyes(draw, mood="idle")
    mouth(draw, mood="sleepy")
    rounded(
        draw,
        (28, 91, 100, 109),
        radius=5,
        fill=(8, 12, 18, 235),
        outline=(95, 235, 194, 170),
        width=1,
    )
    for x in range(35, 89, 10):
        draw.rounded_rectangle(box(x, 97, x + 5, 101), radius=p(1), fill=(95, 235, 194, 170))
    draw.rounded_rectangle(box(91, 96, 94, 104), radius=p(1), fill=(255, 178, 84, 255))


def draw_celebrate(draw: ImageDraw.ImageDraw) -> None:
    base(draw)
    arms(draw, left=[(34, 54), (21, 40), (15, 28)], right=[(94, 54), (107, 40), (113, 28)])
    eyes(draw, mood="idle")
    mouth(draw, mood="celebrate")
    for x, y, color in (
        (20, 19, (255, 178, 84, 255)),
        (35, 20, (95, 235, 194, 255)),
        (101, 18, (117, 176, 255, 255)),
        (112, 43, (255, 112, 132, 255)),
        (14, 45, (117, 176, 255, 255)),
    ):
        draw.rectangle(box(x, y, x + 5, y + 5), fill=color)


def draw_alert(draw: ImageDraw.ImageDraw) -> None:
    base(draw)
    arms(draw, left=[(31, 60), (23, 66), (22, 77)], right=[(97, 60), (107, 62), (113, 53)])
    eyes(draw, mood="alert")
    mouth(draw, mood="idle")
    draw.ellipse(
        box(91, 20, 112, 41), fill=(255, 178, 84, 255), outline=(31, 36, 46, 255), width=p(2)
    )
    line(draw, [(102, 25), (102, 33)], fill=(31, 36, 46, 255), width=3)
    draw.ellipse(box(100, 36, 104, 40), fill=(31, 36, 46, 255))


def draw_thinking(draw: ImageDraw.ImageDraw) -> None:
    base(draw)
    arms(draw, left=[(31, 60), (22, 70), (25, 82)], right=[(97, 60), (105, 69), (96, 76)])
    eyes(draw, mood="idle")
    mouth(draw, mood="sleepy")
    for bounds in ((88, 18, 98, 28), (99, 11, 114, 26), (113, 18, 122, 27)):
        draw.ellipse(
            box(*bounds), fill=(242, 248, 255, 235), outline=(117, 176, 255, 190), width=p(1)
        )


def draw_sleepy(draw: ImageDraw.ImageDraw) -> None:
    base(draw)
    arms(draw, left=[(31, 60), (22, 70), (24, 81)], right=[(97, 60), (106, 70), (104, 81)])
    eyes(draw, mood="sleepy")
    mouth(draw, mood="sleepy")
    line(draw, [(95, 20), (107, 20), (95, 32), (108, 32)], fill=(117, 176, 255, 230), width=3)
    line(draw, [(111, 10), (120, 10), (111, 20), (121, 20)], fill=(95, 235, 194, 210), width=2)


def draw_sad(draw: ImageDraw.ImageDraw) -> None:
    base(draw)
    arms(draw, left=[(31, 61), (23, 74), (23, 87)], right=[(97, 61), (105, 74), (105, 87)])
    eyes(draw, mood="sad")
    mouth(draw, mood="sad")
    draw.ellipse(box(78, 61, 83, 70), fill=(117, 176, 255, 210))


SPRITES: dict[str, Callable[[ImageDraw.ImageDraw], None]] = {
    "idle": draw_idle,
    "typing": draw_typing,
    "celebrate": draw_celebrate,
    "alert": draw_alert,
    "thinking": draw_thinking,
    "sleepy": draw_sleepy,
    "sad": draw_sad,
}


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for mood, draw_fn in SPRITES.items():
        scaled(draw_fn).save(OUTPUT_DIR / f"{mood}.png", "PNG")


if __name__ == "__main__":
    main()
