"""產生 PWA 圖示（需要 Pillow：pip install pillow）。想換圖示風格可改這支再重跑。
用法：python tools/make_icons.py
"""
from pathlib import Path
from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent.parent / "static" / "icons"
OUT.mkdir(parents=True, exist_ok=True)
SS = 4  # 超取樣倍率，讓邊緣更平滑


def gradient(size):
    c1, c2 = (79, 70, 229), (14, 165, 233)  # indigo → sky
    img = Image.new("RGB", (size, size))
    px = img.load()
    for y in range(size):
        for x in range(size):
            t = (x + y) / (2 * (size - 1))
            px[x, y] = tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))
    return img


def glyph(draw, size, scale):
    """白色長條圖：scale 控制圖形佔整張圖的比例（maskable 需留安全區）。"""
    box = size * scale
    x0 = (size - box) / 2
    y0 = (size - box) / 2
    base = y0 + box
    bar_w = box * 0.2
    gap = box * 0.1
    total = bar_w * 3 + gap * 2
    left = x0 + (box - total) / 2
    for i, h in enumerate([0.45, 0.75, 1.0]):
        bx = left + i * (bar_w + gap)
        draw.rounded_rectangle(
            [bx, base - box * h, bx + bar_w, base], radius=bar_w * 0.28, fill=(255, 255, 255)
        )
    draw.rounded_rectangle(
        [x0, base + box * 0.05, x0 + box, base + box * 0.09], radius=box * 0.02, fill=(255, 255, 255, 200)
    )


def make(size, name, rounded, glyph_scale):
    big = size * SS
    img = gradient(big).convert("RGBA")
    glyph(ImageDraw.Draw(img), big, glyph_scale)
    if rounded:
        mask = Image.new("L", (big, big), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, big, big], radius=big * 0.22, fill=255)
        img.putalpha(mask)
    img.resize((size, size), Image.LANCZOS).save(OUT / name)
    print("wrote", OUT / name)


make(192, "icon-192.png", rounded=True, glyph_scale=0.5)
make(512, "icon-512.png", rounded=True, glyph_scale=0.5)
make(512, "maskable-512.png", rounded=False, glyph_scale=0.4)     # 滿版，圖形落在安全區內
make(180, "apple-touch-icon.png", rounded=False, glyph_scale=0.5)  # iOS 會自行裁圓角
make(32, "favicon-32.png", rounded=True, glyph_scale=0.56)
