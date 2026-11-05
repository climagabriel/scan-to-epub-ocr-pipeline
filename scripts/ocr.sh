#!/bin/bash
# OCR every rendered page that has no .txt yet. Idempotent, re-runnable.
cd /home/gabriel/misc_repos/kolmogorov-ocr
for img in pages/p-*.png; do
    base=$(basename "$img" .png)
    out="ocr/${base}.txt"
    [ -s "$out" ] && continue
    nice -n 10 tesseract "$img" "ocr/${base}" -l eng --psm 6 --dpi 400 >/dev/null 2>&1
    echo "ocr: $base"
done
echo "OCR_PASS_DONE $(ls ocr/*.txt 2>/dev/null | wc -l) txt files"
