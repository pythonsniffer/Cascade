# Docker deployment — instructions for an agent

**Audience:** an AI agent or engineer with a normal machine (working Docker, unrestricted
registry access) who must bring Cascade up and confirm it works.

**Status of this file:** the compose setup was written and statically validated, but
**never executed**, because the environment it was authored in blocks Docker Hub's blob
CDN (`production.cloudfront.docker.com` returns 403). Treat the build as unverified.
Everything else — backend, frontend, models, 44 backend tests, 33 browser checks — was
run and passes. Where a step is likely to be where things first break, this file says so.

---

## 0. Preconditions

```bash
docker --version          # 24+ ; compose v2 (`docker compose`, not `docker-compose`)
docker run --rm hello-world   # MUST succeed before you continue
df -h .                   # need ~8 GB free: the backend image is 2.5-3 GB
```

If `hello-world` fails, stop. Every failure below will be a registry problem wearing a
different mask.

Confirm the artifacts are present — the backend loads these and **never trains**:

```bash
ls artifacts/
# bstan_seed0.pt bstan_seed1.pt bstan_seed2.pt   BSTAN ensemble (3 seeds)
# graph.pt                                        fixed 35-station topology
# normalization.json                              xmin/xmax, T_w, CONF_THRESHOLD, FEATURES
# chains.json                                     learned defect-chain table
# mappings.json  metrics.json  line_shifts.npz
# best.pt                                         fine-tuned YOLOv8 detector
```

If `best.pt` is missing the stack still runs — the defect layer reports itself off and
emits nothing. That is intended behaviour, not a failure.

## 1. Build and start

```bash
docker compose up --build
```

First build takes **10-25 minutes**, almost entirely `pip install torch` +
`ultralytics`. It is not hung. Then:

- dashboard → http://localhost:3000
- API docs  → http://localhost:8000/docs

## 2. Verify — do not skip

```bash
# 1. models loaded from artifacts
curl -s localhost:8000/health | jq '{
  models_loaded,
  bstan: .models.bottleneck.ensemble_size,
  detector: .models.defect.state,
  chains: .models.chains.rules }'
# expect: models_loaded true, bstan 3, chains 3,
#         detector "no_frames" (or "ready" if you supplied frames)

# 2. topology is served from graph.pt, 35 stations
curl -s localhost:8000/line | jq '.n_stations, (.edges|length)'

# 3. a tick produces a real forecast (first 2 ticks report warming_up — correct,
#    the model needs a 3-shift history window)
for i in 1 2 3 4; do curl -sX POST localhost:8000/control/tick -o /dev/null; done
curl -s localhost:8000/twin/state?limit=1 | jq '.last_tick.bottleneck'

# 4. P&L re-projects from stored counts with no model rerun
curl -s localhost:8000/pnl | jq '{cumulative_net, shifts_counted}'
curl -sX POST localhost:8000/api/config/pnl -H 'content-type: application/json' \
     -d '{"values":{"downtime_cost_per_min":1700}}' | jq '.cumulative_net'
# cumulative_net must change immediately

# 5. the dashboard is served, and a deep link does not 404
curl -s -o /dev/null -w '%{http_code}\n' localhost:3000/
curl -s -o /dev/null -w '%{http_code}\n' localhost:3000/pnl     # must be 200, not 404
```

Then open http://localhost:3000, press **Play**, and confirm the floor animates, the
predicted bottleneck pulses orange, and the alert rail and P&L update live.

## 3. Failure modes, in the order you will hit them

**Build fails pulling `python:3.11-slim` or `node:22-alpine`** — registry/network, not the
Dockerfile. Check the daemon's proxy config. This is exactly what blocked the authoring
environment.

**Backend exits immediately with a `ConfigError`** — working as designed: it fails fast
rather than starting half-loaded. Read the message; it names the problem. Usually the
`./artifacts` bind mount did not land. Check with
`docker compose exec backend ls /app/artifacts`.

**Backend healthcheck never goes healthy** — importing torch and loading the BSTAN
ensemble takes time. `start_period` is 90 s; on a slow machine raise it in
`backend/Dockerfile`. Watch `docker compose logs -f backend`; look for
`cascade ready: 35 stations`.

**Frontend up, dashboard shows "Can't reach the twin"** — nginx cannot reach the backend.
`docker compose exec frontend wget -qO- http://backend:8000/health`. If that fails the
backend is unhealthy; if it succeeds, the nginx `/api/` proxy block is at fault.

**Dashboard loads but never goes Live** — the WebSocket is not upgrading. Confirm
`frontend/nginx.conf` still has the `map $http_upgrade $connection_upgrade` block and the
`Upgrade`/`Connection` headers inside `location /api/`. Both are required.

**`/pnl` returns JSON instead of the app** — the SPA fallback is broken. The frontend's
own routes (`/pnl`, `/history`, `/config`) share names with API endpoints; the app must
call the API through its `/api` mount and nginx must `try_files ... /index.html`.

**Image is far larger than expected** — the default installs the CUDA torch wheel. Switch
to CPU-only in `backend/Dockerfile` for a much smaller image:

```dockerfile
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
 && pip install --no-cache-dir -r /app/backend/requirements.txt
```

This is not the default only because that host was unreachable where this was authored.

## 4. Enabling detections

`best.pt` is present, so the detector loads. It still needs **frames** to inspect —
`/health` will report `"state": "no_frames"` until you supply them:

```bash
mkdir -p artifacts/sample_frames
cp /path/to/mvtec_yolo/test/images/*.png artifacts/sample_frames/
docker compose restart backend
curl -s localhost:8000/health | jq '.models.defect.state'   # -> "ready"
```

Detections then appear on `/quality` and chain alerts stream into the live rail.

**Do not substitute arbitrary images.** The detector recognises 20 MVTec defect classes;
run it on unrelated photographs and it emits meaningless boxes that the UI would present
as real defect detections. An empty gallery is honest; a fabricated one is not.

## 5. Postgres instead of SQLite

```bash
docker compose -f docker-compose.yml -f docker-compose.postgres.yml up
```

Only `CASCADE_DATABASE_URL` changes. SQLModel creates the same tables; no model, service
or contract code is touched.

## 6. Operating notes

| | |
|---|---|
| Reset all data and config | `docker compose down -v` (config reseeds from `backend/config/defaults/`) |
| Keep data, restart | `docker compose restart` |
| Change ports | `FRONTEND_PORT` / `BACKEND_PORT` env vars |
| Logs | `docker compose logs -f backend` |
| Config edits | live via the dashboard; persisted in the `cascade-config` volume; audited |

Mounts: `./artifacts` is **read-only** by design — the backend must never write to model
artifacts. `cascade-config` and `cascade-data` are read-write named volumes so live P&L
edits and the database survive a restart.

## 7. What "done" means

- [ ] `docker compose up --build` completes
- [ ] `/health` → `models_loaded: true`, `ensemble_size: 3`
- [ ] a tick returns a real forecast after the warm-up shifts
- [ ] editing a P&L assumption changes `/pnl` immediately, no restart
- [ ] http://localhost:3000/pnl returns the app, not JSON
- [ ] pressing Play animates the floor and streams alerts

If all six hold, the deployment is good. Report anything that failed verbatim rather than
working around it — several of these checks exist because the corresponding bug was
already found and fixed once.
