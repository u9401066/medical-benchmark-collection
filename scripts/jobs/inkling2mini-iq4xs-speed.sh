#!/usr/bin/env bash
# Faster Inkling 2 Mini UD-IQ4_XS at 131,072 tokens next to Clef-Flash (run inside scripts/gpu_window.sh after
# inkling2mini-iq4xs-maxctx.sh). The production setting keeps the experts of layers 21, 20, 22 in system RAM: decode drops from
# 81 to 56 tok/s, and prefill from ~2,400 to ~390 tok/s because every 64-token batch uploads those experts over PCIe.
#   1. variants, each: load, free VRAM, then one request and 4 concurrent (decode, total) and a 5k-token prefill:
#        base (production), --no-op-offload (CPU computes those experts in prefill instead of uploading them),
#        --moe-cache-mib 256/512 (GPU cache of the CPU experts), -t 8, -ub 128 with one more CPU layer,
#        and for reference only (changes quality, never deployed here) q4_0 KV with fewer CPU layers
#   2. the flags that help (>= 5% on decode or prefill, no metric > 5% worse) together
#   3. the best of these vs base by decode x prefill; if >= 10% better, the full stability test (long-prompt stress 1x/2x/4x,
#      sweep, stress again) and, if it passes, config/inkling.env is updated (the window restores production with it)
set -u
HERE="$(cd "$(dirname "$0")/../.." && pwd)"
PROD_REPO="${PROD_REPO:-$HOME/llmapi_server}"
MODEL="${INKLING_MODELS:-$HOME/inkling/models}/Inkling-2-Mini-UD-IQ4_XS.gguf"
PORT=8091
URL="http://127.0.0.1:$PORT"
OUT="$HERE/results/slots/iq4xs-speed"
LOGS="$HERE/results/logs"
PY="$HERE/.venv/bin/python"
REQ='{"temperature":1.0,"top_p":1.0,"top_k":0,"min_p":0.0,"chat_template_kwargs":{"reasoning_effort":"medium"}}'
CTX=131072
TOTAL_MIB=24564
NEED_MIB=1400
mkdir -p "$OUT" "$LOGS"
SRV=""
log() { echo "[job $(date -u +%H:%M:%S)] $*"; }
gpu_used() { nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits -i 0 | tr -d ' '; }
serve() {  # serve <tag> VAR=value ...  (INKLING_* overrides on top of the production base)
  local tag=$1; shift
  local slog="$LOGS/inkling-iq4xs-speed-$tag-$(date -u +%Y%m%dT%H%M%SZ).log"
  log "starting $tag: $*"
  env LLM_IGNORE_PAUSE=1 INKLING_ENV_FILE=none INKLING_PORT=$PORT INKLING_HOST=127.0.0.1 INKLING_MODEL="$MODEL" INKLING_DRAFT=none INKLING_SLOTS=4 \
    INKLING_CTX=$CTX INKLING_UBATCH=64 INKLING_CPU_MOE_LAYERS="21 20 22" "$@" \
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
metric() {  # metric <sweep json> c1|c4|prefill
  "$PY" - "$1" "$2" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
lv = {x["concurrency"]: x for x in d.get("levels", []) if "concurrency" in x}
if sys.argv[2] == "c1":
    v = (lv.get(1) or {}).get("decode_tps_median")
elif sys.argv[2] == "c4":
    v = (lv.get(4) or {}).get("aggregate_tok_s")
else:
    v = next((x.get("server_prefill_tps") for x in d.get("prefill", []) if x.get("server_prefill_tps")), None)
print(int(v) if v else 0)
PY
}
declare -A C1 C4 PF
measure() {  # measure <tag> VAR=value ...: 0 and C1/C4/PF[tag] when the variant loads with enough headroom and measures
  local tag=$1; shift
  serve "$tag" "$@" || { unserve; return 1; }
  local free=$(( TOTAL_MIB - $(gpu_used) ))
  if [ "$free" -lt "$NEED_MIB" ]; then log "$tag: only $free MiB free, need $NEED_MIB"; unserve; return 1; fi
  "$PY" "$HERE/scripts/slot_sweep.py" --url "$URL" --label "Inkling 2 Mini UD-IQ4_XS, ctx $CTX, $tag" --concurrency 1,4 --per-slot 2 \
    --long-chars 20000 --request "$REQ" --out "$OUT/$tag.json" || { log "$tag: sweep failed"; unserve; return 1; }
  unserve
  C1[$tag]=$(metric "$OUT/$tag.json" c1); C4[$tag]=$(metric "$OUT/$tag.json" c4); PF[$tag]=$(metric "$OUT/$tag.json" prefill)
  log "$tag: free $free MiB, decode ${C1[$tag]} tok/s, 4 concurrent ${C4[$tag]} tok/s total, prefill ${PF[$tag]} tok/s"
  [ "${C1[$tag]}" -gt 0 ] && [ "${PF[$tag]}" -gt 0 ]
}
better() {  # better <tag>: helps (>= 5% on c1 or prefill) and nothing > 5% worse than base
  local t=$1 b=base
  [ -n "${C1[$t]:-}" ] || return 1
  [ $(( C1[$t] * 100 )) -ge $(( C1[$b] * 95 )) ] && [ $(( PF[$t] * 100 )) -ge $(( PF[$b] * 95 )) ] && [ $(( C4[$t] * 100 )) -ge $(( C4[$b] * 95 )) ] \
    && { [ $(( C1[$t] * 100 )) -ge $(( C1[$b] * 105 )) ] || [ $(( PF[$t] * 100 )) -ge $(( PF[$b] * 105 )) ]; }
}

# 1. variants
measure base || { log "production setting does not measure; stopping"; exit 1; }
declare -A ARGS
ARGS[noopoff]="INKLING_EXTRA_ARGS=--no-op-offload"
ARGS[moecache256]="INKLING_EXTRA_ARGS=--moe-cache-mib 256"
ARGS[moecache512]="INKLING_EXTRA_ARGS=--moe-cache-mib 512"
ARGS[t8]="INKLING_EXTRA_ARGS=-t 8 -tb 12"
ARGS[ub128-cpu4]="INKLING_UBATCH=128 INKLING_CPU_MOE_LAYERS=21 20 22 0"
for v in noopoff moecache256 moecache512 t8; do measure "$v" "${ARGS[$v]}"; done
measure ub128-cpu4 INKLING_UBATCH=128 "INKLING_CPU_MOE_LAYERS=21 20 22 0"
measure ref-kvq4-cpu1 INKLING_KV=q4_0 "INKLING_CPU_MOE_LAYERS=21"      # reference only: q4_0 KV changes quality
measure ref-kvq4-cpu2 INKLING_KV=q4_0 "INKLING_CPU_MOE_LAYERS=21 20"

# 2. the helpful flags together (only flags in INKLING_EXTRA_ARGS combine; -ub 128 replaces the layer set)
extra=""; groups=0
for v in noopoff t8; do better "$v" && { extra="$extra ${ARGS[$v]#INKLING_EXTRA_ARGS=}"; groups=$(( groups + 1 )); }; done
if better moecache512; then extra="$extra --moe-cache-mib 512"; groups=$(( groups + 1 ))
elif better moecache256; then extra="$extra --moe-cache-mib 256"; groups=$(( groups + 1 )); fi
extra="${extra# }"
best=base
score() { echo $(( C1[$1] * PF[$1] )); }
for v in noopoff moecache256 moecache512 t8 ub128-cpu4; do
  better "$v" && [ "$(score "$v")" -gt "$(score "$best")" ] && best=$v
done
if [ "$groups" -ge 2 ]; then
  measure combo "INKLING_EXTRA_ARGS=$extra" && better combo && [ "$(score combo)" -gt "$(score "$best")" ] && best=combo
fi
log "best: $best (decode ${C1[$best]}, 4 concurrent ${C4[$best]}, prefill ${PF[$best]} tok/s; base ${C1[base]} / ${C4[base]} / ${PF[base]})"

# 3. deploy only a clear gain that survives the full stability test
[ "$best" != base ] || { log "no variant is clearly faster; production setting unchanged"; exit 0; }
[ $(( $(score "$best") * 100 )) -ge $(( $(score base) * 110 )) ] || { log "$best is < 10% better; production setting unchanged"; exit 0; }
case $best in
  combo) set -- "INKLING_EXTRA_ARGS=$extra";;
  ub128-cpu4) set -- INKLING_UBATCH=128 "INKLING_CPU_MOE_LAYERS=21 20 22 0";;
  *) set -- "${ARGS[$best]}";;
esac
serve "stable-$best" "$@" || exit 1
tot=$(( CTX * 82 / 100 ))
ok=1
for n in 1 2 4 4; do
  "$PY" "$HERE/scripts/stress_long.py" --url "$URL" --n "$n" --chars $(( tot * 395 / 100 / n )) --max-tokens 256 \
    --out "$OUT/stable-$best-stress-${n}x.json" || { log "stable-$best: stress ${n}x failed"; ok=0; break; }
done
[ $ok = 1 ] && { "$PY" "$HERE/scripts/slot_sweep.py" --url "$URL" --label "Inkling 2 Mini UD-IQ4_XS, ctx $CTX, $best" --concurrency 1,2,4 \
  --request "$REQ" --out "$OUT/stable-$best-sweep.json" || ok=0; }
[ $ok = 1 ] && kill -0 "$SRV" 2>/dev/null || ok=0
unserve
[ $ok = 1 ] || { log "$best failed the stability test; production setting unchanged"; exit 1; }
env_file="$PROD_REPO/config/inkling.env"
{
  echo "# Updated by medqa-bench scripts/jobs/inkling2mini-iq4xs-speed.sh on $(date -u +%Y-%m-%dT%H:%MZ): $best"
  echo "# (results/slots/iq4xs-speed/stable-$best-*): decode ${C1[$best]} vs ${C1[base]}, prefill ${PF[$best]} vs ${PF[base]} tok/s"
  echo "INKLING_MODEL=\$HOME/inkling/models/Inkling-2-Mini-UD-IQ4_XS.gguf"
  echo "INKLING_CTX=$CTX"
  echo "INKLING_SLOTS=4"
  case $best in
    ub128-cpu4) echo "INKLING_UBATCH=128"; echo 'INKLING_CPU_MOE_LAYERS="21 20 22 0"';;
    *) echo "INKLING_UBATCH=64"; echo 'INKLING_CPU_MOE_LAYERS="21 20 22"'; echo "INKLING_EXTRA_ARGS=\"${1#INKLING_EXTRA_ARGS=}\"";;
  esac
} > "$env_file"
log "production: $best written to $env_file"
