#!/usr/bin/env python3
"""OG画像(1200x630)を生成して web/og-image.png に書き出す。"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent.parent / "web" / "og-image.png"
W, H = 1200, 630
BG = "#fcfcfb"
INK = "#0b0b0b"
SUB = "#52514e"
MUTED = "#898781"
BLUE = "#2a78d6"
ORANGE = "#eb6834"

FONT = "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc"
FONT_R = "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc"

img = Image.new("RGB", (W, H), BG)
d = ImageDraw.Draw(img)

# 右側: 円モチーフ + 人口ピラミッド
cx, cy, cr = 900, 315, 240
d.ellipse([cx - cr, cy - cr, cx + cr, cy + cr], outline=BLUE, width=4)
d.ellipse([cx - cr, cy - cr, cx + cr, cy + cr], fill=None)
# 円内をほんのり塗る
overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
od = ImageDraw.Draw(overlay)
od.ellipse([cx - cr, cy - cr, cx + cr, cy + cr], fill=(42, 120, 214, 18))
img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
d = ImageDraw.Draw(img)

# ピラミッド(左=男/青, 右=女/橙)。それらしい年齢分布
dist = [0.30, 0.38, 0.42, 0.50, 0.72, 0.85, 0.80, 0.72, 0.78, 0.88,
        0.95, 0.75, 0.62, 0.68, 0.72, 0.60, 0.45, 0.28, 0.14, 0.06]
rows = len(dist)
bar_h, gap = 14, 6
py0 = cy - (rows * (bar_h + gap) - gap) // 2
maxw = 170
for i, v in enumerate(reversed(dist)):
    y = py0 + i * (bar_h + gap)
    wm = int(maxw * v)
    wf = int(maxw * v * (1.12 if i < 6 else 0.96))  # 高齢帯は女性が長い
    d.rounded_rectangle([cx - 8 - wm, y, cx - 8, y + bar_h], radius=4, fill=BLUE)
    d.rounded_rectangle([cx + 8, y, cx + 8 + wf, y + bar_h], radius=4, fill=ORANGE)

# 左側: テキスト
title_f = ImageFont.truetype(FONT, 76)
sub_f = ImageFont.truetype(FONT_R, 34)
small_f = ImageFont.truetype(FONT_R, 26)
d.text((70, 150), "商圏メーカー", font=title_f, fill=INK)
d.text((70, 265), "地図に円を描くと", font=sub_f, fill=SUB)
d.text((70, 315), "人口・年齢構成がその場でわかる", font=sub_f, fill=SUB)
d.text((70, 420), "無料・登録不要・全国対応", font=sub_f, fill=BLUE)
d.text((70, 540), "2020年国勢調査 500mメッシュ（e-Stat）", font=small_f, fill=MUTED)

img.save(OUT, "PNG", optimize=True)
print(f"saved {OUT} ({OUT.stat().st_size:,} bytes)")
