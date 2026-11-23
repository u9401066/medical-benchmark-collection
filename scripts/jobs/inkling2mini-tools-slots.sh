#!/usr/bin/env bash
# Follow-up to scripts/jobs/inkling2mini.sh (run inside scripts/gpu_window.sh, production paused):
#   1. PubMed tool-calling benchmarks against Inkling's production candidate, one request at a time: with 41 tools a prompt is
#      ~40k Inkling tokens, so two at once do not fit the 65,536 tokens the 4 slots share
#   2. Bonsai 27B with 8 slots (same 131,072 shared tokens) on a test port: concurrency 1/2/4/6/8 for the slot recommendation
set -u
HERE="$(cd "$(dirname "$0")/../.." && pwd)"
PROD_REPO="${PROD_REPO:-$HOME/llmapi_server}"
ROUTER_REPO="${ROUTER_REPO:-$HOME/llama-mcp-router}"
IQ4="${INKLING_MODELS:-$HOME/inkling/models}/Inkling-2-Mini-UD-IQ4_XS.gguf"
PORT=8091
URL="http://127.0.0.1:$PORT"
OUT="$HERE/results/slots"
LOGS="$HERE/results/logs"
PY="$HERE/.venv/bin/python"
mkdir -p "$OUT" "$LOGS"
SRV=""
log() { echo "[job $(date -u +%H:%M:%S)] $*"; }
gpu_used() { nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits -i 0 | tr -d ' '; }
serve() {  # serve <tag> <start script> VAR=value ...
  local tag=$1 script=$2; shift 2
  local slog="$LOGS/$tag-$(date -u +%Y%m%dT%H%M%SZ).log"
  log "starting $tag: $*"
  env LLM_IGNORE_PAUSE=1 "$@" setsid bash "$script" >> "$slog" 2>&1 < /dev/null &
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

# 1. tool calling, one request at a time; long-context stress; Inkling's raw prompt/completion format (for the Sentinel)
serve inkling-iq4xs-np4-c65536-tools "$PROD_REPO/scripts/start_inkling.sh" INKLING_PORT=$PORT INKLING_HOST=127.0.0.1 \
  INKLING_MODEL="$IQ4" INKLING_SLOTS=4 INKLING_CTX=65536 INKLING_UBATCH=256 INKLING_DRAFT=none || exit 1
for spec in "4 56000" "2 112000" "1 225000"; do
  set -- $spec
  [ -s "$OUT/inkling-iq4xs-np4-stress-$1x$2.json" ] && continue
  log "stress: $1 concurrent requests of $2 characters (~$(( $1 * $2 / 3950 )) tokens in total)"
  "$PY" "$HERE/scripts/stress_long.py" --url "$URL" --n "$1" --chars "$2" --max-tokens 512 \
    --out "$OUT/inkling-iq4xs-np4-stress-$1x$2.json" || { log "stress $1x$2 failed"; unserve
    serve inkling-iq4xs-np4-c65536-restart "$PROD_REPO/scripts/start_inkling.sh" INKLING_PORT=$PORT INKLING_HOST=127.0.0.1 \
      INKLING_MODEL="$IQ4" INKLING_SLOTS=4 INKLING_CTX=65536 INKLING_UBATCH=256 INKLING_DRAFT=none || exit 1; }
done
"$PY" - "$URL" "$LOGS/inkling-raw-format.json" <<'PY'
import json, sys, httpx
url, out = sys.argv[1], sys.argv[2]
msgs = [{"role": "user", "content": "A 60-year-old man has crushing chest pain for 30 minutes. What is the first test? One sentence."}]
res = {}
for eff in ("medium", None):
    body = {"messages": msgs}
    if eff:
        body["chat_template_kwargs"] = {"reasoning_effort": eff}
    rendered = httpx.post(url + "/apply-template", json=body, timeout=60).json()["prompt"]
    comp = httpx.post(url + "/completion", json={"prompt": rendered, "n_predict": 400, "temperature": 0, "return_tokens": True},
                      timeout=600).json()
    res[str(eff)] = {"rendered_tail": rendered[-300:], "content": comp.get("content"), "tokens_head": (comp.get("tokens") or [])[:12],
                     "stop_type": comp.get("stop_type"), "n_tokens": len(comp.get("tokens") or [])}
json.dump(res, open(out, "w"), indent=1, ensure_ascii=False)
print("[raw format]", json.dumps(res["medium"], ensure_ascii=False)[:700])
PY
if [ ! -s "$ROUTER_REPO/benchmarks/results/2026-11-23_inkling_heldout/report.md" ] || \
   [ ! -s "$ROUTER_REPO/benchmarks/results/2026-11-23_inkling_hard/report.md" ]; then
  cd "$ROUTER_REPO"
  RP="$PROD_REPO/.venv/bin/python"
  [ -s benchmarks/results/2026-11-23_inkling_heldout/report.md ] || \
    "$RP" benchmarks/run_bench.py --queries benchmarks/data/queries_heldout.jsonl --clef-url http://127.0.0.1:8000 --concurrency 1 \
      --only "all,clef 2-pass" --llm "$URL" --out benchmarks/results/2026-11-23_inkling_heldout || log "held-out tool benchmark failed"
  [ -s benchmarks/results/2026-11-23_inkling_hard/report.md ] || \
    "$RP" benchmarks/run_bench.py --queries benchmarks/data/queries_hard.jsonl --tools benchmarks/data/pubmed_zotero_tools.json \
      --concurrency 1 --only all --llm "$URL" --out benchmarks/results/2026-11-23_inkling_hard || log "hard tool benchmark failed"
  cd "$HERE"
fi
unserve

# 2. Bonsai with 8 slots
if [ ! -s "$OUT/bonsai-pq2-mtp-np8.json" ]; then
  serve bonsai-pq2-mtp-np8 "$PROD_REPO/scripts/start_bonsai.sh" BONSAI_PORT=$PORT BONSAI_HOST=127.0.0.1 BONSAI_EXTRA_ARGS="-np 8" || exit 1
  "$PY" "$HERE/scripts/slot_sweep.py" --url "$URL" --label "Bonsai 27B PQ2_0, 8 slots, MTP, ctx 131072 shared" \
    --concurrency 1,2,4,6,8 --request '{"chat_template_kwargs":{"reasoning_effort":"medium"}}' --out "$OUT/bonsai-pq2-mtp-np8.json"
  unserve
fi
# 3. UD-Q4_K_XL next to Clef: experts of the first n layers on the CPU, or placed by --fit (verified download only)
Q4KXL="${INKLING_MODELS:-$HOME/inkling/models}/Inkling-2-Mini-UD-Q4_K_XL.gguf"
SUMS="${INKLING_MODELS:-$HOME/inkling/models}/SHA256SUMS.hf"
if [ -s "$Q4KXL" ] && [ ! -s "$OUT/inkling-q4kxl-np4.json" ] && \
   [ "$(sha256sum "$Q4KXL" | cut -d' ' -f1)" = "$(grep UD-Q4_K_XL "$SUMS" | cut -d' ' -f1)" ]; then
  for extra in "--n-cpu-moe 2" "--n-cpu-moe 3" "--n-cpu-moe 4" "--n-cpu-moe 6" "fit"; do
    if [ "$extra" = fit ]; then set -- INKLING_FIT=on INKLING_NGL=auto; label="placed by --fit"
    else set -- INKLING_EXTRA_ARGS="$extra"; label="experts of the first ${extra##* } layers on the CPU"; fi
    serve "inkling-q4kxl-np4-${extra// /}" "$PROD_REPO/scripts/start_inkling.sh" INKLING_PORT=$PORT INKLING_HOST=127.0.0.1 \
      INKLING_MODEL="$Q4KXL" INKLING_SLOTS=4 INKLING_CTX=65536 INKLING_UBATCH=256 INKLING_DRAFT=none "$@" || { unserve; continue; }
    if "$PY" "$HERE/scripts/slot_sweep.py" --url "$URL" --label "Inkling 2 Mini UD-Q4_K_XL, 4 slots, $label, ctx 65536, -ub 256" \
        --concurrency 1,2,4 --long-chars 20000 --request '{"temperature":1.0,"top_p":1.0,"top_k":0,"min_p":0.0,"chat_template_kwargs":{"reasoning_effort":"medium"}}' \
        --out "$OUT/inkling-q4kxl-np4.json"; then unserve; break; fi
    mv "$OUT/inkling-q4kxl-np4.json" "$OUT/inkling-q4kxl-np4-${extra// /}-failed.json" 2>/dev/null
    unserve
  done
fi
log "job done"
