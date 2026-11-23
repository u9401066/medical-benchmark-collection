#!/usr/bin/env bash
# Inkling 2 Mini UD-IQ4_XS in production with the longest context that runs stably next to Clef-Flash
# (run inside scripts/gpu_window.sh: production paused, Clef-Flash stays on the GPU).
# Next to Clef ~18.0 GiB of the card are left; IQ4_XS keeps ~14.2 GiB of weights on the GPU, and the 8 global-attention layer
# visits keep ~17 KB of q8_0 KV per token (131,072 tokens = 2.1 GiB; the native 1,048,576 would be 17 GiB). All on the GPU only
# ~65k tokens fit with headroom, so a longer context keeps the expert weights of some layers in system RAM
# (INKLING_CPU_MOE_LAYERS): the non-looped layers 0-5 and 18-23 (run once per token; 21, 20, 22 are the largest), never the
# looped 6-17 (run 3 times per token).
#   1. probe 131,072 / 196,608 / 262,144 tokens, each with the fewest CPU layers that leave the estimated headroom for
#      concurrent long prompts: load, GPU memory, one-request decode and a 5k-token prefill
#   2. take the longest context whose decode and prefill stay at >= 80% of the 131,072-token probe's; full stability test
#      (long-prompt stress 1x/2x/4x at 82% of the context, load sweep 1/2/4, stress and 4 concurrent requests again); on failure
#      one more CPU layer, then the next shorter context
#   3. write config/inkling.env + config/llm.env (LLM_MODEL=inkling): the window then restores production with this setting
set -u
HERE="$(cd "$(dirname "$0")/../.." && pwd)"
PROD_REPO="${PROD_REPO:-$HOME/llmapi_server}"
MODEL="${INKLING_MODELS:-$HOME/inkling/models}/Inkling-2-Mini-UD-IQ4_XS.gguf"
PORT=8091
URL="http://127.0.0.1:$PORT"
OUT="$HERE/results/slots/iq4xs-maxctx"
LOGS="$HERE/results/logs"
PY="$HERE/.venv/bin/python"
REQ='{"temperature":1.0,"top_p":1.0,"top_k":0,"min_p":0.0,"chat_template_kwargs":{"reasoning_effort":"medium"}}'
ORDER=(21 20 22 0 1 2 3 4 5 18 19 23)   # non-looped layers, largest experts first
UB=64
TOTAL_MIB=24564
mkdir -p "$OUT" "$LOGS"
SRV=""
log() { echo "[job $(date -u +%H:%M:%S)] $*"; }
gpu_used() { nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits -i 0 | tr -d ' '; }
layers() { echo "${ORDER[@]:0:$1}"; }
need_mib() { echo $(( 300 + 1100 * $1 / 131072 )); }   # headroom for concurrent long prompts (measured: +1.1 GiB at 131,072)
serve() {  # serve <tag> <ctx> <cpu layers>
  local tag=$1 ctx=$2 k=$3
  local slog="$LOGS/inkling-iq4xs-$tag-$(date -u +%Y%m%dT%H%M%SZ).log"
  log "starting $tag: ctx $ctx, -ub $UB, experts of layers [$(layers "$k")] on the CPU"
  env LLM_IGNORE_PAUSE=1 INKLING_ENV_FILE=none INKLING_PORT=$PORT INKLING_HOST=127.0.0.1 INKLING_MODEL="$MODEL" INKLING_DRAFT=none INKLING_SLOTS=4 \
    INKLING_CTX="$ctx" INKLING_UBATCH=$UB INKLING_CPU_MOE_LAYERS="$(layers "$k")" \
    setsid bash "$PROD_REPO/scripts/start_inkling.sh" >> "$slog" 2>&1 < /dev/null &
  SRV=$!
  for _ in $(seq 240); do
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
label() { echo "Inkling 2 Mini UD-IQ4_XS, 4 slots, ctx $1, -ub $UB, experts of $2 layers on the CPU"; }
metric() {  # metric <sweep json> decode|prefill
  "$PY" - "$1" "$2" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
if sys.argv[2] == "decode":
    v = [x.get("decode_tps_median") for x in d.get("levels", d.get("results", [])) if x.get("concurrency") == 1]
else:
    v = [x.get("server_prefill_tps") or x.get("prefill_tps") for x in d.get("long", d.get("prefill", []))]
v = [x for x in v if x]
print(int(v[0]) if v else 0)
PY
}

# 1. probes: fewest CPU layers with enough headroom, then one-request decode and a 5k-token prefill
declare -A K DEC PRE
for ctx in 131072 196608 262144; do
  case $ctx in 131072) k0=3;; 196608) k0=6;; 262144) k0=10;; esac
  for k in $(seq "$k0" $(( k0 + 2 ))); do
    [ "$k" -le "${#ORDER[@]}" ] || break
    tag="probe-c$ctx-cpu$k"
    if serve "$tag" "$ctx" "$k"; then
      free=$(( TOTAL_MIB - $(gpu_used) ))
      if [ "$free" -ge "$(need_mib "$ctx")" ]; then
        "$PY" "$HERE/scripts/slot_sweep.py" --url "$URL" --label "$(label "$ctx" "$k")" --concurrency 1 --per-slot 2 \
          --long-chars 20000 --request "$REQ" --out "$OUT/$tag.json" \
          && { DEC[$ctx]=$(metric "$OUT/$tag.json" decode); PRE[$ctx]=$(metric "$OUT/$tag.json" prefill);
               if [ "${DEC[$ctx]}" -gt 0 ] && [ "${PRE[$ctx]}" -gt 0 ]; then K[$ctx]=$k; fi
               log "$tag: free $free MiB, decode ${DEC[$ctx]} tok/s, prefill ${PRE[$ctx]} tok/s"; unserve; break; }
        log "$tag: probe sweep failed"
      else
        log "$tag: only $free MiB free, need $(need_mib "$ctx")"
      fi
    fi
    unserve
  done
done
[ -n "${K[131072]:-}" ] || log "no 131,072-token probe passed"

# 2. the longest context within 80% of the 131,072 probe's speed, then the full stability test
cands=()
for ctx in 262144 196608 131072 98304 65536; do
  if [ "$ctx" -le 131072 ] || { [ -n "${K[$ctx]:-}" ] && [ -n "${K[131072]:-}" ] \
      && [ $(( DEC[$ctx] * 100 )) -ge $(( DEC[131072] * 80 )) ] && [ $(( PRE[$ctx] * 100 )) -ge $(( PRE[131072] * 80 )) ]; }; then
    cands+=("$ctx")
  else
    [ -n "${K[$ctx]:-}" ] && log "c$ctx: decode ${DEC[$ctx]} / prefill ${PRE[$ctx]} tok/s is below 80% of 131,072 (${DEC[131072]:-?} / ${PRE[131072]:-?})"
  fi
done
P_CTX=""; P_K=""
for ctx in "${cands[@]}"; do
  case $ctx in 98304) k0=2;; 65536) k0=0;; *) k0=${K[$ctx]:-3};; esac
  for k in $k0 $(( k0 + 1 )); do
    tag="c$ctx-cpu$k"
    tot=$(( ctx * 82 / 100 ))
    ok=1
    serve "$tag" "$ctx" "$k" || ok=0
    for n in 1 2 4; do
      [ $ok = 1 ] || break
      "$PY" "$HERE/scripts/stress_long.py" --url "$URL" --n "$n" --chars $(( tot * 395 / 100 / n )) --max-tokens 256 \
        --out "$OUT/$tag-stress-${n}x.json" || { log "$tag: stress ${n}x failed"; ok=0; }
    done
    [ $ok = 1 ] && { "$PY" "$HERE/scripts/slot_sweep.py" --url "$URL" --label "$(label "$ctx" "$k")" --concurrency 1,2,4 \
      --request "$REQ" --out "$OUT/$tag-sweep.json" || { log "$tag: sweep failed"; ok=0; }; }
    [ $ok = 1 ] && { "$PY" "$HERE/scripts/stress_long.py" --url "$URL" --n 4 --chars $(( tot * 395 / 100 / 4 )) --max-tokens 256 \
      --out "$OUT/$tag-again-stress-4x.json" || { log "$tag: stress again failed"; ok=0; }; }
    [ $ok = 1 ] && { "$PY" "$HERE/scripts/slot_sweep.py" --url "$URL" --label "$(label "$ctx" "$k"), after stress" --concurrency 4 \
      --long-chars "" --request "$REQ" --out "$OUT/$tag-sweep-again.json" || { log "$tag: sweep after stress failed"; ok=0; }; }
    [ $ok = 1 ] && kill -0 "$SRV" 2>/dev/null || ok=0
    unserve
    if [ $ok = 1 ]; then P_CTX=$ctx; P_K=$k; log "stable: ctx $ctx with experts of $k layers on the CPU"; break 2; fi
  done
done
[ -n "$P_CTX" ] || { log "no stable IQ4_XS setting; production stays as it was"; exit 1; }

# 3. production setting (start_bonsai.sh -> start_inkling.sh reads these when the window restores production)
cat > "$PROD_REPO/config/inkling.env" <<EOF
# Written by medqa-bench scripts/jobs/inkling2mini-iq4xs-maxctx.sh on $(date -u +%Y-%m-%dT%H:%MZ): the longest context that
# passed concurrent long-prompt stress next to Clef-Flash (results/slots/iq4xs-maxctx/c$P_CTX-cpu$P_K-*).
INKLING_MODEL=\$HOME/inkling/models/Inkling-2-Mini-UD-IQ4_XS.gguf
INKLING_CTX=$P_CTX
INKLING_UBATCH=$UB
INKLING_SLOTS=4
INKLING_CPU_MOE_LAYERS="$(layers "$P_K")"
EOF
echo "LLM_MODEL=inkling" > "$PROD_REPO/config/llm.env"
echo "{\"model\": \"UD-IQ4_XS\", \"slots\": 4, \"ctx\": $P_CTX, \"ub\": $UB, \"cpu_moe_layers\": \"$(layers "$P_K")\"}" > "$OUT/production.json"
log "production: IQ4_XS, ctx $P_CTX, -ub $UB, experts of layers [$(layers "$P_K")] on the CPU"
