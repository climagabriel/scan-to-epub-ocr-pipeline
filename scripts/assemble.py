#!/usr/bin/env python3
r"""Stage 4: assemble per-page blocks into the book, verifying as it goes.

    /path/to/repo/scripts/assemble.py [repair-output-dir]

Deliberately paranoid, because every failure it guards against is silent:
 - takes the LAST block per page (a model that re-emits a page corrects it)
 - verifies every page book.json expects produced a block, against the
   config rather than any completion marker or self-reported count
 - counts the "I could not read this" markers (\UNSURE / class="unsure"),
   which stay visible in the output and gate the build
 - exits non-zero if any page is missing, so the build stops rather than
   shipping a short book

Profile latex-math writes tex/body.tex (built by build.sh).
Profile xhtml-prose writes build/sections/<id>.xhtml body fragments and
build/sections.json (packaged by build-epub.py), and additionally:
 - checks every page fragment is well-formed XHTML
 - joins a page's <p class="cont"> onto the previous page's last paragraph,
   resolving a word hyphenated across the page break against the system
   word list (keeps the hyphen when the joined word is not a word)
 - turns page footnotes into EPUB pop-up notes, and links superscript note
   references to the Notes section where that note exists
 - inserts book.json "gaps" as visible notices
"""
import glob, html, json, os, re, sys
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import book

cfg = book.load()
src = sys.argv[1] if len(sys.argv) > 1 else None
dirs = [src] if src else sorted(glob.glob('out/repair-*'))
if len(dirs) != 1:
    sys.exit(f'assemble: expected one repair output directory, found {dirs}; name one')
blocks = book.read_blocks(glob.glob(f'{dirs[0]}/c*.raw'))
fixes = 'fixes' if os.path.isdir('fixes') else None
if fixes:
    # Hand-adjudicated corrections: fixes/p-NNN.xhtml replaces that page's
    # block wholesale. Kept apart from model output so a rerun of the model
    # pass cannot silently undo a human decision.
    for f in sorted(glob.glob('fixes/p-*.xhtml')):
        blocks[os.path.basename(f)[:-6]] = open(f, encoding='utf-8').read().strip('\n')

expected = book.expected_pages(cfg)
missing = [p for p in expected if p not in blocks]
extra = sorted(set(blocks) - set(expected))
print(f'expected {len(expected)} pages, got {len(set(blocks) & set(expected))} blocks'
      + (f' ({len(glob.glob("fixes/p-*.xhtml"))} from fixes/)' if fixes else ''))
if missing:
    print('MISSING:', ' '.join(missing))
if extra:
    print('UNEXPECTED (ignored):', ' '.join(extra))

# ---------------------------------------------------------------- latex-math
if cfg['profile'] == 'latex-math':
    body = '\n\n'.join(blocks[p] for p in expected if p in blocks)
    found = re.findall(r'\\UNSURE\{([^}]*)\}', body)
    print(f'\\UNSURE markers: {len(found)}')
    for m in found:
        print('  ?', m[:90])
    os.makedirs('tex', exist_ok=True)
    with open('tex/body.tex', 'w', encoding='utf-8') as fh:
        fh.write(body)
    print(f'wrote tex/body.tex ({len(body)} chars)')
    sys.exit(1 if missing else 0)

# --------------------------------------------------------------- xhtml-prose
WORDS = set()
for path in ('/usr/share/dict/words', '/usr/share/dict/american-english',
             '/usr/share/dict/british-english'):
    if os.path.exists(path):
        WORDS |= {w.strip().lower() for w in open(path, encoding='utf-8', errors='replace')}

problems = []


def parse(page, frag):
    try:
        return ET.fromstring(f'<div>{frag}</div>')
    except ET.ParseError as e:
        problems.append(f'{page}: not well-formed XHTML: {e}')
        return None


def inner(el):
    return html.escape(el.text or '', quote=False) + ''.join(
        ET.tostring(c, encoding='unicode') for c in el)


def outer(el):
    el = ET.fromstring(ET.tostring(el, encoding='unicode'))
    el.tail = None
    return ET.tostring(el, encoding='unicode')


HYPHEN_END = re.compile(r'(\w+)-((?:</\w+>)*)\s*$')
WORD_START = re.compile(r'^((?:<\w+[^>]*>)*)(\w+)')
joins = []


def join(prev, nxt, page):
    m, n = HYPHEN_END.search(prev), WORD_START.search(nxt)
    if m and n:
        a, b = m.group(1), n.group(2)
        whole = (a + b).lower()
        keep = bool(WORDS) and whole not in WORDS and \
            not (whole.endswith('s') and whole[:-1] in WORDS)
        joins.append(f'{page}: {a}-|{b} -> {a + ("-" if keep else "") + b}')
        return prev[:m.start()] + a + ('-' if keep else '') + m.group(2) + nxt
    return prev.rstrip() + ' ' + nxt.lstrip()


sections_out, notes_index, nrefs = [], {}, []
gaps_before = {g['before']: g['note'] for g in cfg['gaps'] if 'before' in g}
gaps_after = {g['after']: g['note'] for g in cfg['gaps'] if 'after' in g}
unsure = []

for sec in book.sections(cfg):
    items = []          # list of [kind, html] where kind is 'p' or 'other'
    footnotes = []      # [id, html]
    fn_seq = 0
    for page in sec['page_list']:
        if page in gaps_before:
            items.append(['gap', f'<p class="gap">{html.escape(gaps_before[page])}</p>'])
        if page not in blocks:
            items.append(['gap', f'<p class="gap">[{page} missing from this build]</p>'])
            continue
        root = parse(page, blocks[page])
        if root is None:
            continue
        if (root.text or '').strip():
            problems.append(f'{page}: loose text outside any element: {root.text.strip()[:60]!r}')
        page_refs = []
        for el in list(root):
            cls = (el.get('class') or '').split()
            if el.tag == 'aside' and 'fn' in cls:
                if 'cont' in cls and footnotes:
                    footnotes[-1][1] += ' ' + inner(el).strip()
                    continue
                fn_seq += 1
                fid = f'fn-{sec["id"]}-{fn_seq}'
                footnotes.append([fid, inner(el).strip(), el.get('data-mark') or '*'])
                page_refs.append((el.get('data-mark') or '*', fid))
                continue
            if el.tag == 'p' and 'cont' in cls:
                if items and items[-1][0] == 'p':
                    prev = items[-1][1]
                    head, body_prev = prev[:prev.index('>') + 1], prev[prev.index('>') + 1:-4]
                    items[-1][1] = head + join(body_prev, inner(el), page) + '</p>'
                    continue
                cls.remove('cont')
                if cls:
                    el.set('class', ' '.join(cls))
                else:
                    el.attrib.pop('class')
            if el.tag == 'p' and 'note' in cls and el.get('data-n'):
                n = el.get('data-n')
                el.set('id', f'note-{n}')
                del el.attrib['data-n']
                notes_index[n] = sec['id']
            items.append(['p' if el.tag == 'p' else 'other', outer(el)])
        # Pair this page's footnote marks with its footnotes, in order.
        for mark, fid in page_refs:
            for k in range(len(items) - 1, -1, -1):
                pat = f'<sup class="fnref">{re.escape(html.escape(mark, quote=False))}</sup>'
                new, hit = re.subn(pat, f'<a epub:type="noteref" class="fnref" id="ref-{fid}" '
                                   f'href="#{fid}">{html.escape(mark, quote=False)}</a>',
                                   items[k][1], count=1)
                if hit:
                    items[k][1] = new
                    break
            else:
                problems.append(f'{page}: footnote {mark!r} has no matching mark in the text')
        if page in gaps_after:
            items.append(['gap', f'<p class="gap">{html.escape(gaps_after[page])}</p>'])
    body = '\n'.join(h for _, h in items)
    left = re.findall(r'<sup class="fnref">', body)
    if left:
        problems.append(f'{sec["id"]}: {len(left)} footnote mark(s) with no footnote text')
    if footnotes:
        body += '\n<section class="footnotes">\n' + '\n'.join(
            f'<aside epub:type="footnote" class="fn" id="{fid}"><p>'
            f'<a class="fnback" href="#ref-{fid}">{html.escape(mark, quote=False)}</a> {text}</p></aside>'
            for fid, text, mark in footnotes) + '\n</section>'
    for m in re.finditer(r'<span class="unsure">(.*?)</span>', body):
        unsure.append(f'{sec["id"]}: {m.group(1)[:90]}')
    sections_out.append({**{k: v for k, v in sec.items() if k != 'page_list'}, 'body': body})

# Second pass: link superscript note references to the Notes section.
seen_ref = {}
for s in sections_out:
    def link(m, sid=s['id']):
        n = m.group(1)
        if n not in notes_index:
            nrefs.append(f'{sid}: note {n} referenced but not in the Notes (lost with a missing page?)')
            return m.group(0)
        rid = f'nref-{n}' if n not in seen_ref else f'nref-{n}-{len(seen_ref)}'
        seen_ref.setdefault(n, (sid, rid))
        return (f'<a epub:type="noteref" class="nref" id="{rid}" '
                f'href="{notes_index[n]}.xhtml#note-{n}"><sup>{n}</sup></a>')
    s['body'] = re.sub(r'<sup class="nref">(\d+)</sup>', link, s['body'])
def backlink(m):
    # The printed "(6)" opening a note becomes a link back to its first
    # reference in the text, where there is one.
    n = m.group(1)
    if n not in seen_ref:
        return m.group(0)
    sid, rid = seen_ref[n]
    return f'<p class="note" id="note-{n}"><a class="noteback" href="{sid}.xhtml#{rid}">({n})</a>'


for s in sections_out:
    s['body'] = re.sub(r'<p class="note" id="note-(\d+)">\s*\(\1\)', backlink, s['body'])

os.makedirs('build/sections', exist_ok=True)
for s in sections_out:
    with open(f'build/sections/{s["id"]}.xhtml', 'w', encoding='utf-8') as fh:
        fh.write(s.pop('body') + '\n')
with open('build/sections.json', 'w', encoding='utf-8') as fh:
    json.dump(sections_out, fh, indent=2, ensure_ascii=False)

print(f'page-break hyphen joins: {len(joins)}')
for j in joins:
    print('  ', j)
print(f'notes: {len(notes_index)} numbered, {len(seen_ref)} referenced from the text')
for r in nrefs:
    print('  ', r)
print(f'unsure markers: {len(unsure)}')
for u in unsure:
    print('   ?', u)
for p in problems:
    print('PROBLEM', p)
print(f'wrote {len(sections_out)} sections under build/sections/')
sys.exit(1 if missing or problems else 0)
