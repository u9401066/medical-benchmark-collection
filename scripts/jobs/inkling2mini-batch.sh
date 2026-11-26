#!/usr/bin/env bash
# Fourth window on the recorded xhigh agent run: does a smaller logical batch (-b) keep one agent's decoding going while the
# other agent's long prompt is processed? Deployed setting: b12651, IQ4_XS all on the GPU, 2 slots with their own 131k
# (--no-kv-unified, -c 262144), -ub 256, -b 2048. With -b 2048 a decode step waits for up to 2,048 prompt tokens of the other
# slot (~1 s); with -b 256 for at most one 256-token micro-batch.
#   A. -b 2048 (the deployed setting, measured again in the same window for a fair comparison)
#   B. -b 256
# each: one agent (requests 1-8) and two agents at once (--parallel 2); B also the 2 x 95%-of-a-slot stress test.
#
#   cd ~/medical-benchmark-collection && env "TEST_PATTERN=--port 8091" bash scripts/gpu_window.sh scripts/jobs/inkling2mini-batch.sh
set -u -o pipefail
HERE="$(cd "$(dirname "$0")/../.." && pwd)"
PROD_REPO="${PROD_REPO:-$HOME/llmapi_server}"
MODELS="${INKLING_MODELS:-$HOME/inkling/models}"
IQ4="$MODELS/Inkling-2-Mini-UD-IQ4_XS.gguf"
B651="$HOME/inkling/bin/b12651/llama-server"
PORT=8091
URL="http://127.0.0.1:$PORT"
OUT="$HERE/results/speed/agent/window4"
LOGS="$HERE/results/logs"
PY="$HERE/.venv/bin/python"
TRACE="$HERE/results/speed/agent/trace-xhigh.jsonl"
SCREEN="${SCREEN_REQUESTS:-1-8}"
BATCHES="${BATCHES:-2048 256}"
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
serve() {  # serve <tag> VAR=value ...  (on top of the deployed setting)
  local tag=$1; shift
  local slog="$LOGS/inkling-batch-$tag-$(date -u +%Y%m%dT%H%M%SZ).log"
  log "starting $tag: $*"
  env LLM_IGNORE_PAUSE=1 INKLING_ENV_FILE=none INKLING_PORT=$PORT INKLING_HOST=127.0.0.1 INKLING_MODEL="$IQ4" INKLING_DRAFT=none \
    INKLING_SLOTS=2 INKLING_CTX=262144 INKLING_KV_UNIFIED=0 INKLING_UBATCH=256 INKLING_CPU_MOE_LAYERS= INKLING_BIN="$B651" "$@" \
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
trap 'unserve' EXIT
replay() {  # replay <tag> <requests> [extra args]
  local tag=$1 req=$2; shift 2
  "$PY" "$HERE/scripts/agent_replay.py" --trace "$TRACE" --url "$URL" --requests "$req" --effort max --quiet \
    --label "$tag" --out "$OUT/$tag.json" "$@" | tail -3
}
alive() { [ -n "$SRV" ] && kill -0 "$SRV" 2>/dev/null; }

for b in $BATCHES; do
  tag="n2-ub256-b$b"
  if serve "$tag" INKLING_BATCH=$b; then
    replay "$tag" "$SCREEN"
    replay "$tag-parallel2" "$SCREEN" --parallel 2
    if [ "$b" != 2048 ]; then
      "$PY" "$HERE/scripts/stress_long.py" --url "$URL" --n 2 --chars $(( 131072 * 95 / 100 * 395 / 100 )) --max-tokens 256 \
        --out "$OUT/$tag-stress-2x.json" > /dev/null && alive && log "$tag: stress 2x ok (GPU peak $(cat "$OUT/$tag.peak") MiB)" \
        || log "$tag: stress 2x FAILED"
    fi
  fi
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
        rows.append("| %s | %s (%d/%d ok) | %s | %s | %s | %s | %s |" % (tag, d["requests"], r["ok"], r["requests"], r["prefill_tps"],
                    r["decode_tps"], r.get("modeled_task_s"), r["wall_s"], peak))
    if d.get("aggregate"):
        rows.append("| %s (both) | | %s | %s | | %s | |" % (tag, d["aggregate"].get("prompt_tok_s"), d["aggregate"].get("output_tok_s"), d.get("wall_s")))
open(os.path.join(out, "summary.md"), "w").write("\n".join(rows) + "\n")
print("\n".join(rows))
PY
log "done"
