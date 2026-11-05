#!/bin/bash
# Stage 2: tesseract every page image that has no OCR text yet.
# Idempotent and re-runnable. Run from the book's working directory:
#     /path/to/repo/scripts/ocr.sh [dpi] [jobs]
#
# --psm 6 ("one uniform block of text") beats the default on single-column
# books: the default segmentation hunts for columns that are not there.
# Pass the scan's real resolution as dpi. pdfimages -list reports 72 for most
# scans, which is a nominal value, not the truth: estimate it from the pixel
# width of a page and the book's trim width instead.
set -euo pipefail
DPI="${1:-400}"
JOBS="${2:-$(( $(nproc) / 2 ))}"
mkdir --parents ocr
export DPI
# One tesseract thread per process: N single-threaded processes are much
# faster than N processes each spawning an OpenMP pool.
ls pages/p-*.png | xargs --max-procs="$JOBS" --replace={} sh -c '
    base=$(basename {} .png)
    [ -s "ocr/$base.txt" ] && exit 0
    OMP_THREAD_LIMIT=1 nice --adjustment=10 \
        tesseract {} "ocr/$base" -l eng --psm 6 --dpi "$DPI" >/dev/null 2>&1
    echo "ocr: $base"'
echo "OCR_PASS_DONE $(ls ocr/*.txt 2>/dev/null | wc --lines) txt files"
