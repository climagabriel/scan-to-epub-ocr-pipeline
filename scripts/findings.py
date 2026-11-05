#!/usr/bin/env python3
"""Stage 4a: collect every reviewer's findings, page by page.

    /path/to/repo/scripts/findings.py [--md findings.md]

Reads out/review-*/c-*.raw (one directory per reviewer), and prints, for
each page any reviewer did not pass as CLEAN, every finding with the
reviewer that made it, most severe first. Also reports pages a reviewer
never returned an audit for -- a missing audit is not a clean page.

Agreement is the useful signal: a finding two reviewers from different
vendors both make, on the same words, is very likely real; one only one of
them makes needs the page image to settle. Either way the image decides.
"""
import glob, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import book

cfg = book.load()
pages = book.expected_pages(cfg)
reviewers = {os.path.basename(d)[len('review-'):]: d for d in sorted(glob.glob('out/review-*'))}
if not reviewers:
    sys.exit('no out/review-* directories')

FIND = re.compile(r'-\s*SEVERITY:\s*(\d)\s*\n\s*PAGE SAYS:\s*(.*?)\n\s*FRAGMENT SAYS:\s*(.*?)\n\s*DEFECT:\s*(.*?)(?=\n\s*-\s*SEVERITY:|\Z)', re.S)
by_page, missing, verdicts = {}, {}, {}
for name, d in reviewers.items():
    audits = book.read_blocks(glob.glob(f'{d}/c*.raw'), pattern=book.AUDIT)
    missing[name] = [p for p in pages if p not in audits]
    for page, body in audits.items():
        verdict = re.search(r'VERDICT:\s*(\w+)', body)
        verdicts.setdefault(page, {})[name] = verdict.group(1) if verdict else '?'
        for sev, said, frag, defect in FIND.findall(body):
            by_page.setdefault(page, []).append(
                (int(sev), name, said.strip(), frag.strip(), ' '.join(defect.split())))

def norm(s):
    return re.sub(r'\W+', ' ', s.lower()).strip()

out = []
total = 0
for page in pages:
    items = sorted(by_page.get(page, []), key=lambda f: (f[0], f[1]))
    if not items:
        continue
    v = ', '.join(f'{n}={x}' for n, x in sorted(verdicts.get(page, {}).items()))
    out.append(f'## {page}   ({v})')
    for sev, name, said, frag, defect in items:
        others = {n for s, n, sd, _, _ in items if n != name and
                  (norm(sd)[:40] in norm(said) or norm(said)[:40] in norm(sd))}
        agree = f'  [also: {", ".join(sorted(others))}]' if others else ''
        out.append(f'- S{sev} {name}{agree}\n  PAGE:     {said}\n  FRAGMENT: {frag}\n  DEFECT:   {defect}')
        total += 1
    out.append('')
for name, miss in missing.items():
    if miss:
        out.append(f'NO AUDIT from {name}: {" ".join(miss)}')
clean = {n: sum(1 for p in pages if verdicts.get(p, {}).get(n) == 'CLEAN') for n in reviewers}
out.append(f'{total} finding(s) on {sum(1 for p in pages if by_page.get(p))} page(s); '
           + ', '.join(f'{n}: {c}/{len(pages)} pages CLEAN' for n, c in clean.items()))
text = '\n'.join(out)
print(text)
if '--md' in sys.argv:
    open(sys.argv[sys.argv.index('--md') + 1], 'w', encoding='utf-8').write(text + '\n')
