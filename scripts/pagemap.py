#!/usr/bin/env python3
"""Stage 2b: map scan pages to printed page numbers and find what is missing.

Run from the book's working directory after ocr.sh. Writes pagemap.tsv and
prints three kinds of anomaly, none of which any later stage can detect:

  GAP     the printed folio jumps (25 -> 29): pages are missing from the scan,
          or are unnumbered chapter openings and blanks. Read the images
          either side and decide which; record real losses in book.json
          "gaps" so the book says so instead of silently running on.
  INK     the page has ink but OCR found almost no text: a truncated image, a
          photograph, a plate, or a page OCR could not segment.
  SPARSE  little ink and little text: a blank page, or a chapter-title or
          section-title page. Glance at it; nothing is lost either way.

Folios are read from the first and last OCR lines, where running heads and
page numbers live. Tesseract misreads them (11 -> "1]", 41 -> "4}", 77 ->
"7/7"), so the common confusions are normalised and anything still
unreadable is left blank; a blank folio between two good ones is not a gap.
"""
import glob, os, re
import numpy as np
from PIL import Image

ROMAN = {'i': 1, 'v': 5, 'x': 10, 'l': 50, 'c': 100}
FIX = str.maketrans({']': '1', '}': '1', '|': '1', 'l': '1', 'I': '1',
                     'O': '0', 'o': '0', 'S': '5', 'B': '8', '/': ''})


def roman(s):
    s = s.lower()
    if not s or any(c not in ROMAN for c in s) or not re.fullmatch(r'[ivxlc]+', s):
        return None
    total = 0
    for a, b in zip(s, s[1:] + ' '):
        v = ROMAN[a]
        total += -v if b != ' ' and ROMAN[b] > v else v
    return total


def folio(line):
    tok = line.strip(" |.-—_'‘’\"").strip()
    if re.fullmatch(r'[0-9\]\}\|lIOoSB/]{1,4}', tok):
        t = tok.translate(FIX)
        if t.isdigit() and re.search(r'\d', tok):
            return ('arabic', int(t))
    r = roman(tok)
    if r and len(tok) <= 6:
        return ('roman', r)
    return None


def ink(png):
    a = np.asarray(Image.open(png).convert('L').reduce(4))
    return float((a < 128).mean())


rows = []
for png in sorted(glob.glob('pages/p-*.png')):
    page = os.path.basename(png)[:-4]
    txt = f'ocr/{page}.txt'
    lines = [l for l in open(txt, encoding='utf-8', errors='replace').read().splitlines()
             if l.strip()] if os.path.exists(txt) else []
    chars = sum(len(l) for l in lines)
    f = None
    for cand in (lines[-1:] + lines[:1]):
        f = folio(cand)
        if f:
            break
    rows.append((page, f, chars, ink(png)))

with open('pagemap.tsv', 'w', encoding='utf-8') as fh:
    fh.write('page\tfolio\tocr_chars\tink\n')
    for page, f, chars, k in rows:
        shown = '' if not f else (f'{f[1]}' if f[0] == 'arabic' else f'r{f[1]}')
        fh.write(f'{page}\t{shown}\t{chars}\t{k:.4f}\n')

last = None   # (scan index, kind, value)
for i, (page, f, chars, k) in enumerate(rows):
    if chars < 40 and k > 0.02:
        print(f'INK    {page}: ink {k:.3f} but only {chars} OCR chars')
    elif chars < 40:
        print(f'SPARSE {page}: {chars} OCR chars')
    if not f:
        continue
    if last and last[1] == f[0]:
        expect = last[2] + (i - last[0])
        if f[1] != expect:
            print(f'GAP    {rows[last[0]][0]} (folio {last[2]}) -> {page} (folio {f[1]}):'
                  f' {f[1] - last[2] - 1} printed page(s) between them,'
                  f' {i - last[0] - 1} scan page(s)')
    last = (i, f[0], f[1])
print('wrote pagemap.tsv')
