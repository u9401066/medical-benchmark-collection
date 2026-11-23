#!/usr/bin/env bash
# Long-prompt robustness of Inkling 2 Mini next to Clef-Flash (run inside scripts/gpu_window.sh, production paused).
# Round 3 showed that with -ub 256 / 65,536 tokens / q8_0 KV a single 57k-token prompt crashes the server and 2-4 parallel
# long prompts fail with "Compute error": the global layers' relative-bias attention needs ~1 GB more at that length.
# For each candidate: 1 x 57k, 2 x 28k and 4 x 14k-token prompts at once (scripts/stress_long.py), then the prefill speed of
# 5k/19k-token prompts and the decode speed at 1/4 concurrent requests (scripts/slot_sweep.py).
set -u
HERE="$(cd "$(dirname "$0")/../.." && pwd)"
PROD_REPO="${PROD_REPO:-$HOME/llmapi_server}"
IQ4="${INKLING_MODELS:-$HOME/inkling/models}/Inkling-2-Mini-UD-IQ4_XS.gguf"
PORT=8091
URL="http://127.0.0.1:$PORT"
OUT="$HERE/results/slots/longctx"
LOGS="$HERE/results/logs"
PY="$HERE/.venv/bin/python"
REQ='{"temperature":1.0,"top_p":1.0,"top_k":0,"min_p":0.0,"chat_template_kwargs":{"reasoning_effort":"medium"}}'
mkdir -p "$OUT" "$LOGS"
SRV=""
log() { echo "[job $(date -u +%H:%M:%S)] $*"; }
gpu_used() { nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits -i 0 | tr -d ' '; }
serve() {  # serve <tag> VAR=value ...
  local tag=$1; shift
  local slog="$LOGS/inkling-$tag-$(date -u +%Y%m%dT%H%M%SZ).log"
  log "starting $tag: $*"
  env LLM_IGNORE_PAUSE=1 INKLING_PORT=$PORT INKLING_HOST=127.0.0.1 INKLING_MODEL="$IQ4" INKLING_SLOTS=4 INKLING_DRAFT=none "$@" \
    setsid bash "$PROD_REPO/scripts/start_inkling.sh" >> "$slog" 2>&1 < /dev/null &
  SRV=$!
  for _ in $(seq 180); do
    if curl -sf -m 3 "$URL/health" >/dev/null && curl -sf -m 600 "$URL/v1/chat/completions" -H 'Content-Type: application/json' \
        -d '{"messages":[{"role":"user","content":"Say OK."}],"max_tokens":64}' >/dev/null; then
      log "$tag ready (GPU memory used $(gpu_used) MiB)"; return 0
    fi
    kill -0 "$SRV" 2>/dev/null || { log "$tag: server exited: $(grep -i -m2 -E 'out of memory|failed|error' "$slog" | cut -c1-160)"; return 1; }
    sleep 2
  done
  return 1
}
unserve() {
  [ -n "$SRV" ] || return 0
  kill -TERM -- "-$SRV" 2>/dev/null
  for _ in $(seq 30); do kill -0 "$SRV" 2>/dev/null || break; sleep 1; done
  kill -9 -- "-$SRV" 2>/dev/null
  SRV=""
  sleep 3
}
trap unserve EXIT

candidate() {  # candidate <tag> <ctx> <tokens per stress round> VAR=value ...
  local tag=$1 ctx=$2 tot=$3; shift 3
  [ -s "$OUT/$tag.done" ] && return 0
  serve "$tag" INKLING_CTX="$ctx" "$@" || { echo load-failed > "$OUT/$tag.done"; unserve; return 1; }
  local chars=$(( tot * 395 / 100 ))  # ~3.95 characters per token for these abstracts
  for n in 1 2 4; do
    if ! "$PY" "$HERE/scripts/stress_long.py" --url "$URL" --n $n --chars $(( chars / n )) --max-tokens 256 \
        --out "$OUT/$tag-stress-${n}x.json"; then
      log "$tag: stress ${n}x failed"
      kill -0 "$SRV" 2>/dev/null || { unserve; serve "$tag-restart" INKLING_CTX="$ctx" "$@" || { echo crashed > "$OUT/$tag.done"; return 1; }; }
    fi
  done
  "$PY" "$HERE/scripts/slot_sweep.py" --url "$URL" --label "Inkling 2 Mini UD-IQ4_XS, 4 slots, $tag" --concurrency 1,4 --per-slot 3 \
    --request "$REQ" --out "$OUT/$tag-sweep.json" || log "$tag: sweep failed"
  echo done > "$OUT/$tag.done"
  unserve
}

candidate ub256-c65536-q8 65536 57000 INKLING_UBATCH=256
candidate ub128-c65536-q8 65536 57000 INKLING_UBATCH=128
candidate ub64-c65536-q8 65536 57000 INKLING_UBATCH=64
candidate ub256-c65536-f16 65536 57000 INKLING_UBATCH=256 INKLING_KV=f16
candidate ub256-c32768-q8 32768 28000 INKLING_UBATCH=256
candidate ub128-c49152-q8 49152 43000 INKLING_UBATCH=128
log "job done"
