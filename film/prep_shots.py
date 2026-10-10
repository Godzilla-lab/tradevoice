"""Cuts the captured app screens (film/shots/*.png, from capture.cjs) into the layers the film moves: the dimmed
screen behind a sheet, the sheet itself (rounded top, transparent corners), the toast. Writes film/shots/layers/ and
film/shots/layers.json (positions in the app's CSS pixels, 390x844).
Run: python film/prep_shots.py
"""
import json
import os

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
SH = os.path.join(HERE, "shots")
OUT = os.path.join(SH, "layers")
S = 3                                   # captured at 3x
CANVAS = (247, 246, 243)
os.makedirs(OUT, exist_ok=True)
boxes = json.load(open(os.path.join(SH, "boxes.json")))
geo = {}


def img(name):
    return Image.open(os.path.join(SH, name + ".png")).convert("RGB")


def sheet_top(im, x=200):
    px = im.load()
    prev = None
    for y in range(100 * S, 800 * S):
        c = px[x * S, y]
        if c == CANVAS and prev and prev != c and sum(prev) < sum(c) - 60:
            return y
        prev = c
    raise SystemExit("no sheet edge")


def rounded_alpha(size, radius, top_only=True):
    m = Image.new("L", size, 0)
    d = ImageDraw.Draw(m)
    w, h = size
    d.rounded_rectangle([0, 0, w - 1, h + (radius * 2 if top_only else 0) - 1], radius=radius, fill=255)
    return m


def dim_map(base, dimmed, y_end):
    """The sheet's backdrop as a per-channel straight line (fitted on the part both show), applied to the whole
    screen, so the dimmed layer exists under the sheet too."""
    a = np.asarray(base, dtype=np.float64)[:y_end].reshape(-1, 3)
    b = np.asarray(dimmed, dtype=np.float64)[:y_end].reshape(-1, 3)
    out = np.empty_like(np.asarray(base, dtype=np.float64))
    full = np.asarray(base, dtype=np.float64)
    for c in range(3):
        k, m = np.polyfit(a[:, c], b[:, c], 1)
        out[..., c] = full[..., c] * k + m
    return Image.fromarray(np.clip(out, 0, 255).round().astype(np.uint8))


def save(im, name, **g):
    im.save(os.path.join(OUT, name + ".png"))
    geo[name] = {k: round(v / S, 2) if isinstance(v, (int, float)) else v for k, v in g.items()}


def sheet_layers(shot, base, name, clear=()):
    """shot: the screen with the sheet up; base: the same screen without it. -> <name>_dim, <name>_sheet."""
    up, under = img(shot), img(base)
    top = sheet_top(up)
    save(dim_map(under, up, top - 2), name + "_dim", y=0, h=under.height)
    sheet = up.crop((0, top - 3 * S, up.width, up.height)).convert("RGBA")
    # the rounded top (radius 24 px, the app's --r3), drawn 4x larger and scaled down for clean edges; above it: clear
    w, h = sheet.size
    big = Image.new("L", (w * 4, 120 * S * 4), 0)
    ImageDraw.Draw(big).rounded_rectangle([0, 3 * S * 4, w * 4 - 1, 120 * S * 4 + 400], radius=24 * S * 4, fill=255)
    top_mask = big.resize((w, 120 * S), Image.LANCZOS)
    alpha = Image.new("L", (w, h), 255)
    alpha.paste(top_mask, (0, 0))
    sheet.putalpha(alpha)
    draw = ImageDraw.Draw(sheet)
    for (x0, y0, x1, y1) in clear:   # parts the film draws itself, live (the status pill, the words)
        draw.rectangle([x0 * S, (y0 * S) - (top - 3 * S), x1 * S, (y1 * S) - (top - 3 * S)], fill=CANVAS + (255,))
    save(sheet, name + "_sheet", y=top - 3 * S, h=sheet.height)


# live talk: the film draws the status pill, the orb and the words with the app's own CSS
pl, cp = boxes["pill"], boxes["cap_pending"]
sheet_layers("talk_listen_noorb", "home_before", "talk",
             clear=[(pl["x"] - 6, pl["y"] - 4, pl["x"] + pl["width"] + 6, pl["y"] + pl["height"] + 4), (8, cp["y"] - 50, 382, cp["y"] + 110)])
sheet_layers("card", "talk_pending_noorb", "card")
sheet_layers("reminder", "customer", "reminder")
sheet_layers("scan", "home", "scan")

# the toast after Save, with its rounded corners
saved = img("saved")
b = boxes["saved_toast"]
x0, y0, x1, y1 = int(b["x"] * S), int(b["y"] * S), int((b["x"] + b["width"]) * S), int((b["y"] + b["height"]) * S)
toast = saved.crop((x0, y0, x1, y1)).convert("RGBA")
toast.putalpha(rounded_alpha(toast.size, 14 * S, top_only=False))
save(toast, "toast", x=x0, y=y0, w=toast.width, h=toast.height)

# the scan sheet's rows, for revealing them one by one (y positions of each .ln row, from colour bands)
geo["boxes"] = boxes
json.dump(geo, open(os.path.join(SH, "layers.json"), "w"), indent=1)
print("layers:", ", ".join(sorted(k for k in geo if k != "boxes")))
