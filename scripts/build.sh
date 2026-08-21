#!/bin/sh
set -eu
cd "$(dirname "$0")"
mkdir -p book
cat tex/preamble.tex tex/frontmatter.tex tex/body.tex tex/closing.tex > tex/kolmogorov.tex
pdflatex --interaction=nonstopmode --output-directory=book tex/kolmogorov.tex >/dev/null 2>&1 || true
pdflatex --interaction=nonstopmode --output-directory=book tex/kolmogorov.tex >/dev/null 2>&1 || true
ls -l book/kolmogorov.pdf
