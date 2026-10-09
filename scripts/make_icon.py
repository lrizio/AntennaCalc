"""Draws icon.ico for AntennaCalc: a Yagi silhouette with radiation arcs on the family's dark tile."""
import os
from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def draw(size):
    s = size * 4
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, s - 1, s - 1), radius=int(s * 0.2), fill="#14181d", outline="#3a414c", width=max(2, s // 64))
    ac, ac2, red = "#6cb6ff", "#57e39a", "#ff7a6b"
    lw = max(3, s // 26)
    # boom
    bx0, bx1, by = int(s * 0.16), int(s * 0.80), int(s * 0.62)
    d.line((bx0, by, bx1, by), fill="#a7b3c0", width=lw)
    # elements: reflector, driven, directors (shrinking)
    xs = [0.22, 0.36, 0.50, 0.63, 0.76]
    hs = [0.34, 0.30, 0.26, 0.23, 0.20]
    for i, (x, h) in enumerate(zip(xs, hs)):
        col = ac2 if i == 1 else ac
        d.line((int(s * x), by - int(s * h), int(s * x), by + int(s * h)), fill=col, width=lw)
    d.ellipse((int(s * 0.36) - lw, by - lw, int(s * 0.36) + lw, by + lw), fill=red)
    # radiation arcs
    for k, r in enumerate((0.10, 0.17, 0.24)):
        cx, cy = int(s * 0.80), int(s * 0.30)
        box = (cx - int(s * r), cy - int(s * r), cx + int(s * r), cy + int(s * r))
        d.arc(box, -50, 50, fill=ac, width=max(2, lw // 2))
    return im.resize((size, size), Image.LANCZOS)


if __name__ == "__main__":
    sizes = [16, 24, 32, 48, 64, 128, 256]
    imgs = [draw(n) for n in sizes]
    out = os.path.join(ROOT, "icon.ico")
    imgs[-1].save(out, format="ICO", sizes=[(n, n) for n in sizes], append_images=imgs[:-1])
    imgs[-1].save(os.path.join(ROOT, "docs", "icon.png"))
    print("wrote", out)
