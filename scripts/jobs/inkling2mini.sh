#!/usr/bin/env bash
# Evaluation job for Inkling 2 Mini on llm01, run inside scripts/gpu_window.sh (production paused, Clef-Flash stays on the GPU).
# Round 1 (results/slots/fit-round1.jsonl) showed that next to Clef the relative-bias attention's compute buffer, not the KV
# cache, limits the context: 131k does not load, 8 slots / 65k / -ub 512 dies at 4 concurrent requests, DSpark only fits at 32k.
#   1. production candidate UD-IQ4_XS, 4 slots, -ub 256, no drafter: the largest context that survives a load sweep
#      (1/2/4 concurrent + 5k/20k-token prompts); then 8 slots with the same context (1/2/4/8) for the slot recommendation
#   2. DSpark with 4 slots at 32k (the only size it fits): does it speed up a request?
#   3. PubMed tool-calling benchmarks of llama-mcp-router (one probe request first, so a server error is logged)
#   4. medical QA: 400 evenly spaced items per dataset first (paired with Bonsai's answers), then the rest until DEADLINE_UTC
#   5. UD-Q4_K_XL (does not fit on the GPU next to Clef): placement probes and a short sweep
# Finished steps are skipped when the job is run again; medbench resumes by itself.
set -u
HERE="$(cd "$(dirname "$0")/../.." && pwd)"
PROD_REPO="${PROD_REPO:-$HOME/llmapi_server}"
ROUTER_REPO="${ROUTER_REPO:-$HOME/llama-mcp-router}"
M="${INKLING_MODELS:-$HOME/inkling/models}"
BIN_DIR="${INKLING_BIN_DIR:-$HOME/inkling/bin/b12631}"
IQ4="$M/Inkling-2-Mini-UD-IQ4_XS.gguf"
Q4KXL="$M/Inkling-2-Mini-UD-Q4_K_XL.gguf"
DSPARK="$M/dspark-Inkling-2-Mini-Q8_0.gguf"
DEADLINE_UTC="${DEADLINE_UTC:-}"          # e.g. "2026-11-23 23:00"; empty = no limit
RESERVE_S="${RESERVE_S:-1200}"            # stop the QA run this long before the deadline (Q4_K_XL step + restore)
UB=256
PORT=8091
URL="http://127.0.0.1:$PORT"
OUT="$HERE/results/slots"
LOGS="$HERE/results/logs"
PY="$HERE/.venv/bin/python"
CFG="$HERE/configs/inkling2mini-iq4xs-medium.json"
REQ='{"temperature":1.0,"top_p":1.0,"top_k":0,"min_p":0.0,"chat_template_kwargs":{"reasoning_effort":"medium"}}'
NV="$PROD_REPO/.venv/lib/python3.12/site-packages/nvidia"
mkdir -p "$OUT" "$LOGS"
SRV=""
SRV_LOG=""
log() { echo "[job $(date -u +%H:%M:%S)] $*"; }
gpu_used() { nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits -i 0 | tr -d ' '; }

estimate() {  # estimate <model> <ctx> <slots> -> "model context compute" MiB from llama-fit-params (no GPU allocation)
  LD_LIBRARY_PATH="$BIN_DIR:$NV/cuda_runtime/lib:$NV/cublas/lib:$NV/nvjitlink/lib" timeout 120 "$BIN_DIR/llama-fit-params" \
    -m "$1" -ngl all -fa on -c "$2" -np "$3" -ctk q8_0 -ctv q8_0 -b 2048 -ub "$UB" --fit-print on 2>/dev/null | awk '/^CUDA0/{print $2, $3, $4}'
}
serve() {  # serve <tag> VAR=value ... : start start_inkling.sh on $PORT; 0 when it answers a request
  local tag=$1; shift
  SRV_LOG="$LOGS/inkling-$tag-$(date -u +%Y%m%dT%H%M%SZ).log"
  log "starting $tag: $*"
  env INKLING_PORT=$PORT INKLING_HOST=127.0.0.1 INKLING_UBATCH=$UB LLM_IGNORE_PAUSE=1 "$@" \
    setsid bash "$PROD_REPO/scripts/start_inkling.sh" >> "$SRV_LOG" 2>&1 < /dev/null &
  SRV=$!
  for _ in $(seq 180); do
    if curl -sf -m 3 "$URL/health" >/dev/null; then
      if curl -sf -m 600 "$URL/v1/chat/completions" -H 'Content-Type: application/json' \
          -d '{"messages":[{"role":"user","content":"Say OK."}],"max_tokens":64}' >/dev/null; then
        log "$tag ready (GPU memory used $(gpu_used) MiB)"; return 0
      fi
      log "$tag: no answer to the first request"; return 1
    fi
    kill -0 "$SRV" 2>/dev/null || { log "$tag: server exited: $(grep -i -m2 -E 'out of memory|failed|error' "$SRV_LOG" | cut -c1-160)"; return 1; }
    sleep 2
  done
  log "$tag: not ready after 6 min"; return 1
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
record() {  # record <tag> <ctx> <ok|load-failed|sweep-failed> <model> <slots>
  printf '{"tag":"%s","ctx":%s,"ub":%s,"slots":%s,"result":"%s","gpu_used_mib":%s,"estimate_model_ctx_compute_mib":"%s","log":"%s"}\n' \
    "$1" "$2" "$UB" "$5" "$3" "$(gpu_used)" "$(estimate "$4" "$2" "$5")" "$(basename "$SRV_LOG")" >> "$OUT/fit.jsonl"
}
sweep() {  # sweep <out name> <label> <concurrency list> [slot_sweep args...]; 0 when every level ran
  local name=$1 label=$2 conc=$3; shift 3
  "$PY" "$HERE/scripts/slot_sweep.py" --url "$URL" --label "$label" --concurrency "$conc" --request "$REQ" \
    --out "$OUT/$name.json" "$@"
}
try_sweep() {  # try_sweep <name> <label> <slots> <conc> "<ctx list>" <model> [VAR=value ...]: largest ctx that loads and survives
  local name=$1 label=$2 slots=$3 conc=$4 ctxs=$5 model=$6; shift 6
  CTX_OK=""
  for c in $ctxs; do
    if ! serve "$name-c$c" INKLING_MODEL="$model" INKLING_SLOTS="$slots" INKLING_CTX="$c" "$@"; then
      record "$name" "$c" load-failed "$model" "$slots"; unserve; continue
    fi
    if sweep "$name" "$label, ctx $c, -ub $UB" "$conc"; then
      record "$name" "$c" ok "$model" "$slots"; CTX_OK=$c; unserve; return 0
    fi
    record "$name" "$c" sweep-failed "$model" "$slots"
    mv "$OUT/$name.json" "$OUT/$name-c$c-failed.json" 2>/dev/null
    unserve
  done
  return 1
}

# 1. production candidate and the slot question
if [ ! -s "$OUT/inkling-iq4xs-np4.json" ]; then
  try_sweep inkling-iq4xs-np4 "Inkling 2 Mini UD-IQ4_XS, 4 slots, no drafter" 4 1,2,4 "65536 49152 32768" "$IQ4" INKLING_DRAFT=none || exit 1
fi
P_CTX=$("$PY" -c 'import json,sys; print(json.load(open(sys.argv[1]))["label"].split("ctx ")[1].split(",")[0])' "$OUT/inkling-iq4xs-np4.json")
log "production candidate: 4 slots, ctx $P_CTX, -ub $UB, no drafter"
[ -s "$OUT/inkling-iq4xs-np8.json" ] || try_sweep inkling-iq4xs-np8 "Inkling 2 Mini UD-IQ4_XS, 8 slots, no drafter" 8 1,2,4,8 "$P_CTX" "$IQ4" INKLING_DRAFT=none
[ -s "$OUT/inkling-iq4xs-np2.json" ] || try_sweep inkling-iq4xs-np2 "Inkling 2 Mini UD-IQ4_XS, 2 slots, no drafter" 2 1,2 "$P_CTX" "$IQ4" INKLING_DRAFT=none
# 2. DSpark at the only size it fits
[ -s "$OUT/inkling-iq4xs-np4-dspark.json" ] || try_sweep inkling-iq4xs-np4-dspark "Inkling 2 Mini UD-IQ4_XS, 4 slots, DSpark" 4 1,2,4 "32768" "$IQ4" INKLING_DRAFT="$DSPARK"

# 3. tool calling with the production candidate
serve "iq4xs-np4-c$P_CTX-tools" INKLING_MODEL="$IQ4" INKLING_SLOTS=4 INKLING_CTX="$P_CTX" INKLING_DRAFT=none || exit 1
"$PY" - "$URL" "$ROUTER_REPO" <<'PY'
import json, sys, httpx
url, router = sys.argv[1], sys.argv[2]
tools = json.load(open(router + "/benchmarks/data/pubmed_tools.json"))
q = json.loads(open(router + "/benchmarks/data/queries_heldout.jsonl").readline())
r = httpx.post(url + "/v1/chat/completions", timeout=600, json={"messages": [{"role": "user", "content": q["query"]}], "tools": tools,
               "temperature": 0, "max_tokens": 2048, "chat_template_kwargs": {"reasoning_effort": "medium"}})
d = r.json()
if "choices" in d:
    m = d["choices"][0]["message"]
    print("[tool probe] HTTP %d, prompt %s tokens, tool calls: %s" % (r.status_code, d["usage"]["prompt_tokens"],
          [c["function"]["name"] + " " + c["function"]["arguments"][:120] for c in m.get("tool_calls") or []]))
else:
    print("[tool probe] HTTP %d: %s" % (r.status_code, json.dumps(d)[:600]))
PY
cd "$ROUTER_REPO"
RP="$PROD_REPO/.venv/bin/python"
[ -s benchmarks/results/2026-11-23_inkling_heldout/report.md ] || \
  "$RP" benchmarks/run_bench.py --queries benchmarks/data/queries_heldout.jsonl --clef-url http://127.0.0.1:8000 \
    --only "all,clef 2-pass" --llm "$URL" --out benchmarks/results/2026-11-23_inkling_heldout || log "held-out tool benchmark failed"
[ -s benchmarks/results/2026-11-23_inkling_hard/report.md ] || \
  "$RP" benchmarks/run_bench.py --queries benchmarks/data/queries_hard.jsonl --tools benchmarks/data/pubmed_zotero_tools.json \
    --only all --llm "$URL" --out benchmarks/results/2026-11-23_inkling_hard || log "hard tool benchmark failed"
cd "$HERE"

# 4. medical QA with the production candidate (the server from step 3 keeps running)
"$PY" - "$CFG" "$P_CTX" "$UB" <<'PY'
import json, sys
p, ctx, ub = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
c = json.load(open(p))
c["concurrency"] = 4
c["launch"]["env"].update({"INKLING_SLOTS": "4", "INKLING_CTX": str(ctx), "INKLING_UBATCH": str(ub), "INKLING_DRAFT": "none"})
c["system"]["engine"] = "Unsloth llama.cpp prebuilt b12631-mix-acc0843（上游 b12631 + looped-layer / DSpark 修補，CUDA 12.8），不用推測解碼"
c["system"]["weights"] = "Unsloth UD-IQ4_XS（Dynamic 3.0 imatrix），GGUF 14.65 GiB"
c["system"]["placement"] = "全部層在 GPU（-ngl all），KV q8_0、%s tokens 由 4 個 slot 共用（--kv-unified），-ub %d，flash-attn" % (format(ctx, ","), ub)
json.dump(c, open(p, "w"), indent=1, ensure_ascii=False)
PY
left() { [ -n "$DEADLINE_UTC" ] || { echo 999999; return; }; echo $(( $(date -u -d "$DEADLINE_UTC" +%s) - $(date -u +%s) - RESERVE_S )); }
QA="$HERE/.venv/bin/medbench --data $HERE/data run --config $CFG"
L=$(left); [ "$L" -gt 600 ] && timeout --signal=TERM --kill-after=120 "$L" $QA --sample 400
L=$(left); [ "$L" -gt 600 ] && timeout --signal=TERM --kill-after=120 "$L" $QA
unserve

# 5. Q4_K_XL placement probes (verified download only)
if [ -s "$Q4KXL" ] && [ ! -s "$OUT/inkling-q4kxl-np4.json" ] && \
   [ "$(sha256sum "$Q4KXL" | cut -d' ' -f1)" = "$(grep UD-Q4_K_XL "$M/SHA256SUMS.hf" | cut -d' ' -f1)" ]; then
  for n in 2 3 4 6; do
    try_sweep inkling-q4kxl-np4 "Inkling 2 Mini UD-Q4_K_XL, 4 slots, experts of the first $n layers on the CPU" 4 1,2,4 "$P_CTX" \
      "$Q4KXL" INKLING_DRAFT=none INKLING_EXTRA_ARGS="--n-cpu-moe $n" && break
  done
  [ -s "$OUT/inkling-q4kxl-np4.json" ] || try_sweep inkling-q4kxl-np4 "Inkling 2 Mini UD-Q4_K_XL, 4 slots, placed by --fit" 4 1,2,4 \
    "$P_CTX" "$Q4KXL" INKLING_DRAFT=none INKLING_FIT=on INKLING_NGL=auto
fi
log "job done"
