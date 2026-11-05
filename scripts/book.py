"""Shared helpers: the per-book config (book.json) and the page-block format.

Every stage after OCR reads book.json from the current directory (the book's
working directory). It is the one place that knows anything about a specific
book; the scripts and prompts do not. See examples/ for complete configs.

Scan pages are always named by their 1-based position in the scan, p-NNN,
never by the printed page number: printed numbers skip, repeat, and switch
between roman and arabic, and the scan can be missing pages.
"""
import json, os, re, sys

BLOCK = re.compile(r'<<<PAGE (p-\d{3})>>>\n(.*?)\n?<<<END \1>>>', re.S)
AUDIT = re.compile(r'<<<AUDIT (p-\d{3})>>>\n(.*?)\n?<<<END \1>>>', re.S)


def load(path='book.json'):
    if not os.path.exists(path):
        sys.exit(f"{path} not found: run from the book's working directory")
    with open(path, encoding='utf-8') as fh:
        cfg = json.load(fh)
    cfg.setdefault('profile', 'xhtml-prose')
    cfg.setdefault('chunk_size', 5)
    cfg.setdefault('gaps', [])
    return cfg


def pages_of(spec):
    """'5-7,9' -> ['p-005', 'p-006', 'p-007', 'p-009']"""
    out = []
    for part in str(spec).split(','):
        part = part.strip()
        if not part:
            continue
        a, _, b = part.partition('-')
        for n in range(int(a), int(b or a) + 1):
            out.append(f'p-{n:03d}')
    return out


def sections(cfg):
    """Sections in reading order, each with its expanded page list."""
    out = []
    for s in cfg['sections']:
        s = dict(s)
        s['page_list'] = pages_of(s['pages'])
        out.append(s)
    return out


def expected_pages(cfg):
    seen, out = set(), []
    for s in sections(cfg):
        for p in s['page_list']:
            if p in seen:
                sys.exit(f"book.json: {p} appears in more than one section")
            seen.add(p)
            out.append(p)
    return out


def read_blocks(paths, pattern=BLOCK):
    """Last block per page wins: files are read oldest first (a retry of a
    page in a newer chunk file replaces the earlier attempt), and within a
    file a model that re-emits a page corrects it."""
    blocks = {}
    for path in sorted(paths, key=lambda p: (os.path.getmtime(p), p)):
        with open(path, encoding='utf-8', errors='replace') as fh:
            for page, body in pattern.findall(fh.read()):
                blocks[page] = body.strip('\n')
    return blocks
