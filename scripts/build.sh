#!/bin/sh
# Stage 5 (latex-math): typeset tex/body.tex into a small-format PDF.
#
#     /path/to/repo/scripts/build.sh [fontsize_pt]     (default 8)
#
# Run from the book's working directory. Uses the repository's
# tex/preamble.tex unless the book directory has its own; the book supplies
# tex/frontmatter.tex and tex/closing.tex. On an e-reader the page is scaled
# to the screen, so perceived type size is set by characters per line, not by
# the pt value; both are reported after the build.
set -eu
REPO="$(cd "$(dirname "$0")/.." && pwd)"
SIZE="${1:-8}"
SLUG="$(python3 -c 'import json; print(json.load(open("book.json")).get("slug", "book"))')"
PRE=tex/preamble.tex; [ -f "$PRE" ] || PRE="$REPO/tex/preamble.tex"
for f in tex/frontmatter.tex tex/body.tex tex/closing.tex; do
    [ -f "$f" ] || { echo "missing $f" >&2; exit 1; }
done
mkdir --parents book
TEX="tex/${SLUG}-${SIZE}pt.tex"
sed "s/fontsize=[0-9.]*pt/fontsize=${SIZE}pt/" "$PRE" > "$TEX.tmp"
cat "$TEX.tmp" tex/frontmatter.tex tex/body.tex tex/closing.tex > "$TEX"
rm --force "$TEX.tmp"
# Two passes for the table of contents. nonstopmode recovers from errors and
# still writes a PDF, which is useful for proofreading -- but a recovered
# error means LaTeX guessed (an unclosed environment closed at the end of
# the document, a bad macro dropped), so errors are reported and the build
# exits non-zero instead of being swallowed.
pdflatex --interaction=nonstopmode --output-directory=book "$TEX" >/dev/null 2>&1 || true
pdflatex --interaction=nonstopmode --output-directory=book "$TEX" >/dev/null 2>&1 || true
PDF="book/${SLUG}-${SIZE}pt.pdf"
LOG="book/${SLUG}-${SIZE}pt.log"
[ -f "$PDF" ] || { echo "pdflatex produced no PDF; see $LOG" >&2; exit 1; }
errors=$(grep --count '^!' "$LOG" || true)
printf '%-6s pages=%-4s chars/line=%-4s %s\n' "${SIZE}pt" \
  "$(pdfinfo "$PDF" | awk '/^Pages/{print $2}')" \
  "$(pdftotext "$PDF" - | awk 'length>25{n++;s+=length} END{printf "%d", s/n}')" "$PDF"
if [ "$errors" -gt 0 ]; then
    echo "$errors LaTeX error(s), recovered from but not fixed (first ones below; all in $LOG):" >&2
    grep --max-count=5 --after-context=2 '^!' "$LOG" >&2 || true
    exit 1
fi
