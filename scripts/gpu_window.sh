#!/usr/bin/env bash
# Maintenance window for a test that needs the GPU: pause production (Bonsai's llama-server on :8081), run a job script that
# starts/stops its own test servers, then ALWAYS stop whatever the job left running and restore production - also after an
# error, Ctrl-C or SIGTERM.
#
#   TEST_PATTERN=inkling/bin scripts/gpu_window.sh scripts/jobs/inkling2mini.sh
#
# Environment (defaults match the llm01 server this benchmark was run on):
#   PROD_REPO     llmapi_server checkout with scripts/start_bonsai.sh and config/bonsai.pause   [~/llmapi_server]
#   PROD_PATTERN  command-line pattern of the production llama-server (any model on :8081)       [llama-server .*--port 8081]
#   PROD_URL      production health URL                                                         [http://127.0.0.1:8081/health]
#   TEST_PATTERN  command-line pattern of the test servers, killed when the window ends         (required)
#   PAUSE_CLEF=1  also pause the decision model (Clef-Flash on :8000, laya.service) for the whole GPU; needs a start_clef.sh
#                 that waits on config/clef.pause. CLEF_PATTERN / CLEF_URL                [Clef-Flash.*--port 8000 / :8000/health]
set -u
JOB="${1:?usage: gpu_window.sh <job script> [args...]}"
shift
: "${TEST_PATTERN:?set TEST_PATTERN to the command-line pattern of the test servers}"
PROD_REPO="${PROD_REPO:-$HOME/llmapi_server}"
PROD_PATTERN="${PROD_PATTERN:-llama-server .*--port 8081}"
PROD_URL="${PROD_URL:-http://127.0.0.1:8081/health}"
PAUSE="$PROD_REPO/config/bonsai.pause"
PAUSE_CLEF="${PAUSE_CLEF:-0}"
CLEF_PAUSE="$PROD_REPO/config/clef.pause"
CLEF_PATTERN="${CLEF_PATTERN:-Clef-Flash.*--port 8000}"
CLEF_URL="${CLEF_URL:-http://127.0.0.1:8000/health}"
JOB="$(realpath "$JOB")"
log() { echo "[window $(date -u +%H:%M:%S)] $*"; }
prod_systemd() { [ "$(systemctl show -p ActiveState --value bonsai 2>/dev/null)" = active ]; }
gpu_used() { nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits -i 0 | tr -d ' '; }

restore() {
  trap - EXIT INT TERM
  log "stopping test servers ($TEST_PATTERN)"
  # only llama-server processes: the shell that started this window may carry the pattern in its own command line
  test_pids() { for p in $(pgrep -f -- "$TEST_PATTERN"); do [ "$(cat /proc/$p/comm 2>/dev/null)" = llama-server ] && echo "$p"; done; }
  for p in $(test_pids); do kill -TERM "$p"; done
  for _ in $(seq 30); do [ -z "$(test_pids)" ] && break; sleep 1; done
  for p in $(test_pids); do kill -9 "$p"; done
  log "restoring production"
  rm -f "$PAUSE"
  if ! prod_systemd && ! pgrep -f -- "$PROD_PATTERN" >/dev/null; then
    setsid nohup bash "$PROD_REPO/scripts/start_bonsai.sh" >> "$HOME/.local/share/bonsai-manual.log" 2>&1 < /dev/null &
  fi
  for _ in $(seq 120); do
    if curl -sf -m 3 "$PROD_URL" >/dev/null; then log "production healthy again"; return 0; fi
    sleep 5
  done
  log "WARNING: production did not become healthy within 10 min; check $PROD_REPO"
  return 1
}
restore_clef() {
  [ "$PAUSE_CLEF" = 1 ] || return 0
  log "restoring the decision model"
  rm -f "$CLEF_PAUSE"
  for _ in $(seq 120); do
    if curl -sf -m 3 "$CLEF_URL" >/dev/null; then log "decision model healthy again"; return 0; fi
    sleep 5
  done
  log "WARNING: decision model ($CLEF_URL) did not become healthy within 10 min"
  return 1
}
trap 'restore; restore_clef' EXIT
trap 'exit 130' INT TERM

if [ "$PAUSE_CLEF" = 1 ]; then
  log "pausing the decision model ($CLEF_PATTERN)"
  touch "$CLEF_PAUSE"
  # SIGKILL for the same reason as below; its llama-server runs under a private ld.so, so match the command line only
  for p in $(pgrep -f -- "$CLEF_PATTERN"); do grep -qa -- "llama-server" "/proc/$p/cmdline" 2>/dev/null && kill -9 "$p"; done
  for _ in $(seq 30); do pgrep -f -- "$CLEF_PATTERN" >/dev/null || break; sleep 1; done
fi

log "pausing production ($PROD_PATTERN)"
touch "$PAUSE"
for p in $(pgrep -f -- "$PROD_PATTERN"); do
  # SIGKILL: a clean exit would leave a systemd unit with Restart=on-failure stopped; this way it restarts and waits on the pause file
  [ "$(cat /proc/$p/comm 2>/dev/null)" = llama-server ] && kill -9 "$p"
done
before="$(gpu_used)"
for _ in $(seq 60); do pgrep -f -- "$PROD_PATTERN" >/dev/null || break; sleep 1; done
sleep 3
log "GPU memory used: ${before} -> $(gpu_used) MiB"
log "job: $JOB $*"
bash "$JOB" "$@"
rc=$?
log "job exited with $rc"
exit $rc
