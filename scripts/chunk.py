#!/usr/bin/env python3
"""Stage 3a: build the per-chunk prompts for a model pass.

    /path/to/repo/scripts/chunk.py repair
    /path/to/repo/scripts/chunk.py review [repair-output-dir]

Env: PAGES=p-049,p-050 builds chunks for just those pages (a retry);
CHUNK_SIZE overrides book.json "chunk_size".

Writes chunks/<stage>/c-pNNN-pMMM.txt (the full prompt) and .pages (the
pages it covers, one per line, which run-model.sh checks the output
against). Chunks are named by page range, not by sequence, so a retry of a
few pages at a smaller chunk size lands beside the earlier output instead of
overwriting a different chunk; book.read_blocks lets the newest file win.

repair  prompt = prompts/<profile>-repair.txt + per page: the image views (if
        views/ has them) and the OCR text.
review  prompt = prompts/<profile>-review.txt + per page: the image views,
        the OCR text, and the fragment the repair pass produced, read from
        out/repair-* (or the directory given). A review only ever sees a
        page's own fragment, so a reviewer cannot be anchored by the repair
        model's handling of neighbouring pages.

Chunks are small on purpose (book.json "chunk_size", default 5): a long run
can have its context compacted mid-flight, and whatever the model meant to
emit "at the end" is then silently lost while the process still exits 0.
"""
import glob, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import book

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
stage = sys.argv[1] if len(sys.argv) > 1 else 'repair'
if stage not in ('repair', 'review'):
    sys.exit('usage: chunk.py repair | review [repair-output-dir]')

cfg = book.load()
prompt = open(os.path.join(REPO, 'prompts', f"{cfg['profile']}-{stage}.txt"),
              encoding='utf-8').read().replace('{{CONTEXT}}', cfg.get('context', '').strip())

folios = {}
if os.path.exists('pagemap.tsv'):
    for line in open('pagemap.tsv', encoding='utf-8').read().splitlines()[1:]:
        page, folio = line.split('\t')[:2]
        folios[page] = folio

opens = {}
for s in book.sections(cfg):
    if s.get('title'):
        label = f"{s['label']} " if s.get('label') else ''
        opens[s['page_list'][0]] = f"{label}{s['title']}"

fragments = {}
if stage == 'review':
    src = sys.argv[2] if len(sys.argv) > 2 else None
    dirs = [src] if src else sorted(glob.glob('out/repair-*'))
    if not dirs:
        sys.exit('review: no out/repair-* directory; run the repair pass first')
    if len(dirs) > 1:
        sys.exit(f'review: several repair outputs {dirs}; name one')
    fragments = book.read_blocks(glob.glob(f'{dirs[0]}/c*.raw'))

pages = book.expected_pages(cfg)
only = [p.strip() for p in os.environ.get('PAGES', '').split(',') if p.strip()]
if only:
    unknown = set(only) - set(pages)
    if unknown:
        sys.exit(f'PAGES: not in book.json: {sorted(unknown)}')
    pages = [p for p in pages if p in only]
size = int(os.environ.get('CHUNK_SIZE') or cfg['chunk_size'])
outdir = f'chunks/{stage}'
os.makedirs(outdir, exist_ok=True)
for old in glob.glob(f'{outdir}/c*'):
    os.remove(old)

here = os.getcwd()
for ci in range(0, len(pages), size):
    group = pages[ci:ci + size]
    parts = [prompt.rstrip('\n'), '']
    for page in group:
        folio = folios.get(page) or '?'
        if folio.startswith('r'):
            folio = f'{folio[1:]} (roman)'
        parts.append(f'=== {page} (printed page {folio}) ===')
        views = [f'{here}/views/{page}-1.png', f'{here}/views/{page}-2.png']
        if all(os.path.exists(v) for v in views):
            parts.append(f'images: {views[0]} (top half), {views[1]} (bottom half)')
        if page in opens:
            parts.append(f'this page opens section "{opens[page]}": its printed '
                         'title is supplied by the assembler; do not transcribe it.')
        ocr = open(f'ocr/{page}.txt', encoding='utf-8', errors='replace').read().strip()
        parts += ['--- OCR ---', ocr]
        if stage == 'review':
            if page not in fragments:
                sys.exit(f'review: no repair block for {page}; rerun the repair pass')
            parts += ['--- FRAGMENT UNDER TEST ---', fragments[page]]
        parts.append(f'=== end of {page} ===\n')
    name = f'c-{group[0].replace("-", "")}-{group[-1].replace("-", "")}'
    with open(f'{outdir}/{name}.txt', 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(parts))
    with open(f'{outdir}/{name}.pages', 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(group) + '\n')
print(f'{stage}: {len(pages)} pages in {(len(pages) + size - 1) // size} chunks under {outdir}/')
