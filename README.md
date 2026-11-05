# scan-to-epub-ocr-pipeline

Turn a scanned book — a PDF in which every page is a picture — into real,
reflowable, searchable text: an **EPUB** for prose, or a small-format
**LaTeX PDF** for mathematics.

The method is OCR for a cheap first reading, a vision model that reads the
page images to produce the text, two independent model reviewers that proof
it against the same images, and a mechanical cross-check between the model
and the OCR that no model can talk its way past. What a reviewer flags is
adjudicated against the scan before anything ships.

**Everything here is reproducible.** The scripts, the prompts and a per-book
config file are the whole method. Human (or adjudicating-agent) judgement is
needed at exactly two points, both explicit and counted: the page-map
anomalies of stage 2b, and the review findings of stage 4.

Two books have been through it, and they are worked examples below:

| | Kolmogorov, *Foundations of the Theory of Probability* (1950) | Polanyi, *The Tacit Dimension* (1966) |
|---|---|---|
| kind | measure-theoretic monograph | philosophical prose |
| profile | `latex-math` → PDF | `xhtml-prose` → EPUB |
| scan | 88 pages, bilevel JBIG2, 1.2 MB | 102 pages, bilevel CCITT at ~480 dpi, 10.8 MB |
| repair model | Codex, from OCR text only | Claude Opus, from page images + OCR |
| review | Codex (one reviewer) | Grok 4.7 and Claude Sonnet, both from page images |

---

## Rights

**This repository contains the pipeline only — never a built book or a
reconstructed text.** The pipeline (scripts, prompts, this README) is offered
under the MIT licence. A book you run through it keeps whatever copyright
status it has. Point the scripts at your own copy of a scan, and treat the
output as a private reading copy unless you have established that the work
is free to redistribute.

---

## The pipeline

```
scan.pdf
   │ 1   render.sh       one PNG per page, extracted losslessly when possible
   ▼
pages/p-NNN.png
   │ 2   ocr.sh          tesseract --psm 6, parallel
   │ 2b  pagemap.py      printed page numbers → GAPs, INK and SPARSE pages
   │ 2c  views.py        each page as two half-page images a model can read
   ▼
ocr/p-NNN.txt  views/p-NNN-{1,2}.png  pagemap.tsv     + book.json (you write it)
   │ 3a  chunk.py repair     5 pages per prompt
   │ 3b  run-model.sh <claude|grok|codex> repair
   ▼
out/repair-<provider>/c-*.raw         one delimited block per page
   │ 3c  diffcheck.py        model output vs OCR, word level, model-free
   │ 3d  chunk.py review + run-model.sh <provider> review   (one or more reviewers)
   ▼
out/review-<provider>/c-*.raw         one AUDIT block per page
   │ 4a  findings.py         all reviewers' findings per page, agreement marked
   │ 4b  adjudicate against the images → fixes/p-NNN.xhtml
   │     assemble.py         coverage check, joins, notes, gaps, markers
   ▼
build/sections/*.xhtml     (or tex/body.tex)
   │ 5   build-epub.py       (or build.sh: pdflatex ×2)
   ▼
book/<slug>.epub           (or book/<slug>-<N>pt.pdf)
```

Every script runs **from the book's working directory**, not from this
repository: `/path/to/repo/scripts/ocr.sh`. Each stage reads the previous
stage's files from the current directory, so a book is a directory and can be
rerun from any stage.

### `book.json`

The only place that knows anything about a particular book.
[`examples/`](examples/) has the configs for both worked books.

```json
{
  "title": "...", "author": "...", "publisher": "...", "date": "1966",
  "language": "en", "slug": "short-name",
  "profile": "xhtml-prose",
  "chunk_size": 5,
  "context": "A paragraph the prompts quote: what the book is, its typography
              (running heads, footnote marks, drop caps), and what in this
              copy is not the book (library stamps, marginalia).",
  "sections": [
    {"id": "introduction", "title": "Introduction", "pages": "5-7"},
    {"id": "ch1", "label": "1", "title": "Tacit Knowing", "pages": "9-31"}
  ],
  "skipped": {"p-008": "chapter 1 title page"},
  "gaps": [{"after": "p-097", "note": "Printed pages 96–97 are missing from the scan."}]
}
```

`pages` are **scan** pages (1-based position in the PDF), never printed page
numbers. Pages in no section are not transcribed; `skipped` documents why.
`gaps` become visible notices in the book, so a reader can tell what the scan
lacked.

### 1. Pages — `scripts/render.sh scan.pdf [dpi]`

If the PDF holds exactly one image per page, the images are **extracted
losslessly with `pdfimages`**. Otherwise pages are rasterised with
`pdftoppm -r 400`. This matters more than it looks: scans commonly declare a
nominal 72 ppi page size, so the Polanyi scan's 2066×3522 px page images
claim to be 29"×49" pages, and `pdftoppm -r 400` would have rendered each at
roughly 11500×19500 px. Every PNG is decode-checked afterwards (see
*Failures worth recording*).

### 2. OCR — `scripts/ocr.sh [dpi] [jobs]`

`tesseract --psm 6` ("a single uniform block of text"): on single-column
books the default mode looks for columns that are not there. One tesseract
thread per process, `nproc/2` processes: 102 pages in 17 s.

### 2b. Page map — `scripts/pagemap.py`

Reads the printed folio off each page, then reports:

- **GAP** — the printed numbers jump. Either an unnumbered chapter opening
  and blank pages, or pages missing from the scan. On Polanyi it found that
  printed pp. 96–97 and 101–102 were never scanned, which no later stage can
  see: every page that *is* there transcribes perfectly.
- **INK** — ink but almost no OCR text: a photograph, a plate, a truncated
  image, a display title.
- **SPARSE** — little of either: a blank or a title page.

Read the images around each anomaly and record the outcome in `book.json`.

### 2c. Model views — `scripts/views.py`

Vision models downscale their inputs to roughly 1500 px on the long edge. A
full scan page then comes out about 840 px wide, at which body text is
readable but italics, small capitals and footnotes are not reliably so. Each
page is therefore trimmed to its ink and split into a top and a bottom half,
with a few lines of overlap so no line is only ever seen cut in two. The
prompts tell the model about the overlap.

### 3. Repair — `chunk.py repair` + `run-model.sh <provider> repair`

> **Prose survives OCR. Mathematics does not. And OCR loses everything
> typographic.**

Tesseract on the Polanyi scan produces nearly clean words — and no italics,
no small capitals, no superscript note references, footnotes merged into the
text, pencil marginalia turned into garbage, and occasionally a whole line
dropped (on p. 48 it lost a footnote line naming three chemists). So the
model's job is repair, and **for prose the model reads the page images**: the
OCR is supplied as a helper, the image is the ground truth.

Each provider runs headless, with **file reading as its only tool** and no
writing, shell, web or MCP access. The model emits delimited blocks on
stdout; the scripts do the writing, so every byte passes through the parser.

```sh
MODEL=opus EFFORT=medium scripts/run-model.sh claude repair 6
MODEL=grok-4.7          scripts/run-model.sh grok   repair 4
EFFORT=high             scripts/run-model.sh codex  repair 6
```

Prompts: [`prompts/xhtml-prose-repair.txt`](prompts/xhtml-prose-repair.txt)
and [`prompts/latex-math-repair.txt`](prompts/latex-math-repair.txt). The
prose output is a small XHTML vocabulary: `<p>`, `<p class="cont">` for a
paragraph continued from the previous page (decided by the first line's
*indentation*, not by grammar), `<em>`, small caps, block quotations,
footnote marks and texts, note references, numbered notes, and an *unsure*
marker.

`run-model.sh` is resumable and does not trust exit codes. A chunk counts as
done only when its output holds a block for every page the chunk was given;
an incomplete chunk is retried once, and a rerun redoes only what is still
incomplete. `PAGES=p-049,p-050 CHUNK_SIZE=1 chunk.py repair` rebuilds just
those pages, one per prompt; chunks are named by page range so a retry lands
beside earlier output, and the newest block for a page wins.

#### The unsure contract

A model that cannot read something produces a *plausible* something. In a
probability monograph a plausible-but-wrong formula typesets beautifully and
is silently false; in prose, a plausible word is never found again. So both
repair prompts make admitting blindness the success case: `\UNSURE{...}` in
LaTeX, `<span class="unsure">[? ...]</span>` in XHTML. Markers render
**visibly** in the output, and `assemble.py` counts and lists every one.

And it only covers half the risk. On Kolmogorov, spot checks found
mathematics transcribed *confidently and wrongly* with no marker: a finite
sum bounding a probability came back as a limit with the inequality
flattened to an equality, and an OCR error in a section cross-reference was
carried straight through. A marker means the model knew it was blind.
**Nothing in a single pass catches the cases where it was blind and did not
know.** That is what stages 3c and 3d are for.

### 3c. Mechanical cross-check — `scripts/diffcheck.py`

The OCR is noisy but it is *independent of the model*: it cannot drop a
sentence because it decided to, and it cannot invent one. A word-level diff
between OCR and output flags any run of six or more words present in only one
of them, plus any page whose overall similarity is low. On Polanyi it flagged
4 of 95 pages: one real omission (an *Erratum* notice the model had treated as
not part of the book), and three places where the model was right and
tesseract had dropped or garbled a line.

### 3d. Review — `chunk.py review` + `run-model.sh <provider> review`

A reviewer gets, per page, the two image halves, the OCR and the repaired
fragment, and is told to hunt, in order: omissions, inventions, wrong
words, italics, structure, meaning-changing punctuation — and that CLEAN is
the normal outcome and a false finding costs a human a lookup. It may not
write corrected text; it quotes both sides. Prompts:
[`prompts/xhtml-prose-review.txt`](prompts/xhtml-prose-review.txt),
[`prompts/latex-math-review.txt`](prompts/latex-math-review.txt).

Use **a different model from the repair pass**, and ideally two from
different vendors: their blind spots differ, and agreement between them is
the strongest signal you get without a human proofreader.

### 4a. Collect findings — `scripts/findings.py [--md findings.md]`

Merges every `out/review-*` directory page by page, most severe first, marks
a finding `[also: <reviewer>]` when another reviewer quoted the same words,
and lists pages a reviewer returned no audit for (a missing audit is not a
clean page). Ends with each reviewer's CLEAN count.

On Polanyi, Claude Sonnet passed 93 of 95 pages and Grok 4.7 passed 91. They
agreed on the two real defects in the text: the *Erratum* on p. 99 and the
section-break ornament on p. 83. Neither noticed that four other
ornament pages had lost theirs too; that turned up when the p. 83 fix was
checked against the book's other section breaks, so search for the same
defect elsewhere whenever you confirm one. Of Grok's four solo findings, one
was real (book entries in the bibliography split into title and imprint
paragraphs). Three were wrong: it called two italic *See*s roman, and read
a tightly kerned "Modern" as "Modem", copying tesseract's misreading. A
single reviewer's finding is a lead to check, not a verdict.

### 4b. Adjudicate, then assemble — `scripts/assemble.py`

Every review finding is checked against the page image. A confirmed one is
fixed by writing the corrected page to `fixes/p-NNN.xhtml`, which replaces
that page's model block wholesale. Corrections live apart from model output
so that rerunning a model pass can never silently undo them.

`assemble.py` then:

- verifies every page in `book.json` produced a block — against the config,
  never against a model's own completion marker — and exits non-zero if not;
- checks each page fragment is well-formed XHTML;
- joins continued paragraphs across page breaks, resolving a word hyphenated
  across the break against the system word list, and prints every join;
- pairs footnote marks with footnotes per page, links superscript note
  references to the Notes, and lists references whose note is not there;
- inserts the `gaps` notices, and counts the unsure markers.

### 5. Build

- **EPUB** — `scripts/build-epub.py`: EPUB 3 with an EPUB 2 `toc.ncx` for
  older readers; footnotes as `epub:type="noteref"`/`"footnote"`, which
  Kindle and Apple Books show as pop-ups. It adds a generated title page and
  an *About this edition* page that says the text is a machine transcription
  and lists everything the scan was missing. Every document is checked for
  well-formedness before zipping. Smoke test:
  `ebook-convert book/<slug>.epub /tmp/x.azw3`.
- **PDF** — `scripts/build.sh [pt]` (default 8): `tex/preamble.tex` targets a
  90×120 mm e-reader page. The `fontsize` package sets the base size so that
  `\small`, headings and math script sizes all follow; what the eye judges on
  an e-reader is characters per line, which the build reports. LaTeX errors
  are reported and fail the build, rather than being recovered from silently.
  The book directory supplies `tex/frontmatter.tex` and `tex/closing.tex`.

---

## Running a book

Requires `poppler-utils`, `tesseract-ocr`, Python 3 with Pillow and NumPy,
`jq`, a word list in `/usr/share/dict`, and at least one of the `claude`,
`grok` or `codex` CLIs. LaTeX output also needs `texlive-latex-recommended`
and `texlive-science`; Calibre's `ebook-convert` is optional.

```sh
mkdir mybook && cd mybook
R=/path/to/scan-to-epub-ocr-pipeline/scripts
$R/render.sh ~/scans/mybook.pdf
$R/ocr.sh 450 10
$R/pagemap.py                  # then write book.json
$R/views.py
$R/chunk.py repair
MODEL=opus $R/run-model.sh claude repair 6
$R/diffcheck.py
$R/chunk.py review
MODEL=grok-4.7 $R/run-model.sh grok review 4
MODEL=sonnet EFFORT=high $R/run-model.sh claude review 4
$R/findings.py --md findings.md
# adjudicate findings -> fixes/p-NNN.xhtml
$R/assemble.py
$R/build-epub.py
```

---

## Failures worth recording

Kept because they cost real time and are not obvious in advance.

**`claude --print --output-format json` keeps only the last text block.**
The repair prompt asks the model to write each page as soon as it is done,
which it does — one text block per page, between its image reads. JSON mode
returns only the final block, so a five-page chunk came back as one page
with exit status 0. `run-model.sh` uses `stream-json` and concatenates every
assistant text block.

**A model can write a page in its reasoning and not in its reply.** One
Polanyi chunk came back with one page out of five on four attempts, two of
them after the prompt was changed to say in so many words that reasoning is
not output: the model read all ten images, wrote four pages where only it
could see them, and replied with the fifth. The completeness check caught it
every time, and rerunning those four pages one per prompt fixed it. The
lesson is the check, not the prompt wording.

**Nominal page sizes.** See stage 1: rasterising a 72 ppi-declared scan at
400 dpi would have produced images roughly 30 times larger than the actual
scan, for no gain.

**A killed renderer leaves a truncated PNG that OCRs to zero bytes.** On
Kolmogorov, page 46 was in flight when `pdftoppm` was killed by a timeout;
tesseract produced an empty `.txt` without erroring, indistinguishable from
the genuinely blank pages 84–88. Caught by measuring ink per page rather
than trusting file sizes, which is now what `pagemap.py` reports as INK.

**Codex buffers stdout until it exits**, so watching its output file shows
nothing until the end; and its `model_reasoning_effort` defaults to `none`,
far too shallow for reconstructing notation. `run-model.sh` passes `high`.

**`pgrep --full` matches the process that runs it.** A background waiter
built as `while pgrep --full 'run-model.sh grok review'; do sleep 15; done`
never exits, because that pattern is in the waiter's own command line. Grok
finished all 95 audits at 13:23; the waiter was still polling an hour later.
Wait on the PID (`wait`, or `tail --pid=N --follow /dev/null`), or a
pattern the waiter itself does not contain, such as `pgrep --full '[r]un-model.sh'`.

**Swallowed LaTeX errors.** The Kolmogorov build ran `pdflatex … || true`,
and its body has an unbalanced `\begin{proof}` that LaTeX silently closed at
`\end{document}`. `build.sh` now reports recovered errors and exits non-zero.
