#!/usr/bin/env python3
"""Generate Claude Code Widget app icon as AppIcon.icns"""
import os, struct, subprocess
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path("/Users/nayerkotry/Documents/ClaudeWidget")
ICONSET = Path("/tmp/ClaudeWidget.iconset")
ICONSET.mkdir(exist_ok=True)

def make_icon(size):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    
    # Rounded rect background — amber/orange gradient approximated
    radius = int(size * 0.22)
    # Draw gradient via scanlines
    for y in range(size):
        t = y / size
        r = int(184 + (232 - 184) * t)
        g = int(98  + (168 - 98)  * t)
        b = int(56  + (124 - 56)  * t)
        d.line([(0, y), (size, y)], fill=(r, g, b, 255))
    
    # Mask to rounded rect
    mask = Image.new("L", (size, size), 0)
    dm = ImageDraw.Draw(mask)
    dm.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    img.putalpha(mask)
    
    # Draw ◆ diamond as a polygon
    cx, cy = size / 2, size / 2
    half = size * 0.34
    diamond = [
        (cx, cy - half),         # top
        (cx + half * 0.72, cy),  # right
        (cx, cy + half),         # bottom
        (cx - half * 0.72, cy),  # left
    ]
    overlay = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.polygon(diamond, fill=(255, 255, 255, 240))
    
    # Slight inner diamond (Claude's double-diamond look)
    inner = size * 0.13
    inner_d = [
        (cx, cy - inner),
        (cx + inner * 0.72, cy),
        (cx, cy + inner),
        (cx - inner * 0.72, cy),
    ]
    od.polygon(inner_d, fill=(184, 98, 56, 180))
    
    # Soft glow on diamond
    glow = overlay.filter(ImageFilter.GaussianBlur(radius=size * 0.025))
    img = Image.alpha_composite(img, glow)
    img = Image.alpha_composite(img, overlay)
    
    return img

sizes = [16, 32, 64, 128, 256, 512, 1024]
for s in sizes:
    img = make_icon(s)
    img.save(ICONSET / f"icon_{s}x{s}.png")
    if s <= 512:
        img2 = make_icon(s * 2)
        img2.save(ICONSET / f"icon_{s}x{s}@2x.png")

subprocess.run(["iconutil", "-c", "icns", str(ICONSET),
                "-o", str(ROOT / "ClaudeWidgetApp" / "AppIcon.icns")], check=True)
print("✓ AppIcon.icns generated")
