#!/usr/bin/env python3
"""Stage 2c: make page images a vision model can actually read.

    /path/to/repo/scripts/views.py [width]

Writes views/p-NNN-1.png (top) and views/p-NNN-2.png (bottom) for every page
in book.json. Why not hand the model the full page:

  - Model image inputs are downscaled to roughly 1500 px on the long edge. A
    full 2000x3600 scan page shrinks to about 840 px wide, where body text is
    readable but footnotes, italics and small capitals are not reliably so.
    Two halves at the same budget each keep twice the linear resolution.
  - The halves overlap by a few lines so no line is cut through without also
    appearing whole in the other half. The prompts say so, so the model does
    not transcribe the overlap twice.
  - Margins are trimmed first (to the ink bounding box, ignoring specks), so
    pixels are spent on text rather than on paper.
"""
import os, sys
import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import book

WIDTH = int(sys.argv[1]) if len(sys.argv) > 1 else 1400
OVERLAP = 0.06

cfg = book.load()
os.makedirs('views', exist_ok=True)


def content_box(im):
    a = np.asarray(im.reduce(4)) < 128
    rows = np.where(a.mean(axis=1) > 0.004)[0]
    cols = np.where(a.mean(axis=0) > 0.004)[0]
    if len(rows) == 0 or len(cols) == 0:
        return (0, 0) + im.size
    pad = 12
    return (max(0, cols[0] * 4 - pad * 4), max(0, rows[0] * 4 - pad * 4),
            min(im.width, cols[-1] * 4 + pad * 4), min(im.height, rows[-1] * 4 + pad * 4))


made = 0
for page in book.expected_pages(cfg):
    out = [f'views/{page}-1.png', f'views/{page}-2.png']
    if all(os.path.exists(o) for o in out):
        continue
    im = Image.open(f'pages/{page}.png').convert('L')
    im = im.crop(content_box(im))
    h = im.height
    cut, ov = h // 2, int(h * OVERLAP)
    for o, (top, bot) in zip(out, [(0, cut + ov), (cut - ov, h)]):
        half = im.crop((0, top, im.width, bot))
        scale = WIDTH / half.width
        if scale < 1:
            half = half.resize((WIDTH, round(half.height * scale)), Image.LANCZOS)
        half.save(o, optimize=True)
    made += 1
print(f'views: {made} pages written, {len(book.expected_pages(cfg))} in book.json')
