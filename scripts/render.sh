#!/bin/bash
# Stage 1: turn the scan into one PNG per page, pages/p-NNN.png (1-based).
#
# Run from the book's working directory, not from this repository:
#     /path/to/repo/scripts/render.sh path/to/scan.pdf [dpi]
#
# Two paths, chosen automatically:
#  - If the PDF holds exactly one image per page, the images are extracted
#    losslessly with pdfimages. This is the common case for scans, and the
#    only correct one when the PDF declares a nominal page size: a scan stored
#    as 2066x3522 px "at 72 ppi" is a 29"x49" page to pdftoppm, and -r 400
#    would render it at roughly 11500x19500 px.
#  - Otherwise every page is rasterised with pdftoppm at the given dpi
#    (default 400; oversampling a 300 dpi bilevel scan helps tesseract's line
#    segmentation and there is no blur to amplify).
set -euo pipefail
SRC="${1:?usage: render.sh path/to/scan.pdf [dpi]}"
DPI="${2:-400}"
mkdir --parents pages

pages=$(pdfinfo "$SRC" | awk '/^Pages:/{print $2}')
one_per_page=$(pdfimages -list "$SRC" | awk -v n="$pages" '
    NR>2 && $3=="image" {c[$1]++; t++}
    END {ok = (t==n); for (p in c) if (c[p]!=1) ok=0; print ok}')

if [ "$one_per_page" -eq 1 ]; then
    echo "one image per page ($pages pages): extracting natively"
    tmp=$(mktemp --directory pages/.extract.XXXX)
    nice --adjustment=10 pdfimages -png "$SRC" "$tmp/raw"
    for f in "$tmp"/raw-*.png; do
        n=${f##*/raw-}; n=${n%.png}
        mv "$f" "pages/p-$(printf '%03d' $((10#$n + 1))).png"
    done
    rmdir "$tmp"
else
    echo "not one image per page: rasterising $pages pages at ${DPI} dpi"
    nice --adjustment=10 pdftoppm -r "$DPI" -gray -png "$SRC" pages/r
    for f in pages/r-*.png; do
        n=${f##*/r-}; n=${n%.png}
        mv "$f" "pages/p-$(printf '%03d' $((10#$n))).png"
    done
fi
echo "rendered $(ls pages/p-*.png | wc --lines) pages"

# Integrity check. A killed renderer leaves a truncated PNG that later OCRs to
# zero bytes and is indistinguishable from a genuinely blank page.
python3 - <<'PY'
from PIL import Image
import glob, sys
bad = []
for f in sorted(glob.glob('pages/p-*.png')):
    try:
        Image.open(f).load()
    except Exception as e:
        bad.append((f, e))
for f, e in bad:
    print(f"TRUNCATED: {f}: {e}", file=sys.stderr)
sys.exit(1 if bad else 0)
PY
echo "all PNGs decode cleanly"
