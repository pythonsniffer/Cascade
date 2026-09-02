#!/usr/bin/env bash
# Cascade — run the whole twin without Docker.
#
#   ./scripts/run_local.sh              build the frontend, serve on :4173  (production mode)
#   ./scripts/run_local.sh --dev        Vite dev server on :5173 with hot reload
#   ./scripts/run_local.sh --backend    backend only, on :8000
#
# Use this when Docker is unavailable or unverified. Same app, same routing.
# Nothing here trains a model: the backend loads artifacts/ and serves them.

set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$PWD"

MODE="preview"
case "${1:-}" in
  --dev)     MODE="dev" ;;
  --backend) MODE="backend" ;;
  --help|-h) sed -n '2,10p' "$0"; exit 0 ;;
  "")        ;;
  *)         echo "unknown option: $1 (try --help)" >&2; exit 2 ;;
esac

BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-$([ "$MODE" = dev ] && echo 5173 || echo 4173)}"
PY="$ROOT/.venv/bin/python"

log()  { printf '\033[1m==>\033[0m %s\n' "$*"; }
fail() { printf '\033[31mERROR:\033[0m %s\n' "$*" >&2; exit 1; }

# ── preflight ───────────────────────────────────────────────────────────
[ -d artifacts ] || fail "artifacts/ not found. The backend loads models from there and
       never trains. Run: python tools/export_artifacts.py --out artifacts"

missing=""
for f in graph.pt normalization.json chains.json bstan_seed0.pt bstan_seed1.pt bstan_seed2.pt; do
  [ -f "artifacts/$f" ] || missing="$missing $f"
done
[ -z "$missing" ] || fail "missing artifacts:$missing
       Run: python tools/export_artifacts.py --out artifacts"

if [ ! -f artifacts/best.pt ]; then
  log "note: artifacts/best.pt absent — the defect layer will report itself off and"
  log "      emit no detections. The bottleneck layer is unaffected."
elif ! compgen -G "artifacts/sample_frames/*" > /dev/null 2>&1; then
  log "note: no frames in artifacts/sample_frames — the detector is loaded but has"
  log "      nothing to inspect, so no detections are produced."
fi

# ── python env ──────────────────────────────────────────────────────────
if [ ! -x "$PY" ]; then
  log "creating .venv"
  python3 -m venv .venv
fi
if ! "$PY" -c "import fastapi, torch, torch_geometric" 2>/dev/null; then
  log "installing backend dependencies (several minutes on a cold cache)"
  "$PY" -m pip install -q --upgrade pip
  "$PY" -m pip install -q -r backend/requirements.txt
fi

# ── start backend ───────────────────────────────────────────────────────
cleanup() {
  [ -n "${BACK_PID:-}" ] && kill "$BACK_PID" 2>/dev/null || true
  [ -n "${FRONT_PID:-}" ] && kill "$FRONT_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

log "starting backend on :$BACKEND_PORT"
"$PY" -m uvicorn backend.main:app --host 0.0.0.0 --port "$BACKEND_PORT" &
BACK_PID=$!

log "waiting for models to load (torch + BSTAN ensemble takes a moment)"
for i in $(seq 1 60); do
  if curl -fsS "http://127.0.0.1:$BACKEND_PORT/health" >/dev/null 2>&1; then
    break
  fi
  kill -0 "$BACK_PID" 2>/dev/null || fail "backend exited during startup — see the log above.
       A ConfigError here is intentional: it fails fast rather than serving wrong numbers."
  sleep 2
  [ "$i" = 60 ] && fail "backend did not become healthy within 120s"
done

"$PY" - "$BACKEND_PORT" <<'PYEOF'
import json, sys, urllib.request
h = json.load(urllib.request.urlopen(f"http://127.0.0.1:{sys.argv[1]}/health", timeout=20))
d = h["models"]["defect"]
print(f"    models_loaded : {h['models_loaded']}")
print(f"    bottleneck    : {h['models']['bottleneck']['ensemble_size']} BSTAN models, "
      f"window {h['models']['bottleneck']['T_w']} shifts")
print(f"    detector      : {d['state']} — {d['detail']}")
print(f"    chains        : {h['models']['chains']['rules']} rules")
PYEOF

if [ "$MODE" = "backend" ]; then
  log "backend only. API http://localhost:$BACKEND_PORT  ·  docs /docs"
  wait "$BACK_PID"
fi

# ── frontend ────────────────────────────────────────────────────────────
cd frontend
[ -d node_modules ] || { log "installing frontend dependencies"; npm ci; }

export VITE_BACKEND="http://127.0.0.1:$BACKEND_PORT"
if [ "$MODE" = "dev" ]; then
  log "starting Vite dev server on :$FRONTEND_PORT"
  npm run dev -- --host --port "$FRONTEND_PORT" &
else
  log "building the frontend"
  npm run build
  log "serving the production build on :$FRONTEND_PORT"
  npm run preview -- --host --port "$FRONTEND_PORT" &
fi
FRONT_PID=$!
cd "$ROOT"

sleep 4
cat <<EOF

  Cascade is running.

    dashboard   http://localhost:$FRONTEND_PORT
    API + docs  http://localhost:$BACKEND_PORT/docs

  Press Play (or Next shift) in the top bar. The first two shifts report
  "warming up" — the forecaster needs a 3-shift history window before it
  predicts. That is the honest state, not a bug.

  Ctrl-C stops both.

EOF

wait "$FRONT_PID"
