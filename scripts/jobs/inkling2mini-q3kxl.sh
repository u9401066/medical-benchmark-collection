#!/usr/bin/env bash
# Inkling 2 Mini UD-Q3_K_XL on llm01 (run inside scripts/gpu_window.sh, production paused, Clef-Flash stays on the GPU).
# UD-IQ4_XS left ~0.5 GB of the card free under load and every 4-slot setting crashed or failed under some load pattern
# (results/slots/longctx); Q3_K_XL is 1.95 GiB smaller.
#   1. stability: 65,536 tokens shared by 4 slots, -ub 256 then 128 then 64 until one survives long-prompt stress (1x54k, 2x27k,
#      4x13.5k tokens at once), a load sweep (1/2/4 + 5k/19k prompts), and the stress and 4 concurrent requests once more
#   2. 131,072 tokens (-ub 128 / 64): 1x110k and 4x27k tokens
#   3. tool calling (52 held-out queries: all tools / Clef 2-pass; 110 hard queries with 61 tools), one request at a time
#   4. medical QA on the same 400 items per dataset as UD-IQ4_XS
#   5. 8 slots (1/2/4/8) for the slot recommendation
set -u
HERE="$(cd "$(dirname "$0")/../.." && pwd)"
PROD_REPO="${PROD_REPO:-$HOME/llmapi_server}"
ROUTER_REPO="${ROUTER_REPO:-$HOME/llama-mcp-router}"
Q3="${INKLING_MODELS:-$HOME/inkling/models}/Inkling-2-Mini-UD-Q3_K_XL.gguf"
PORT=8091
URL="http://127.0.0.1:$PORT"
OUT="$HERE/results/slots/q3kxl"
LOGS="$HERE/results/logs"
PY="$HERE/.venv/bin/python"
CFG="$HERE/configs/inkling2mini-q3kxl-medium.json"
REQ='{"temperature":1.0,"top_p":1.0,"top_k":0,"min_p":0.0,"chat_template_kwargs":{"reasoning_effort":"medium"}}'
mkdir -p "$OUT" "$LOGS"
SRV=""
UB=""
log() { echo "[job $(date -u +%H:%M:%S)] $*"; }
gpu_used() { nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits -i 0 | tr -d ' '; }
serve() {  # serve <tag> VAR=value ...
  local tag=$1; shift
  local slog="$LOGS/inkling-q3kxl-$tag-$(date -u +%Y%m%dT%H%M%SZ).log"
  log "starting $tag: $*"
  env LLM_IGNORE_PAUSE=1 INKLING_PORT=$PORT INKLING_HOST=127.0.0.1 INKLING_MODEL="$Q3" INKLING_DRAFT=none "$@" \
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
stress() {  # stress <tag> <tokens in total> <n...>: 0 when every round passed and the server is alive
  local tag=$1 tot=$2; shift 2
  local n
  for n in "$@"; do
    "$PY" "$HERE/scripts/stress_long.py" --url "$URL" --n "$n" --chars $(( tot * 395 / 100 / n )) --max-tokens 256 \
      --out "$OUT/$tag-stress-${n}x.json" || { log "$tag: stress ${n}x failed"; return 1; }
  done
}
stable() {  # stable <tag> <ctx> <tokens> <slots>: load, stress, sweep, stress again, 4 concurrent again
  local tag=$1 ctx=$2 tot=$3 slots=$4
  serve "$tag" INKLING_CTX="$ctx" INKLING_UBATCH="$UB" INKLING_SLOTS="$slots" || return 1
  stress "$tag" "$tot" 1 2 4 || return 1
  "$PY" "$HERE/scripts/slot_sweep.py" --url "$URL" --label "Inkling 2 Mini UD-Q3_K_XL, $slots slots, ctx $ctx, -ub $UB" \
    --concurrency 1,2,4 --request "$REQ" --out "$OUT/$tag-sweep.json" || { log "$tag: sweep failed"; return 1; }
  stress "$tag-again" "$tot" 4 || return 1
  "$PY" "$HERE/scripts/slot_sweep.py" --url "$URL" --label "Inkling 2 Mini UD-Q3_K_XL, $slots slots, ctx $ctx, -ub $UB, after stress" \
    --concurrency 4 --long-chars "" --request "$REQ" --out "$OUT/$tag-sweep-again.json" || { log "$tag: sweep after stress failed"; return 1; }
  kill -0 "$SRV" 2>/dev/null
}

# 1. stability at 65,536 tokens
P_UB=""
for UB in 256 128 64; do
  if stable "np4-c65536-ub$UB" 65536 54000 4; then P_UB=$UB; log "stable: 4 slots, 65536 tokens, -ub $UB"; unserve; break; fi
  unserve
done
[ -n "$P_UB" ] || { log "no stable 65k setting"; exit 1; }
# 2. 131,072 tokens
P_CTX=65536
for UB in 128 64; do
  if stable "np4-c131072-ub$UB" 131072 108000 4; then P_CTX=131072; P_UB=$UB; log "stable: 4 slots, 131072 tokens, -ub $UB"; unserve; break; fi
  unserve
done
echo "{\"slots\": 4, \"ctx\": $P_CTX, \"ub\": $P_UB}" > "$OUT/production-candidate.json"
log "production candidate: 4 slots, ctx $P_CTX, -ub $P_UB"

# 3-4. tool calling and medical QA with the candidate
serve "np4-c$P_CTX-ub$P_UB-eval" INKLING_CTX="$P_CTX" INKLING_UBATCH="$P_UB" INKLING_SLOTS=4 || exit 1
cd "$ROUTER_REPO"
RP="$PROD_REPO/.venv/bin/python"
[ -s benchmarks/results/2026-11-23_inkling-q3kxl_heldout/report.md ] || \
  "$RP" benchmarks/run_bench.py --queries benchmarks/data/queries_heldout.jsonl --clef-url http://127.0.0.1:8000 --concurrency 1 \
    --only "all,clef 2-pass" --llm "$URL" --out benchmarks/results/2026-11-23_inkling-q3kxl_heldout || log "held-out tool benchmark failed"
[ -s benchmarks/results/2026-11-23_inkling-q3kxl_hard/report.md ] || \
  "$RP" benchmarks/run_bench.py --queries benchmarks/data/queries_hard.jsonl --tools benchmarks/data/pubmed_zotero_tools.json \
    --concurrency 1 --only all --llm "$URL" --out benchmarks/results/2026-11-23_inkling-q3kxl_hard || log "hard tool benchmark failed"
cd "$HERE"
kill -0 "$SRV" 2>/dev/null || serve "np4-c$P_CTX-ub$P_UB-eval-restart" INKLING_CTX="$P_CTX" INKLING_UBATCH="$P_UB" INKLING_SLOTS=4 || exit 1
"$PY" - "$CFG" "$P_CTX" "$P_UB" <<'PY'
import json, sys
p, ctx, ub = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
c = json.load(open(p))
c["launch"]["env"].update({"INKLING_CTX": str(ctx), "INKLING_UBATCH": str(ub)})
c["system"]["placement"] = "全部層在 GPU（-ngl all），KV q8_0、%s tokens 由 4 個 slot 共用（--kv-unified），-ub %d，flash-attn" % (format(ctx, ","), ub)
json.dump(c, open(p, "w"), indent=1, ensure_ascii=False)
PY
"$HERE/.venv/bin/medbench" --data "$HERE/data" run --config "$CFG" --sample 400
unserve

# 5. 8 slots with the candidate's context
UB=$P_UB
serve "np8-c$P_CTX-ub$P_UB" INKLING_CTX="$P_CTX" INKLING_UBATCH="$P_UB" INKLING_SLOTS=8 && \
  "$PY" "$HERE/scripts/slot_sweep.py" --url "$URL" --label "Inkling 2 Mini UD-Q3_K_XL, 8 slots, ctx $P_CTX, -ub $P_UB" \
    --concurrency 1,2,4,8 --request "$REQ" --out "$OUT/np8-c$P_CTX-ub$P_UB-sweep.json"
unserve
log "job done"
