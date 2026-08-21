# Kolmogorov, *Foundations of the Theory of Probability* — Kindle edition

A rebuild of A. N. Kolmogorov's *Foundations of the Theory of Probability*
(Chelsea Publishing Company, New York, 1950; Nathan Morrison's translation of
the 1933 *Grundbegriffe der Wahrscheinlichkeitsrechnung*) from a scanned PDF
into a small-format, text-based PDF that is actually readable on a Kindle.

The scan is a 1.2 MB, 88-page bilevel JBIG2 image PDF. Every page is a picture.
On a 6" e-reader that means pan-and-zoom on a 5.6"×8.75" page, no text reflow,
no selection, no search. This repository contains the pipeline that turns it
into real text, and the result.

**Everything here is reproducible.** The scripts, the prompt, and the LaTeX
preamble are the whole method — there is no hand-editing step hidden between
them, and the one place where human judgement is required is explicit and
counted (see *The `\UNSURE` contract* below).

---

## Provenance and rights

Read this before reusing the built book.

- The underlying work is Kolmogorov's 1933 *Grundbegriffe*.
- **This is the 1950 Chelsea English translation by Nathan Morrison**, whose
  copyright page reads `COPYRIGHT 1950 BY CHELSEA PUBLISHING COMPANY`. A
  separate 1956 copyright exists for the second edition.
- Under US law a 1950 work published with notice entered a 28-year term,
  renewable in 1977–78 for a total of 95 years. **We did not verify whether
  that renewal was filed.** If it was, the translation is protected until 2045
  and the rightsholder lineage runs Chelsea → American Mathematical Society. If
  it was not, the translation is in the US public domain.
- We make **no public-domain claim**. Settling it requires a Class A renewal
  search in the *Catalog of Copyright Entries*, Part 1A, for 1977 and 1978 —
  or a query against Stanford's
  [Copyright Renewal Database](https://exhibits.stanford.edu/copyrightrenewals).

**This repository contains the pipeline only. The built book is not
published here, and neither is the reconstructed text.** The pipeline
(scripts, prompt, preamble, this README) is our own work and is offered under
the MIT licence. The book text carries whatever status the 1950 Morrison
translation carries — and since we could not establish that status,
redistributing a full book-length reconstruction of it is not something this
repository does. Point the scripts at your own copy of the scan.

---

## Result

| | source scan | rebuilt |
|---|---|---|
| type | bilevel page images (JBIG2) | real text |
| page size | 401×630 pt (5.6"×8.75") | 90×120 mm |
| selectable / searchable | no | yes |
| font scales with reader setting | no | yes (rebuild at another size) |
| size | 1.2 MB | 0.7 MB, 190 pages |

---

## The pipeline

Five stages. Stages 1, 2 and 5 are deterministic; stage 3 is the model; stage 4
is the human gate.

```
scan.pdf
   │  1. pdftoppm -r 400 -gray -png
   ▼
pages/p-NN.png            88 page images
   │  2. tesseract -l eng --psm 6
   ▼
ocr/p-NN.txt              raw OCR, prose clean / math destroyed
   │  3. codex exec  (6 parallel chunks, 13 pages each)
   ▼
out/cNN.raw               per-page LaTeX blocks
   │  4. assemble.py  → verify coverage, count \UNSURE
   ▼
tex/body.tex
   │  5. pdflatex ×2
   ▼
book/kolmogorov.pdf
```

### 1. Rasterise — `scripts/render.sh`

```sh
pdftoppm -r 400 -gray -png source.pdf pages/p
```

400 dpi from a 300 dpi source is deliberate oversampling: tesseract's line
segmentation behaves better with the extra pixels, and the source is bilevel so
there is no interpolation blur to worry about.

### 2. OCR — `scripts/ocr.sh`

```sh
tesseract pages/p-NN.png ocr/p-NN -l eng --psm 6 --dpi 400
```

`--psm 6` ("a single uniform block of text") beats the default on this book —
the default page-segmentation mode tries to find columns that are not there and
fragments the running text.

The script is idempotent: it skips any page that already has a non-empty
`.txt`. That matters more than it sounds — see *Failures worth recording*.

### 3. The Codex pass — `prompts/codex-latex-repair.txt`

This is the stage that does the real work, and it exists because of one fact:

> **Prose survives OCR. Mathematics does not.**

Tesseract on this scan produces near-perfect English and near-useless
mathematics. A representative failure, from page 30 of the scan:

```
Let now E = {&,, &,..., én, ...} be a countable set, and let $
coincide with the aggregate of the subsets of E.
...
and for each set A put
where the summation >’ extends to all the indices n for which
```

Three separate failures in six lines: the indexed family `ξ₁, ξ₂, …, ξₙ` is
mangled to `&,, &,..., én`; the fraktur field symbol became `$`; and the
display equation between "put" and "where" was **dropped entirely** — the OCR
leaves no trace that anything was there.

So the model's job is not transcription, it is *repair*. It is invoked as:

```sh
env -u SSLKEYLOGFILE codex exec --sandbox read-only --skip-git-repo-check \
  -c model_reasoning_effort="high" - < chunks/cNN.txt
```

Three details that are easy to get wrong:

- **`model_reasoning_effort` defaults to `none`.** Left unset, Codex answers at
  roughly search-and-summarise depth, which is nowhere near enough to
  reconstruct measure-theoretic notation from corrupted text.
- **`--sandbox read-only`** means Codex cannot write files. It emits LaTeX on
  stdout and the surrounding scripts do the writing. This is a feature: every
  byte it produces passes through `assemble.py` and gets counted.
- **Chunk the input and force incremental emission.** A long run can have its
  context compacted mid-flight, and anything the model planned to emit "at the
  end" is silently lost — the run still exits 0. So: 13 pages per process, six
  processes in parallel, and rule 1 of the prompt forbids reading the corpus
  before emitting. `assemble.py` then verifies the emitted blocks against the
  input list mechanically rather than trusting any completion marker.

### 4. The `\UNSURE` contract — the part that matters

A model asked to reconstruct a dropped equation will produce a *plausible* one.
In a probability monograph a plausible-but-wrong formula is undetectable
downstream: it typesets beautifully and it is silently false. This is the
single largest risk in the whole project and it is why rule 4 of the prompt
reads:

> A `\UNSURE` marker is a success: a human will read the page image and fill it
> in. An invented formula that looks plausible is the single worst outcome of
> this job, because it is undetectable downstream. When torn between
> reconstructing and marking, MARK.

`\UNSURE{...}` renders **visibly** in the PDF as `[? description]`. It is not a
silent comment. `assemble.py` counts every occurrence and prints it, and each
one is then resolved by reading the actual page image and supplying the
formula by hand.

The honest summary of this pipeline is therefore: *the model does 100% of the
transcription and the human does 100% of the adjudication of what the model
admitted it could not read.* That division only works because the model was
instructed to admit it.

**And it only covers half the risk.** Spot-checking the output against the page
images turned up a second, worse failure class: mathematics the model
transcribed *confidently and wrongly*, with no marker. On one page a finite sum
bounding a probability came back as a limit, with the inequality flattened to an
equality and the summation index silently renamed. On another, an OCR error in a
cross-reference (a section number) was carried straight through into clean
LaTeX. Both typeset perfectly.

So the contract's real scope is narrower than it first appears:

> `\UNSURE` catches **dropped** content. It does not catch **misread** content.

A marker means the model knew it was blind. Nothing in the pipeline detects the
cases where it was blind and didn't know. The only remedy is page-by-page
comparison against the images by someone who can read the mathematics, and this
pipeline does not do that for you. Treat any output of it as a draft to be
proofread, not as a faithful edition.

### 5. Typeset — `scripts/build.sh`

`tex/preamble.tex` targets a 90×120 mm page with 5 mm margins — an e-reader
trim size, not a paper one. The non-obvious settings:

- `\abovedisplayskip` etc. cut to 4 pt. At this page size default display
  skips push almost every equation onto its own page.
- `\raggedbottom` and `\sloppy`. On a 90 mm measure, justified text with
  default tolerances produces constant overfull boxes; loose lines are the
  better trade.
- `\UNSURE` is defined in the preamble, so an unresolved marker cannot be
  compiled away by accident.

---

## Failures worth recording

Kept because they cost real time and are not obvious in advance.

**A killed `pdftoppm` leaves a truncated PNG that OCRs to zero bytes.** The
first render was interrupted by a timeout; page 46 was in flight and was left
as a valid-looking but truncated file. Tesseract produced an empty `.txt` for
it without erroring, and the empty file looked exactly like the genuinely blank
pages 84–88. It was caught by measuring ink coverage per page rather than
trusting file sizes:

```python
a = np.array(Image.open(png).convert('L'))
ink = (a < 128).mean()      # 0.0 = blank page; >0.04 = has content
```

A page with ink and no OCR text is a bug. A page with no ink and no OCR text is
a blank page. Without that distinction the corrupt page would have shipped as a
silently missing page of the book.

**Codex buffers stdout to the end of the run.** Watching the output file for
partial results shows nothing until the process exits; the visible stream on
stderr is just the echoed prompt. Progress has to be judged another way.

---

## Reproducing

Requires `poppler-utils`, `tesseract-ocr`, `texlive-latex-recommended`,
`texlive-science`, and the `codex` CLI.

```sh
./scripts/render.sh path/to/scan.pdf
./scripts/ocr.sh
./scripts/chunk.py                  # build the per-chunk prompts
./scripts/run-codex.sh              # six parallel processes
./scripts/assemble.py               # verify coverage, count \UNSURE
./scripts/build.sh                  # pdflatex ×2
```

`assemble.py` exits non-zero if any expected page failed to produce a block, so
the build stops rather than silently shipping a short book.
