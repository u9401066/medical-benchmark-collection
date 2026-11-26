#!/usr/bin/env bash
# Follow-up to inkling2mini-agent-speed.sh (same replay of the recorded xhigh agent run):
#   1. the production candidate (b12651, all on the GPU, 4 slots sharing 131k, -ub 512): long-prompt stress and two agents at once
#   2. two agents at once with -b 512 (a decoding agent waits for at most one 512-token prefill chunk of the other per step)
#   3. two slots with their own 131k each (--no-kv-unified, -c 262144): one agent, two at once
#   4. keeping Clef-Flash (and so Sentinel) on the GPU: UD-Q3_K_XL all on the GPU next to it (-ub 64, 128), and its selection latency
#
#   cd ~/medical-benchmark-collection && env PAUSE_CLEF=1 "TEST_PATTERN=--port 809[14]" bash scripts/gpu_window.sh scripts/jobs/inkling2mini-agent-speed2.sh
set -u -o pipefail
HERE="$(cd "$(dirname "$0")/../.." && pwd)"
PROD_REPO="${PROD_REPO:-$HOME/llmapi_server}"
ROUTER_REPO="${ROUTER_REPO:-$HOME/llama-mcp-router}"
MODELS="${INKLING_MODELS:-$HOME/inkling/models}"
IQ4="$MODELS/Inkling-2-Mini-UD-IQ4_XS.gguf"
Q3="$MODELS/Inkling-2-Mini-UD-Q3_K_XL.gguf"
B651="$HOME/inkling/bin/b12651/llama-server"
PORT=8091
URL="http://127.0.0.1:$PORT"
OUT="$HERE/results/speed/agent/window2"
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
serve() {  # serve <tag> VAR=value ...  (on top of: IQ4_XS, b12651, 131k shared by 4 slots, -ub 512, q8_0 KV, all on the GPU)
  local tag=$1; shift
  local slog="$LOGS/inkling-agent-speed2-$tag-$(date -u +%Y%m%dT%H%M%SZ).log"
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
clef_stop() {
  for p in $(pgrep -f -- "--port 8094"); do grep -qa -- "llama-server" "/proc/$p/cmdline" 2>/dev/null && kill "$p"; done
  sleep 2
}
trap 'unserve; clef_stop' EXIT
replay() {  # replay <tag> <requests> [extra args]
  local tag=$1 req=$2; shift 2
  "$PY" "$HERE/scripts/agent_replay.py" --trace "$TRACE" --url "$URL" --requests "$req" --effort max --quiet \
    --label "$tag" --out "$OUT/$tag.json" "$@" | tail -3
}
alive() { [ -n "$SRV" ] && kill -0 "$SRV" 2>/dev/null; }
stress() {  # stress <tag> <n...>: n concurrent prompts filling 95% of the 131k context together (or of each slot: per-slot)
  local tag=$1; shift
  for n in "$@"; do
    "$PY" "$HERE/scripts/stress_long.py" --url "$URL" --n "$n" --chars $(( 131072 * 95 / 100 * 395 / 100 / ${STRESS_DIV:-$n} )) --max-tokens 256 \
      --out "$OUT/$tag-stress-${n}x.json" > /dev/null || { log "$tag: stress ${n}x failed"; return 1; }
    alive || { log "$tag: server died in stress ${n}x"; return 1; }
    log "$tag: stress ${n}x ok (GPU peak so far $(cat "$OUT/$tag.peak") MiB)"
  done
}

# 1. the production candidate
if serve u4-ub512; then
  stress u4-ub512 2 4 && replay u4-ub512-parallel2 "$SCREEN" --parallel 2
  alive || log "u4-ub512: server died"
  log "u4-ub512: GPU peak $(cat "$OUT/u4-ub512.peak") MiB"
fi
unserve

# 2. smaller logical batch
if serve u4-ub512-b512 INKLING_BATCH=512; then
  replay u4-ub512-b512 "$SCREEN"
  replay u4-ub512-b512-parallel2 "$SCREEN" --parallel 2
  alive || log "u4-ub512-b512: server died"
  log "u4-ub512-b512: GPU peak $(cat "$OUT/u4-ub512-b512.peak") MiB"
fi
unserve

# 3. two slots, 131k each
for ub in 256 512; do
  tag="n2-ub$ub"
  if serve "$tag" INKLING_SLOTS=2 INKLING_CTX=262144 INKLING_KV_UNIFIED=0 INKLING_UBATCH=$ub; then
    replay "$tag" "$SCREEN"
    replay "$tag-parallel2" "$SCREEN" --parallel 2
    STRESS_DIV=1 stress "$tag" 2  # two prompts of 95% of a slot each
    alive || log "$tag: server died"
    log "$tag: GPU peak $(cat "$OUT/$tag.peak") MiB"
  fi
  unserve
done

# 4. UD-Q3_K_XL all on the GPU next to Clef-Flash
for ub in 64 128; do
  tag="q3-clef-ub$ub"
  serve "$tag" INKLING_MODEL="$Q3" INKLING_UBATCH=$ub || { unserve; continue; }
  env CLEF_IGNORE_PAUSE=1 CLEF_HOST=127.0.0.1 CLEF_PORT=8094 CLEF_WAIT_URL="$URL/health" setsid bash "$PROD_REPO/scripts/start_clef.sh" \
    > "$LOGS/clef-gpu-window2-ub$ub.log" 2>&1 < /dev/null &
  up=0
  for _ in $(seq 90); do curl -sf -m 2 http://127.0.0.1:8094/health >/dev/null && { up=1; break; }; sleep 2; done
  log "$tag: Clef-Flash $([ $up = 1 ] && echo up || echo 'did not start') (GPU memory used $(gpu_used) MiB)"
  if [ $up = 1 ]; then
    replay "$tag" "$SCREEN"
    [ "$ub" = 64 ] && (cd "$ROUTER_REPO" && timeout 600 .venv/bin/python benchmarks/run_bench.py --queries benchmarks/data/queries_heldout.jsonl \
      --sample 8 --clef-url http://127.0.0.1:8094 --only "clef 2-pass" --out "$OUT/clef-gpu-select" 2>&1 | grep -E "^\| clef")
    stress "$tag" 2 4
    alive || log "$tag: server died"
    log "$tag: GPU peak $(cat "$OUT/$tag.peak") MiB"
  fi
  clef_stop
  unserve
done

"$PY" - "$OUT" <<'PY'
import glob, json, os, sys
out = sys.argv[1]
rows = ["| setting | requests | prefill tok/s | decode tok/s | modeled task s | wall s | GPU peak MiB |", "|---|---|---|---|---|---|---|"]
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
        rows.append("| %s | %s (%d/%d ok) | %s | %s | %s | %s | %s |" % (tag, d["requests"], r["ok"], r["requests"], r["prefill_tps"], r["decode_tps"],
                    r.get("modeled_task_s"), r["wall_s"], peak))
    if d.get("aggregate"):
        rows.append("| %s (both) | | %s | %s | | %s | |" % (tag, d["aggregate"].get("prompt_tok_s"), d["aggregate"].get("output_tok_s"), d.get("wall_s")))
open(os.path.join(out, "summary.md"), "w").write("\n".join(rows) + "\n")
print("\n".join(rows))
PY
