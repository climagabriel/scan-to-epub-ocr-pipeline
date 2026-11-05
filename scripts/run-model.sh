#!/bin/bash
# Stage 3b: run one model pass over every chunk of a stage, in parallel.
#
#     /path/to/repo/scripts/run-model.sh <claude|grok|codex> <repair|review> [jobs]
#
# Env: MODEL, EFFORT override the provider defaults below; TIMEOUT (seconds,
# default 1500) bounds one chunk.
#
# Writes out/<stage>-<provider>/cNN.raw. Resumable: a chunk whose .raw
# already holds a block for every page in its .pages file is skipped, so a
# rerun only redoes the failures. A chunk is retried once if its output is
# missing pages, because an exit code of 0 proves nothing: a model can stop
# early, or lose part of its plan to context compaction, and still exit 0.
#
# Every provider runs with file READING only (the page images) and no
# writing, shell, web or MCP tools: the model emits text on stdout and these
# scripts do the writing, so every byte passes through the block parser.
set -euo pipefail
PROVIDER="${1:?usage: run-model.sh <claude|grok|codex> <repair|review> [jobs]}"
STAGE="${2:?usage: run-model.sh <claude|grok|codex> <repair|review> [jobs]}"
JOBS="${3:-4}"
TIMEOUT="${TIMEOUT:-1500}"
OUT="out/${STAGE}-${PROVIDER}"
mkdir --parents "$OUT"
[ "$STAGE" = review ] && TAG=AUDIT || TAG=PAGE
export PROVIDER STAGE OUT TAG TIMEOUT MODEL="${MODEL:-}" EFFORT="${EFFORT:-}"

run_one() {
    c="$1"; i=$(basename "$c" .txt); pages="${c%.txt}.pages"
    complete() {
        [ -s "$OUT/$i.raw" ] || return 1
        while read -r p; do
            grep --quiet --fixed-strings "<<<END $p>>>" "$OUT/$i.raw" || return 1
        done < "$pages"
    }
    complete && { echo "$i: already complete"; return 0; }
    for attempt in 1 2; do
        case "$PROVIDER" in
        claude)
            # --safe-mode: no hooks, plugins, CLAUDE.md or memory from the
            # host, so the run sees the prompt and nothing else.
            # stream-json, not json: --output-format json returns only the
            # LAST assistant text block, and a model that emits each page
            # between its image reads (as the prompt asks) writes one text
            # block per page -- json mode silently keeps the last page only.
            timeout "$TIMEOUT" env --unset=SSLKEYLOGFILE CLAUDE_CODE_DISABLE_FAST_MODE=1 \
                claude --print --model "${MODEL:-sonnet}" --effort "${EFFORT:-medium}" \
                --output-format stream-json --verbose --safe-mode --tools Read --allowedTools Read \
                --strict-mcp-config --mcp-config '{"mcpServers":{}}' \
                --no-session-persistence < "$c" > "$OUT/$i.jsonl" 2> "$OUT/$i.err" || true
            jq --raw-output 'select(.type == "assistant") | .message.content[]
                             | select(.type == "text") | .text' "$OUT/$i.jsonl" \
                > "$OUT/$i.raw" 2>> "$OUT/$i.err" || true ;;
        grok)
            # grok's file tool only reaches the working directory, which is
            # why the chunk prompts give image paths under it.
            timeout "$TIMEOUT" env --unset=SSLKEYLOGFILE \
                grok --cwd "$PWD" --prompt-file "$c" --model "${MODEL:-grok-4.7}" \
                --reasoning-effort "${EFFORT:-medium}" --tools read_file \
                --disable-web-search --no-subagents --permission-mode dontAsk \
                --output-format plain < /dev/null > "$OUT/$i.raw" 2> "$OUT/$i.err" || true ;;
        codex)
            # model_reasoning_effort defaults to none, far too shallow for
            # this; codex also buffers stdout until it exits.
            timeout "$TIMEOUT" env --unset=SSLKEYLOGFILE \
                codex exec --sandbox read-only --skip-git-repo-check \
                ${MODEL:+--model "$MODEL"} -c model_reasoning_effort="${EFFORT:-high}" \
                - < "$c" > "$OUT/$i.raw" 2> "$OUT/$i.err" || true ;;
        *) echo "unknown provider $PROVIDER" >&2; return 2 ;;
        esac
        if complete; then
            echo "$i: ok (attempt $attempt, $(grep --count "<<<$TAG " "$OUT/$i.raw") blocks)"
            return 0
        fi
        echo "$i: incomplete on attempt $attempt ($(grep --count "<<<$TAG " "$OUT/$i.raw" || true) of $(wc --lines < "$pages") blocks)" >&2
    done
    return 1
}
export -f run_one

fail=0
ls chunks/"$STAGE"/c*.txt | xargs --max-procs="$JOBS" --replace={} bash -c 'run_one {}' || fail=1
echo "=== $STAGE/$PROVIDER: all chunks returned ==="
[ "$fail" -eq 0 ] || { echo "some chunks are still incomplete; rerun to retry them" >&2; exit 1; }
