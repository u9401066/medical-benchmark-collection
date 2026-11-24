#!/usr/bin/env bash
# Inkling 2 Mini UD-IQ4_XS on the recorded xhigh agent run (results/speed/agent/trace-xhigh.jsonl, scripts/agent_replay.py):
# which engine settings make agent turns faster. Run inside scripts/gpu_window.sh with the decision model paused too:
#
#   cd ~/medqa-bench && env PAUSE_CLEF=1 "TEST_PATTERN=--port 809[14]" bash scripts/gpu_window.sh scripts/jobs/inkling2mini-agent-speed.sh
#
# Production (b12631, experts of layers 21/20/22 in RAM next to Clef-Flash, -ub 64) is the recorded trace itself.
#   1. screening, replay of requests 1-8 (17k-53k-token prompts, two full re-processings) at reasoning effort max:
#        b12651 with the production layout (does the new build help while Clef stays on the GPU?), then everything on the
#        GPU (possible only without Clef there): b12631 -ub 256, b12651 -ub 64/256/512/1024
#   2. speculative decoding on the fastest of these: DSpark (Inkling's drafter, 2 and 3 tokens) and ngram-mod
#   3. the best setting: a context compaction at effort max vs low, long-prompt stress (1x/2x/4x concurrent prompts filling 95% of the shared 131k KV; production
#        crashed with CUDA OOM on 2 x 64k on 2026-11-24) and two agent replays at once
#   4. Clef-Flash on the CPU only (no VRAM) next to it: tool-selection latency (llama-mcp-router run_bench, 8 of the 52 held-out queries)
# Results: results/speed/agent/window/*.json, a summary table in results/speed/agent/window/summary.md.
set -u -o pipefail
HERE="$(cd "$(dirname "$0")/../.." && pwd)"
PROD_REPO="${PROD_REPO:-$HOME/llmapi_server}"
ROUTER_REPO="${ROUTER_REPO:-$HOME/llama-mcp-router}"
MODELS="${INKLING_MODELS:-$HOME/inkling/models}"
MODEL="$MODELS/Inkling-2-Mini-UD-IQ4_XS.gguf"
DRAFT="$MODELS/dspark-Inkling-2-Mini-Q8_0.gguf"
B631="$HOME/inkling/bin/b12631/llama-server"
B651="$HOME/inkling/bin/b12651/llama-server"
PORT=8091
URL="http://127.0.0.1:$PORT"
OUT="$HERE/results/speed/agent/window"
LOGS="$HERE/results/logs"
PY="$HERE/.venv/bin/python"
TRACE="$HERE/results/speed/agent/trace-xhigh.jsonl"
CTX=131072
TOTAL_MIB=24564
SCREEN="${SCREEN_REQUESTS:-1-8}"
mkdir -p "$OUT" "$LOGS"
SRV=""
MON=""
log() { echo "[job $(date -u +%H:%M:%S)] $*"; }
gpu_used() { nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits -i 0 | tr -d ' '; }
monitor() {  # GPU memory peak while a variant runs -> $OUT/<tag>.peak
  local f=$1; echo 0 > "$f"
  ( while :; do u=$(gpu_used); [ "$u" -gt "$(cat "$f")" ] && echo "$u" > "$f"; sleep 0.5; done ) &
  MON=$!
}
serve() {  # serve <tag> VAR=value ...  (INKLING_* on top of: IQ4_XS, 131k shared by 4 slots, q8_0 KV, all on the GPU)
  local tag=$1; shift
  local slog="$LOGS/inkling-agent-speed-$tag-$(date -u +%Y%m%dT%H%M%SZ).log"
  log "starting $tag: $*"
  env LLM_IGNORE_PAUSE=1 INKLING_ENV_FILE=none INKLING_PORT=$PORT INKLING_HOST=127.0.0.1 INKLING_MODEL="$MODEL" INKLING_DRAFT=none \
    INKLING_SLOTS=4 INKLING_CTX=$CTX INKLING_UBATCH=256 INKLING_CPU_MOE_LAYERS= INKLING_BIN="$B651" "$@" \
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
clef_cpu_stop() {
  for p in $(pgrep -f -- "--port 8094"); do grep -qa -- "llama-server" "/proc/$p/cmdline" 2>/dev/null && kill "$p"; done
}
trap 'unserve; clef_cpu_stop' EXIT
replay() {  # replay <tag> <requests> [extra args]: 0 when every request finished
  local tag=$1 req=$2; shift 2
  "$PY" "$HERE/scripts/agent_replay.py" --trace "$TRACE" --url "$URL" --requests "$req" --effort max --quiet \
    --label "$tag" --out "$OUT/$tag.json" "$@" | tail -3
}
alive() { [ -n "$SRV" ] && kill -0 "$SRV" 2>/dev/null; }
# modeled task time of a replay (lower is better), 999999 when missing
modeled() { "$PY" -c 'import json,sys
try:
    d=json.load(open(sys.argv[1])); r=d["runs"][0]; print(int(r["modeled_task_s"]*10) if r["ok"]==r["requests"] else 999999)
except Exception: print(999999)' "$1"; }
variant() {  # variant <tag> <requests> VAR=value ...
  local tag=$1 req=$2; shift 2
  serve "$tag" "$@" || { unserve; return 1; }
  replay "$tag" "$req"
  alive || log "$tag: server died during the replay"
  log "$tag: GPU peak $(cat "$OUT/$tag.peak") MiB"
  unserve
}

# 1. screening
variant p651-ub64 1-4 INKLING_UBATCH=64 "INKLING_CPU_MOE_LAYERS=21 20 22"
variant g631-ub256 "$SCREEN" INKLING_BIN="$B631"
for ub in 64 256 512 1024; do variant "g651-ub$ub" "$SCREEN" INKLING_UBATCH=$ub; done
best=""; bs=999999
for ub in 64 256 512 1024; do s=$(modeled "$OUT/g651-ub$ub.json"); [ "$s" -lt "$bs" ] && { bs=$s; best=$ub; }; done
[ -n "$best" ] || { log "no all-GPU variant finished; stopping"; exit 1; }
log "fastest all-GPU ubatch: $best (modeled task $((bs / 10)) s for requests $SCREEN)"

# 2. speculative decoding
variant "g651-ub$best-dspark2" "$SCREEN" INKLING_UBATCH=$best INKLING_DRAFT="$DRAFT" INKLING_DRAFT_N=2
variant "g651-ub$best-dspark3" "$SCREEN" INKLING_UBATCH=$best INKLING_DRAFT="$DRAFT" INKLING_DRAFT_N=3
variant "g651-ub$best-ngram" "$SCREEN" INKLING_UBATCH=$best "INKLING_EXTRA_ARGS=--spec-type ngram-mod"
spec=""; tag="g651-ub$best"; ts=$bs
for v in dspark2 dspark3 ngram; do
  s=$(modeled "$OUT/g651-ub$best-$v.json")
  [ $(( s * 100 )) -le $(( bs * 95 )) ] && [ "$s" -lt "$ts" ] && { ts=$s; spec=$v; tag="g651-ub$best-$v"; }
done
log "best: $tag (modeled $((ts / 10)) s)"
SPEC=()
case $spec in
  dspark2) SPEC=(INKLING_DRAFT="$DRAFT" INKLING_DRAFT_N=2);;
  dspark3) SPEC=(INKLING_DRAFT="$DRAFT" INKLING_DRAFT_N=3);;
  ngram) SPEC=("INKLING_EXTRA_ARGS=--spec-type ngram-mod");;
esac

# 3. stability of the best setting, then two agents at once
serve "stable-$tag" INKLING_UBATCH=$best "${SPEC[@]}" || exit 1
# a context compaction (trace request 14: summarise the oldest span) at the turn's effort and at a low one
for e in max low; do replay "compaction-$e" 14 --effort $e --budget cap --max-tokens 16384; done
tot=$(( CTX * 95 / 100 ))
ok=1
for n in 1 2 4; do
  "$PY" "$HERE/scripts/stress_long.py" --url "$URL" --n "$n" --chars $(( tot * 395 / 100 / n )) --max-tokens 256 \
    --out "$OUT/stable-$tag-stress-${n}x.json" > /dev/null || { log "stable-$tag: stress ${n}x failed"; ok=0; break; }
  alive || { log "stable-$tag: server died in stress ${n}x"; ok=0; break; }
  log "stable-$tag: stress ${n}x ok (GPU peak so far $(cat "$OUT/stable-$tag.peak") MiB)"
done
[ $ok = 1 ] && { replay "stable-$tag-parallel2" "$SCREEN" --parallel 2 || ok=0; alive || ok=0; }
log "stable-$tag: $([ $ok = 1 ] && echo passed || echo FAILED), GPU peak $(cat "$OUT/stable-$tag.peak") MiB"

# 4. Clef-Flash on the CPU next to it
if alive; then
  env CLEF_IGNORE_PAUSE=1 CLEF_DEVICE=none CLEF_HOST=127.0.0.1 CLEF_PORT=8094 setsid bash "$PROD_REPO/scripts/start_clef.sh" > "$LOGS/clef-cpu-window.log" 2>&1 < /dev/null &
  for _ in $(seq 120); do curl -sf -m 2 http://127.0.0.1:8094/health >/dev/null && break; sleep 2; done
  (cd "$ROUTER_REPO" && timeout 600 .venv/bin/python benchmarks/run_bench.py --queries benchmarks/data/queries_heldout.jsonl --sample 8 \
    --clef-url http://127.0.0.1:8094 --only "clef 2-pass" --out "$OUT/clef-cpu-select" 2>&1 | grep -E "^\| clef") \
    || log "clef on the CPU: selection bench failed or timed out"
  clef_cpu_stop
fi
unserve

# summary
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
    peak = open(os.path.join(out, tag.replace("-parallel2", "") + ".peak")).read().strip() if os.path.exists(os.path.join(out, tag.replace("-parallel2", "") + ".peak")) else "-"
    for r in d["runs"]:
        rows.append("| %s | %s (%d/%d ok) | %s | %s | %s | %s | %s | %s |" % (tag, d["requests"], r["ok"], r["requests"], r["prefill_tps"], r["decode_tps"],
                    r.get("draft_acceptance", "-"), r.get("modeled_task_s"), r["wall_s"], peak))
open(os.path.join(out, "summary.md"), "w").write("\n".join(rows) + "\n")
print("\n".join(rows))
PY
