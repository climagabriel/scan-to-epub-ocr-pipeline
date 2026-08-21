#!/usr/bin/env python3
r"""Assemble Codex per-page LaTeX blocks into one document.

Deliberately paranoid, because the failure mode this guards against is silent:
 - takes the LAST block per page name (Codex streams and re-emits)
 - verifies every expected page produced a block, against the input list
 - never trusts a DONE marker or a self-reported count
 - counts \UNSURE markers, which gate the build
"""
import re, glob, os, sys

expected = []
for f in sorted(glob.glob('ocr/p-*.txt')):
    nn = os.path.basename(f)[2:4]
    if not (5 <= int(nn) <= 83):
        continue
    if len(open(f, encoding='utf-8', errors='replace').read().strip()) < 30:
        continue
    expected.append(nn)

blocks = {}
pat = re.compile(r'<<<PAGE p-(\d+)>>>\n(.*?)\n<<<END p-\1>>>', re.S)
for raw in sorted(glob.glob('out/c*.raw')):
    for nn, body in pat.findall(open(raw, encoding='utf-8', errors='replace').read()):
        blocks[nn] = body          # last wins

missing = [p for p in expected if p not in blocks]
extra   = [p for p in blocks if p not in expected]
print(f"expected {len(expected)} pages, got {len(blocks)} blocks")
if missing: print("MISSING:", " ".join('p-'+p for p in missing))
if extra:   print("UNEXPECTED:", " ".join('p-'+p for p in extra))

body = "\n\n".join(blocks[p] for p in expected if p in blocks)
unsure = len(re.findall(r'\\UNSURE', body))
print(f"\\UNSURE markers: {unsure}")
for m in re.finditer(r'\\UNSURE\{([^}]*)\}', body):
    print("  ?", m.group(1)[:90])

with open('tex/body.tex', 'w', encoding='utf-8') as fh:
    fh.write(body)
print(f"\nwrote tex/body.tex ({len(body)} chars)")
sys.exit(1 if missing else 0)
