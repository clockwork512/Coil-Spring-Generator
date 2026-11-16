"""Draws the Coil Spring Designer icon and writes icon.ico + icon.png next to this script.

Run:  python assets/make_icon.py
"""
import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from coilspring.calc import SpringInput          # noqa: E402
from coilspring.geometry import centerline       # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))

BG_TOP, BG_BOT = (33, 39, 47), (16, 19, 23)
EDGE = (58, 66, 76)
STEEL_FRONT = (190, 206, 220)
STEEL_BACK = (88, 104, 120)
HILITE = (238, 244, 249)
ORANGE = (217, 138, 43)
ORANGE_DARK = (168, 101, 24)


def lerp(a, b, t):
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def stroke(draw, pts, color, width):
    """Thick polyline with round caps and joins."""
    if len(pts) < 2:
        return
    draw.line(pts, fill=color, width=round(width), joint="curve")
    r = width / 2
    for x, y in (pts[0], pts[-1]):
        draw.ellipse((x - r, y - r, x + r, y + r), fill=color)


def render(size, coils, wire_frac, highlight, plates_frac, tilt=0.30):
    S = size * 4                                   # supersample
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))

    # rounded-square background with a vertical gradient
    grad = Image.new("RGBA", (S, S))
    gd = ImageDraw.Draw(grad)
    for yy in range(S):
        gd.line([(0, yy), (S, yy)], fill=lerp(BG_TOP, BG_BOT, yy / S) + (255,))
    mask = Image.new("L", (S, S), 0)
    pad, rad = S * 0.04, S * 0.22
    ImageDraw.Draw(mask).rounded_rectangle((pad, pad, S - pad, S - pad), radius=rad, fill=255)
    img.paste(grad, (0, 0), mask)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((pad, pad, S - pad, S - pad), radius=rad, outline=EDGE, width=max(2, round(S * 0.008)))

    # spring geometry (real closed & ground centreline from the app)
    s = SpringInput(wire_d=1.0, mean_d=6.2, active_coils=coils, free_length=1.0 + coils * 1.55 + 2,
                    end_type="Closed & ground")
    pts, *_ = centerline(s, samples_per_turn=90)
    plate_h = S * plates_frac
    top, bot = S * 0.11 + plate_h, S * 0.89 - plate_h       # spring between the plates
    span_x = S * 0.54                                        # spring OD on screen
    sc_x = span_x / s.od
    wire = S * wire_frac
    ell = tilt * s.mean_d / 2 * sc_x                       # half-height of each coil ellipse
    sc_z = (bot - top - 2 * ell - wire * 0) / s.free_length
    cx = S / 2

    def P(x, y, z):
        # looking slightly down on the spring: the front of each coil sits lower on screen
        return (cx + x * sc_x, bot - ell - z * sc_z - y * sc_x * tilt)

    # clip so ground ends are cut flat against the plates
    layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    for front in (False, True):
        runs, run = [], []
        for x, y, z in pts:
            if (y <= 0) == front:
                run.append(P(x, y, z))
            elif run:
                runs.append(run)
                run = []
        if run:
            runs.append(run)
        for r_ in runs:
            stroke(ld, r_, (STEEL_FRONT if front else STEEL_BACK) + (255,), wire)
            if front and highlight:
                off = wire * 0.20
                hl = [(x - off * 0.6, y - off) for x, y in r_]
                stroke(ld, hl, HILITE + (255,), wire * 0.22)
    clip = Image.new("L", (S, S), 0)
    ImageDraw.Draw(clip).rectangle((0, top + ell - plate_h * 0.5, S, bot - ell + plate_h * 0.5), fill=255)
    img.paste(layer, (0, 0), Image.composite(layer.split()[3], Image.new("L", (S, S), 0), clip))

    # orange plates
    pw = S * 0.62
    pr = plate_h * 0.35
    for y0 in (top + ell - plate_h, bot - ell):     # plates sit on the end coils
        box = (cx - pw / 2, y0, cx + pw / 2, y0 + plate_h)
        d.rounded_rectangle(box, radius=pr, fill=ORANGE)
        d.rounded_rectangle((box[0], box[3] - plate_h * 0.28, box[2], box[3]), radius=pr, fill=ORANGE_DARK)
        d.rectangle((box[0] + pr, box[3] - plate_h * 0.28, box[2] - pr, box[3] - plate_h * 0.28 + pr),
                    fill=ORANGE)

    return img.resize((size, size), Image.LANCZOS)


def main():
    big = {n: render(n, coils=4, wire_frac=0.052, highlight=True, plates_frac=0.045)
           for n in (256, 128, 64, 48)}
    small = {n: render(n, coils=2.5, wire_frac=0.085, highlight=False, plates_frac=0.07)
             for n in (32, 24, 16)}
    imgs = {**big, **small}
    order = [256, 128, 64, 48, 32, 24, 16]
    render(1024, coils=4, wire_frac=0.052, highlight=True, plates_frac=0.045).save(
        os.path.join(HERE, "icon.png"))
    imgs[256].save(os.path.join(HERE, "icon.ico"), format="ICO",
                   sizes=[(n, n) for n in order],
                   append_images=[imgs[n] for n in order[1:]])
    # preview sheet
    sheet = Image.new("RGBA", (sum(order) + 20 * len(order) + 20, 296), (243, 244, 246, 255))
    x = 20
    for n in order:
        sheet.paste(imgs[n], (x, 20 + (256 - n)), imgs[n])
        x += n + 20
    sheet.save(os.path.join(HERE, "icon_preview.png"))
    print("wrote icon.ico, icon.png, icon_preview.png")


if __name__ == "__main__":
    main()
