#!/usr/bin/env python3
"""Stage 3c: a model-free cross-check of a repair pass against the OCR.

    /path/to/repo/scripts/diffcheck.py [repair-output-dir] [min-run]

The OCR is noisy but independent of the model: it cannot drop a sentence
because it "decided" to, and it cannot invent one. So a long run of words
present in one and absent from the other is worth a look at the page image:

  OCR-ONLY   words tesseract read that the fragment lacks: a dropped line or
             sentence, or (often) marginalia/stamps the model rightly dropped.
  MODEL-ONLY words in the fragment that tesseract never saw: an invention, or
             a passage tesseract garbled beyond recognition.

Runs shorter than min-run words (default 6) are ignored: at that length
they are almost always OCR misreads, rejoined hyphens and dropped running
heads. Prose profile only; for LaTeX output the comparison is meaningless.
Also prints a per-page similarity ratio; a low ratio on a page with clean
OCR is the cheapest omission detector there is.
"""
import difflib, glob, html, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import book

src = sys.argv[1] if len(sys.argv) > 1 else (sorted(glob.glob('out/repair-*')) or [''])[0]
MIN = int(sys.argv[2]) if len(sys.argv) > 2 else 6
blocks = book.read_blocks(glob.glob(f'{src}/c*.raw'))
if not blocks:
    sys.exit(f'no repair blocks under {src!r}')


def words(text):
    text = re.sub(r'-\s*\n\s*', '', text)          # rejoin line-end hyphenation
    text = text.replace('’', "'").replace('‘', "'")
    return re.findall(r"[a-z0-9]+(?:'[a-z]+)?", text.lower())


def plain(fragment):
    # Block tags separate words; inline tags do not ("S<span>ome</span>").
    fragment = re.sub(r'</?(p|h\d|blockquote|aside|li|br)\b[^>]*>', ' ', fragment)
    return html.unescape(re.sub(r'<[^>]+>', '', fragment))


def body_lines(lines):
    # Drop the running head and the folio only where they look like one, so
    # a chapter-opening page (no running head) keeps its first line.
    if lines and len(lines[0]) < 45 and not re.search(r'[a-z]{3}', lines[0]):
        lines = lines[1:]
    if lines and re.fullmatch(r'[\W\dixvlcIXVLC\]\}/|]{1,8}', lines[-1].strip()):
        lines = lines[:-1]
    return lines


flagged = 0
for page in book.expected_pages(book.load()):
    if page not in blocks:
        print(f'{page}: NO BLOCK')
        flagged += 1
        continue
    lines = open(f'ocr/{page}.txt', encoding='utf-8', errors='replace').read().strip().splitlines()
    a = words('\n'.join(body_lines(lines)))
    b = words(plain(blocks[page]))
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    notes = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op in ('delete', 'replace') and i2 - i1 >= MIN and (op == 'delete' or i2 - i1 > 2 * (j2 - j1)):
            notes.append(f'  OCR-ONLY   ({i2 - i1} words) {" ".join(a[i1:i2])[:160]}')
        if op in ('insert', 'replace') and j2 - j1 >= MIN and (op == 'insert' or j2 - j1 > 2 * (i2 - i1)):
            notes.append(f'  MODEL-ONLY ({j2 - j1} words) {" ".join(b[j1:j2])[:160]}')
    ratio = sm.ratio()
    if notes or ratio < 0.90:
        flagged += 1
        print(f'{page}: similarity {ratio:.3f}')
        print('\n'.join(notes))
print(f'\n{flagged} page(s) flagged of {len(blocks)}')
