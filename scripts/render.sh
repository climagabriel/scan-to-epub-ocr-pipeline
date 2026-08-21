#!/bin/bash
# Rasterise the scan to 400 dpi grayscale PNGs.
# 400 from a 300 dpi bilevel source is deliberate oversampling: tesseract's
# line segmentation likes the extra pixels and there is no blur to amplify.
set -euo pipefail
SRC="${1:?usage: render.sh path/to/scan.pdf}"
mkdir -p pages
nice -n 10 pdftoppm -r 400 -gray -png "$SRC" pages/p
echo "rendered $(ls pages/*.png | wc -l) pages"

# Integrity check. A killed pdftoppm leaves a truncated PNG that later OCRs to
# zero bytes and is indistinguishable from a genuinely blank page.
python3 - <<'PY'
from PIL import Image
import glob, sys
bad = []
for f in sorted(glob.glob('pages/*.png')):
    try:
        Image.open(f).load()
    except Exception as e:
        bad.append((f, e))
if bad:
    for f, e in bad:
        print(f"TRUNCATED: {f}: {e}", file=sys.stderr)
    sys.exit(1)
print("all PNGs decode cleanly")
PY
