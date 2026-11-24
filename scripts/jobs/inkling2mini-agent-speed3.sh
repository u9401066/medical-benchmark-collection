#!/usr/bin/env bash
# Third window on the recorded xhigh agent run (b12651, IQ4_XS all on the GPU):
#   A. DSpark, Inkling 2 Mini's own MTP drafter (converted from its mtp.safetensors), on 4 slots sharing 131k.
#      inkling2mini-agent-speed.sh could not test it: at -ub 1024 the drafter's KV cache did not fit. Here -ub 512
#      (256 if it does not fit), 3/2/5 draft tokens per step (Unsloth's default is 3, the trained block is 8).
#   B. if it is at least 5% faster: the drafter on window 2's fastest setting, 2 slots with their own 131k (-ub 256)
#   C. 3 slots with their own 131k (-ub 128): how many agents fit without slowing each other
#
#   cd ~/medqa-bench && env PAUSE_CLEF=1 "TEST_PATTERN=--port 809[14]" bash scripts/gpu_window.sh scripts/jobs/inkling2mini-agent-speed3.sh
set -u -o pipefail
HERE="$(cd "$(dirname "$0")/../.." && pwd)"
PROD_REPO="${PROD_REPO:-$HOME/llmapi_server}"
MODELS="${INKLING_MODELS:-$HOME/inkling/models}"
IQ4="$MODELS/Inkling-2-Mini-UD-IQ4_XS.gguf"
DRAFT="$MODELS/dspark-Inkling-2-Mini-Q8_0.gguf"
B651="$HOME/inkling/bin/b12651/llama-server"
PORT=8091
URL="http://127.0.0.1:$PORT"
OUT="$HERE/results/speed/agent/window3"
LOGS="$HERE/results/logs"
PY="$HERE/.venv/bin/python"
TRACE="$HERE/results/speed/agent/trace-xhigh.jsonl"
SCREEN="${SCREEN_REQUESTS:-1-8}"
mkdir -p "$OUT" "$LOGS"
SRV=""
MON=""
log() { echo "[job $(date -u +%H:%M:%S)] $*"; }
gpu_used() { nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits -i 0 | tr -d ' '; }
monitor() {
  local f=$1; echo 0 > "$f"
  ( while :; do u=$(gpu_used); [ "$u" -gt "$(cat "$f")" ] && echo "$u" > "$f"; sleep 0.5; done ) &
  MON=$!
}
serve() {  # serve <tag> VAR=value ...
  local tag=$1; shift
  local slog="$LOGS/inkling-agent-speed3-$tag-$(date -u +%Y%m%dT%H%M%SZ).log"
  log "starting $tag: $*"
  env LLM_IGNORE_PAUSE=1 INKLING_ENV_FILE=none INKLING_PORT=$PORT INKLING_HOST=127.0.0.1 INKLING_MODEL="$IQ4" INKLING_DRAFT=none \
    INKLING_SLOTS=4 INKLING_CTX=131072 INKLING_UBATCH=512 INKLING_CPU_MOE_LAYERS= INKLING_BIN="$B651" "$@" \
    setsid bash "$PROD_REPO/scripts/start_inkling.sh" >> "$slog" 2>&1 < /dev/null &
  SRV=$!
  for _ in $(seq 240); do
    if curl -sf -m 3 "$URL/health" >/dev/null && curl -sf -m 600 "$URL/v1/chat/completions" -H 'Content-Type: application/json' \
        -d '{"messages":[{"role":"user","content":"Say OK."}],"max_tokens":64}' >/dev/null; then
      log "$tag ready (GPU memory used $(gpu_used) MiB)"; monitor "$OUT/$tag.peak"; return 0
    fi
    kill -0 "$SRV" 2>/dev/null || { log "$tag: server exited: $(grep -i -m2 -E 'out of memory|failed|error' "$slog" | cut -c1-160)"; SRV=""; return 1; }
    sleep 2
  done
  return 1
}
unserve() {
  [ -n "$MON" ] && { kill "$MON" 2>/dev/null; wait "$MON" 2>/dev/null; MON=""; }
  [ -n "$SRV" ] || return 0
  kill -TERM -- "-$SRV" 2>/dev/null
  for _ in $(seq 30); do kill -0 "$SRV" 2>/dev/null || break; sleep 1; done
  kill -9 -- "-$SRV" 2>/dev/null
  SRV=""
  sleep 3
}
trap unserve EXIT
replay() {  # replay <tag> <requests> [extra args]
  local tag=$1 req=$2; shift 2
  "$PY" "$HERE/scripts/agent_replay.py" --trace "$TRACE" --url "$URL" --requests "$req" --effort max --quiet \
    --label "$tag" --out "$OUT/$tag.json" "$@" | tail -3
}
alive() { [ -n "$SRV" ] && kill -0 "$SRV" 2>/dev/null; }
stress() {  # stress <tag> <n...>: n concurrent prompts filling 95% of the 131k context together (STRESS_DIV=1: of each slot)
  local tag=$1; shift
  for n in "$@"; do
    "$PY" "$HERE/scripts/stress_long.py" --url "$URL" --n "$n" --chars $(( 131072 * 95 / 100 * 395 / 100 / ${STRESS_DIV:-$n} )) --max-tokens 256 \
      --out "$OUT/$tag-stress-${n}x.json" > /dev/null || { log "$tag: stress ${n}x failed"; return 1; }
    alive || { log "$tag: server died in stress ${n}x"; return 1; }
    log "$tag: stress ${n}x ok (GPU peak so far $(cat "$OUT/$tag.peak") MiB)"
  done
}
modeled() { "$PY" -c "import json,sys; print(json.load(open(sys.argv[1]))['runs'][0]['modeled_task_s'])" "$1" 2>/dev/null || echo 0; }

# A. DSpark on the 4-slot shared-KV setting (-ub 512; -ub 256 if the drafter does not fit)
best=""; best_s=0; best_ub=""; best_n=""
for ub in 512 256; do
  if [ "$ub" = 256 ]; then  # reference without the drafter at -ub 256 (window 1: g651-ub256)
    serve "u4-ub$ub" INKLING_UBATCH=$ub && replay "u4-ub$ub" "$SCREEN"; unserve
  fi
  for n in 3 2 5; do
    tag="u4-ub$ub-dspark$n"
    if serve "$tag" INKLING_UBATCH=$ub INKLING_DRAFT="$DRAFT" INKLING_DRAFT_N=$n; then
      replay "$tag" "$SCREEN"
      log "$tag: GPU peak $(cat "$OUT/$tag.peak") MiB"
      s=$(modeled "$OUT/$tag.json")
      if [ "$s" != 0 ] && { [ -z "$best" ] || "$PY" -c "import sys; sys.exit(0 if float(sys.argv[1]) < float(sys.argv[2]) else 1)" "$s" "$best_s"; }; then
        best=$tag; best_s=$s; best_ub=$ub; best_n=$n
      fi
    else
      unserve; [ "$n" = 3 ] && break  # the drafter does not fit at this -ub
      continue
    fi
    unserve
  done
  [ -n "$best" ] && break  # it fits at -ub 512: -ub 256 is slower anyway
done
ref_s=89.6  # without the drafter: window 1 g651-ub512 (window 2 u4-ub512-b512: 90.1)
[ "$best_ub" = 256 ] && ref_s=$(modeled "$OUT/u4-ub256.json")
log "best drafter setting: ${best:-none} (${best_s} s modeled vs ${ref_s} s without)"

# B. the drafter on the 2-slot setting (own 131k each, -ub 256: window 2's fastest), if it helped in A
if [ -n "$best" ] && "$PY" -c "import sys; sys.exit(0 if float(sys.argv[1]) <= 0.95 * float(sys.argv[2]) else 1)" "$best_s" "$ref_s"; then
  tag="n2-ub256-dspark$best_n"
  if serve "$tag" INKLING_SLOTS=2 INKLING_CTX=262144 INKLING_KV_UNIFIED=0 INKLING_UBATCH=256 INKLING_DRAFT="$DRAFT" INKLING_DRAFT_N=$best_n; then
    replay "$tag" "$SCREEN"
    replay "$tag-parallel2" "$SCREEN" --parallel 2
    STRESS_DIV=1 stress "$tag" 2
    alive || log "$tag: server died"
    log "$tag: GPU peak $(cat "$OUT/$tag.peak") MiB"
  fi
  unserve
fi

# C. three slots with their own 131k each (-ub 128, the 3rd 131k KV takes the room of the larger compute buffer)
tag="n3-ub128"
if serve "$tag" INKLING_SLOTS=3 INKLING_CTX=393216 INKLING_KV_UNIFIED=0 INKLING_UBATCH=128; then
  replay "$tag" "$SCREEN"
  replay "$tag-parallel2" "$SCREEN" --parallel 2
  STRESS_DIV=1 stress "$tag" 3
  alive || log "$tag: server died"
  log "$tag: GPU peak $(cat "$OUT/$tag.peak") MiB"
fi
unserve

"$PY" - "$OUT" <<'PY'
import glob, json, os, sys
out = sys.argv[1]
rows = ["| setting | requests | prefill tok/s | decode tok/s | draft acceptance | modeled task s | wall s | GPU peak MiB |", "|---|---|---|---|---|---|---|---|"]
for f in sorted(glob.glob(os.path.join(out, "*.json"))):
    try:
        d = json.load(open(f))
    except Exception:
        continue
    if "runs" not in d:
        continue
    tag = os.path.basename(f)[:-5]
    pf = os.path.join(out, tag.replace("-parallel2", "") + ".peak")
    peak = open(pf).read().strip() if os.path.exists(pf) else "-"
    for r in d["runs"]:
        rows.append("| %s | %s (%d/%d ok) | %s | %s | %s | %s | %s | %s |" % (tag, d["requests"], r["ok"], r["requests"], r["prefill_tps"], r["decode_tps"],
                    r.get("draft_acceptance") if r.get("draft_acceptance") is not None else "-", r.get("modeled_task_s"), r["wall_s"], peak))
    if d.get("aggregate"):
        rows.append("| %s (both) | | %s | %s | | | %s | |" % (tag, d["aggregate"].get("prompt_tok_s"), d["aggregate"].get("output_tok_s"), d.get("wall_s")))
open(os.path.join(out, "summary.md"), "w").write("\n".join(rows) + "\n")
print("\n".join(rows))
PY
