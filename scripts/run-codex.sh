#!/bin/bash
# Six parallel Codex processes, 13 pages each.
#
# Why chunked and parallel rather than one long run: a long run can have its
# context compacted mid-flight, and anything the model planned to emit "at the
# end" is silently lost -- the process still exits 0 with a plausible-looking
# terminal marker. Small chunks bound the blast radius, and assemble.py
# verifies the emitted blocks against the input list rather than trusting any
# self-reported count.
#
# --sandbox read-only is intentional: Codex never writes to the tree. It emits
# LaTeX on stdout and these scripts do the writing.
set -euo pipefail
mkdir -p out
for c in chunks/c*.txt; do
    i=$(basename "$c" .txt)
    ( env -u SSLKEYLOGFILE nice -n 5 codex exec --sandbox read-only --skip-git-repo-check \
        -c model_reasoning_effort="high" - < "$c" > "out/$i.raw" 2> "out/$i.err"
      echo "$i exit=$? bytes=$(wc -c < out/$i.raw)" ) &
done
wait
echo "=== all chunks returned ==="
for f in out/c*.raw; do printf '%s: %s blocks\n' "$(basename $f .raw)" "$(grep -c '<<<PAGE' "$f" || true)"; done
