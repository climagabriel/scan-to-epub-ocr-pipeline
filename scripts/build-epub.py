#!/usr/bin/env python3
"""Stage 5 (prose): package build/sections/ into an EPUB 3 book.

    /path/to/repo/scripts/build-epub.py

Writes book/<slug>.epub. Plain EPUB 3 with an EPUB 2 toc.ncx alongside, so
older Kindle and Kobo firmware gets a table of contents too; footnotes use
epub:type="noteref"/"footnote", which Kindle and Apple Books show as
pop-ups and everything else shows as ordinary links.

Adds two pages the scan does not have: a title page generated from
book.json, and an "About this edition" page at the end that says how the
text was made and lists every gap, so a reader of the EPUB alone can tell
what is missing and that the text is machine-made.

Every XHTML file is checked for well-formedness before it is zipped; the
build fails rather than produce a book a reader will reject.
"""
import html, json, os, sys, uuid, zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import book

cfg = book.load()
sections = json.load(open('build/sections.json', encoding='utf-8'))
slug = cfg.get('slug') or 'book'
lang = cfg.get('language', 'en')
ident = f'urn:uuid:{uuid.uuid5(uuid.NAMESPACE_URL, "scan-to-epub-ocr-pipeline/" + slug)}'
esc = lambda s: html.escape(s or '', quote=True)

CSS = """\
body { margin: 0 4%; line-height: 1.45; text-align: justify; hyphens: auto; -webkit-hyphens: auto; }
h1 { font-size: 1.4em; text-align: center; margin: 2.5em 0 1.5em; font-weight: normal; letter-spacing: 0.04em; text-transform: uppercase; hyphens: none; }
h1 .label { display: block; font-size: 1.3em; margin-bottom: 0.4em; }
h3 { font-size: 1em; font-weight: bold; margin: 1.2em 0 0.4em; text-align: left; }
p { margin: 0; text-indent: 1.2em; }
h1 + p, h3 + p, .gap + p, p.noindent { text-indent: 0; }
blockquote { margin: 0.6em 1.5em; font-size: 0.95em; }
hr.break { border: 0; margin: 1.2em 0; text-align: center; height: 1em; }
hr.break::after { content: "◇ ◇ ◇"; font-size: 0.8em; }
hr.break + p { text-indent: 0; }
blockquote p { text-indent: 0; }
.bibliography p { text-indent: -1.5em; margin-left: 1.5em; text-align: left; }
.sc { font-variant: small-caps; }
.unsure { font-weight: bold; background: #eee; }
.gap { text-indent: 0; margin: 1em 0; padding: 0.5em 0.7em; border: 1px solid #888; font-size: 0.9em; font-style: italic; }
a.fnref, a.nref { text-decoration: none; }
a.fnref { vertical-align: super; font-size: 0.75em; }
.footnotes { margin-top: 2em; border-top: 1px solid #999; font-size: 0.85em; }
.footnotes p, p.note { text-indent: 0; margin: 0.5em 0; }
p.note { font-size: 0.92em; }
.fnback, .noteback { text-decoration: none; }
.title { text-align: center; text-indent: 0; }
.title .t { font-size: 1.8em; margin: 3em 0 0.8em; letter-spacing: 0.05em; }
.title .a { font-size: 1.2em; margin-bottom: 4em; }
.about p { text-indent: 0; margin: 0.6em 0; text-align: left; }
"""


def page(title, body, epub_ns=True):
    return ('<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n'
            f'<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" '
            f'xml:lang="{lang}" lang="{lang}">\n<head><meta charset="utf-8"/>'
            f'<title>{esc(title)}</title><link rel="stylesheet" type="text/css" href="style.css"/></head>\n'
            f'<body>\n{body}\n</body>\n</html>\n')


files = {}   # name -> (content, media-type, nav title or None)
files['title.xhtml'] = (page(cfg['title'], (
    '<section epub:type="titlepage" class="title">'
    f'<p class="title t">{esc(cfg["title"]).upper()}</p>'
    f'<p class="title a">{esc(cfg["author"])}</p>'
    f'<p class="title">{esc(cfg.get("publisher", ""))}</p>'
    f'<p class="title">{esc(cfg.get("date", ""))}</p></section>')), 'Title page')

order = ['title.xhtml']
for s in sections:
    body = open(f'build/sections/{s["id"]}.xhtml', encoding='utf-8').read()
    nav = s.get('title') or s['id'].replace('-', ' ').capitalize()
    head = ''
    if s.get('title'):
        label = f'<span class="label">{esc(s["label"])}</span>' if s.get('label') else ''
        head = f'<h1>{label}{esc(s["title"])}</h1>\n'
        if s.get('label'):
            nav = f'{s["label"]}. {s["title"]}'
    kind = {'front': 'frontmatter', 'back': 'backmatter'}.get(s.get('kind'), 'bodymatter')
    files[f'{s["id"]}.xhtml'] = (page(nav, f'<section epub:type="{kind}" class="{esc(s["id"])}">\n{head}{body}</section>'), nav)
    order.append(f'{s["id"]}.xhtml')

gaps = ''.join(f'<p>• {esc(g["note"])}</p>' for g in cfg['gaps']) or '<p>None recorded.</p>'
files['about.xhtml'] = (page('About this edition', (
    '<section epub:type="backmatter" class="about"><h1>About this edition</h1>'
    f'<p>This e-book was rebuilt from a scanned copy of the printed book ({esc(cfg.get("publisher", ""))}, '
    f'{esc(cfg.get("date", ""))}). The text was read from the page images by OCR and a vision model, '
    'then checked page by page against the scan by two independent model reviewers, with the '
    'findings adjudicated against the page images. It is a careful machine transcription, not a '
    'publisher\'s edition: treat it as a reading copy, and quote from the printed book.</p>'
    '<p>Running heads, page numbers, library stamps and readers’ marginalia in the scan are omitted. '
    'Where the scan was illegible the text says so in a highlighted bracket.</p>'
    f'<p>Missing from the scan:</p>{gaps}'
    '<p>Made with scan-to-epub-ocr-pipeline (github.com/climagabriel/scan-to-epub-ocr-pipeline).</p>'
    '</section>')), 'About this edition')
order.append('about.xhtml')

for name in order:
    try:
        ET.fromstring(files[name][0].split('\n', 2)[2])
    except ET.ParseError as e:
        sys.exit(f'{name}: not well-formed: {e}')

nav_items = ''.join(f'<li><a href="{n}">{esc(files[n][1])}</a></li>' for n in order)
nav = page('Contents', f'<nav epub:type="toc" id="toc"><h1>Contents</h1><ol>{nav_items}</ol></nav>')
ncx_points = ''.join(
    f'<navPoint id="np{i}" playOrder="{i}"><navLabel><text>{esc(files[n][1])}</text></navLabel>'
    f'<content src="{n}"/></navPoint>' for i, n in enumerate(order, 1))
ncx = ('<?xml version="1.0" encoding="utf-8"?>\n<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">'
       f'<head><meta name="dtb:uid" content="{ident}"/></head><docTitle><text>{esc(cfg["title"])}</text></docTitle>'
       f'<navMap>{ncx_points}</navMap></ncx>\n')
modified = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
manifest = ''.join(f'<item id="i{i}" href="{n}" media-type="application/xhtml+xml"/>'
                   for i, n in enumerate(order))
spine = ''.join(f'<itemref idref="i{i}"/>' for i in range(len(order)))
opf = f'''<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid" xml:lang="{lang}">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
<dc:identifier id="uid">{ident}</dc:identifier>
<dc:title>{esc(cfg["title"])}</dc:title>
<dc:creator>{esc(cfg["author"])}</dc:creator>
<dc:language>{lang}</dc:language>
<dc:publisher>{esc(cfg.get("publisher", ""))}</dc:publisher>
<dc:date>{esc(cfg.get("date", ""))}</dc:date>
<meta property="dcterms:modified">{modified}</meta>
</metadata>
<manifest>
<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
<item id="css" href="style.css" media-type="text/css"/>
{manifest}
</manifest>
<spine toc="ncx">{spine}</spine>
</package>
'''
container = ('<?xml version="1.0" encoding="utf-8"?>\n<container version="1.0" '
             'xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles>'
             '<rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>'
             '</rootfiles></container>\n')

os.makedirs('book', exist_ok=True)
out = f'book/{slug}.epub'
with zipfile.ZipFile(out, 'w') as z:
    # mimetype must be first and stored uncompressed, or readers reject the file.
    z.writestr(zipfile.ZipInfo('mimetype'), 'application/epub+zip', compress_type=zipfile.ZIP_STORED)
    z.writestr('META-INF/container.xml', container, zipfile.ZIP_DEFLATED)
    z.writestr('OEBPS/content.opf', opf, zipfile.ZIP_DEFLATED)
    z.writestr('OEBPS/nav.xhtml', nav, zipfile.ZIP_DEFLATED)
    z.writestr('OEBPS/toc.ncx', ncx, zipfile.ZIP_DEFLATED)
    z.writestr('OEBPS/style.css', CSS, zipfile.ZIP_DEFLATED)
    for n in order:
        z.writestr(f'OEBPS/{n}', files[n][0], zipfile.ZIP_DEFLATED)
print(f'wrote {out} ({os.path.getsize(out) // 1024} KiB, {len(order)} documents)')
