#!/usr/bin/env python3
"""Generate app icon assets. Run once to create assets/icon.png and assets/icon.ico.
Replace assets/icon.png with your own 256x256 PNG at any time."""

import os
from PIL import Image, ImageDraw


def create_icon(size: int = 256) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Background circle — deep blue
    pad = 4
    draw.ellipse([pad, pad, size - pad, size - pad], fill=(30, 80, 200, 255))

    # Waveform bars
    bar_color = (255, 255, 255, 235)
    heights = [0.35, 0.6, 0.85, 1.0, 0.85, 0.6, 0.35]
    n = len(heights)
    bar_w = max(4, int(size * 0.07))
    gap = max(3, int(size * 0.04))
    total_w = n * bar_w + (n - 1) * gap
    x0 = (size - total_w) // 2
    cy = size // 2
    max_h = int(size * 0.55)

    for i, h in enumerate(heights):
        x = x0 + i * (bar_w + gap)
        bh = max(4, int(h * max_h))
        radius = bar_w // 2
        draw.rounded_rectangle(
            [x, cy - bh // 2, x + bar_w, cy + bh // 2],
            radius=radius,
            fill=bar_color,
        )

    return img


def save_assets(img: Image.Image):
    os.makedirs("assets", exist_ok=True)

    # PNG for Tkinter and general use
    img.save("assets/icon.png")
    print("Saved assets/icon.png")

    # ICO with multiple sizes for Windows / PyInstaller
    ico_sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    frames = [img.resize(s, Image.LANCZOS) for s in ico_sizes]
    frames[0].save(
        "assets/icon.ico",
        format="ICO",
        sizes=ico_sizes,
        append_images=frames[1:],
    )
    print("Saved assets/icon.ico")


if __name__ == "__main__":
    save_assets(create_icon())
