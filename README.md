# Cascade — Digital Twin for a 35-station vehicle assembly line

A 3-layer live digital twin built for the Accenture Innovation Challenge 2026,
Problem Statement 4 (DigitalTwin.ai). It forecasts two things a shift ahead:

1. **Bottlenecks** — where the line's throughput will choke next.
2. **Defect chains** — which defect a caught defect will trigger downstream, so a
   vehicle can be re-inspected before a batch carries the flaw forward.

One shared graph, two predictors, joined into a single twin-state record.

---

## What is real, and what is not

This is the project's credibility, so it is stated first and repeated in the UI.

**Real — validated models and deterministic code**

| Layer | Result | Where measured |
|---|---|---|
| BSTAN bottleneck forecaster | Test RMSE **2.689** vs persistence 3.44 and moving-average 3.23; localises within ±2 stations on **65%** of bottleneck shifts (66% excluding edge stations) | measured at artifact export, `artifacts/metrics.json` |
| Defect-chain engine | **3/3** planted causal chains recovered, lifts **1.53 / 1.44 / 1.36** | measured at artifact export |
| Fine-tuned YOLOv8 detector | mAP50 **0.9098**, precision 0.9051, recall 0.8441, F1 0.8735 | read from `best.pt` itself at load time (`checkpoint_train_metrics`) |
| — same detector, notebook's figures | mAP50 0.901, precision 0.891, recall 0.826, F1 0.857 on 161 real test images | the notebook validation run, shown for comparison |

**Simulated — labelled everywhere**
The line itself: the 35-station layout, buffer sizes, per-shift process features and
the inspection history, generated with seed 42. Also `vehicle_id` / `station_id` /
`timestamp` on defect events — the defect dataset has no automotive context, so a
config layer assigns them.

**Assumed — rule-based and documented**
`CAMERA_TO_STATION`, the `visual → process` defect mapping, and every P&L cost.

> The mechanisms — detection, chaining, forecasting, gating — are real and validated.
> The factory around them is a realistic simulation, exactly as PS4 invites.

### Caveat: the detector is loaded but has no frames to inspect

`artifacts/best.pt` **is** present and verified — 20 classes matching `VISUAL_CLASSES`,
trained 50 epochs at 416 px. The loader compares its class names against the configured
list and **refuses to start** if handed a COCO or otherwise foreign model.

What is still missing are the **camera frames** for it to run on. The MVTec-derived test
images need HuggingFace, which was unreachable where this was built. So `/health` reports:

```json
"defect": { "detector_loaded": true, "state": "no_frames",
            "detail": "The fine-tuned detector is loaded and verified, but there are
                       no camera frames for it to inspect." }
```

No detections are produced, and **nothing is substituted for them**. The Quality page
shows the detector's own recorded metrics and says plainly why the gallery is empty.

**To produce detections**, add real frames and restart:

```bash
mkdir -p artifacts/sample_frames
cp /path/to/mvtec_yolo/test/images/*.png artifacts/sample_frames/
docker compose restart backend      # or restart uvicorn
```

Do **not** substitute unrelated photographs. The detector knows 20 MVTec defect classes;
on out-of-domain images it emits meaningless boxes the UI would present as real defect
detections. An empty gallery is honest; a fabricated one is not.

Set `model_config.defect.required` to `true` to make an absent detector a hard startup
failure instead of a degraded mode.

---

## Run it

**Without Docker** (verified working — this is the path that was actually run):

```bash
./scripts/run_local.sh            # builds the frontend, serves it on :4173
./scripts/run_local.sh --dev      # Vite dev server on :5173 with hot reload
./scripts/run_local.sh --backend  # backend only, on :8000
```

It creates the virtualenv, installs what is missing, checks the artifacts are present,
waits for the models to load, prints exactly what loaded, then starts the dashboard.
Ctrl-C stops both.

**With Docker** — one container (what hosted deployments use):

```bash
docker build -t cascade . && docker run -p 7860:7860 cascade    # everything on :7860
```

or two containers behind nginx:

```bash
docker compose up --build                                        # dashboard on :3000
```

**Hosted live** — see `docs/HOSTING.md`. Hugging Face Spaces is a one-command push:

```bash
./deploy/huggingface/push_to_space.sh <your-hf-username>
```

- dashboard → http://localhost:3000
- API + docs → http://localhost:8000/docs

Then press **Play** (or **Next shift**) in the top bar. The first two shifts report
*warming up*: the forecaster needs a 3-shift history window before it will predict.
That is the honest state, not a bug.

Nothing trains at startup or inside Docker. The backend loads the exported artifacts
and runs the notebooks' inference code unchanged.

### Postgres instead of SQLite

```bash
docker compose -f docker-compose.yml -f docker-compose.postgres.yml up
```

Only the connection string changes — no model, service or contract code is touched.

---

## Local development

```bash
python -m venv .venv && .venv/bin/pip install -r backend/requirements.txt
.venv/bin/uvicorn backend.main:app --reload          # :8000
cd frontend && npm install && npm run dev            # :5173, proxies to :8000
```

Tests:

```bash
.venv/bin/python -m pytest tests/ -q                 # 44 backend tests
```

---

## Regenerating the artifacts

The notebooks are the source of truth for model code. `tools/export_artifacts.py`
copies their training loop verbatim and runs it **once, offline**, to produce what
the backend loads:

```bash
.venv/bin/python tools/export_artifacts.py --out artifacts
```

It writes `bstan_seed{0,1,2}.pt`, `graph.pt`, `normalization.json`, `chains.json`,
`mappings.json`, `metrics.json` and `line_shifts.npz` (~1 MB total, ~4 minutes on
4 CPU cores). It does **not** produce `best.pt` — that needs the image dataset.

Every metric it writes carries a `source` field: `measured_at_export` for numbers it
measured, `notebook_validation_run` for the detector's, which it did not re-measure.

## Further reading

| | |
|---|---|
| `docs/HOSTING.md` | running it locally, in one container, or hosted live |
| `docs/DOCKER_DEPLOYMENT.md` | bringing the stack up with Docker, and what breaks first |
| `docs/WEBAPP_BUILD.md` | how the app was built and why each decision was made |
| `docs/DEPLOYMENT.md` | sizing, ports, volumes, startup behaviour |

---

## Architecture

```
 simulator ──[35,10] normalized features──► BOTTLENECK  (BSTAN ×3 + confidence gate)
     │                                           │
     └───────vehicle frames──► DEFECT  (YOLO ──► chain engine)
                                     │           │
                                     ▼           ▼
                            INTEGRATION · build_twin_state()
                                     │
                    ┌────────────────┼────────────────┐
                 P&L engine      SQLite store    REST + WebSocket ──► React dashboard
```

The two predictors stay separate: YOLO's classes never become BSTAN features, and the
chain engine is a distinct layer from the forecaster. They meet only at the
twin-state record.

| Path | What lives there |
|---|---|
| `backend/models/` | BSTAN, the process-flow graph and both Turning-Point variants — **copied verbatim** from the notebook |
| `backend/services/bottleneck_core.py` | the confidence gate and `LiveBottleneckMonitor` — also verbatim |
| `backend/services/` | simulator, bottleneck, defect, integration, P&L, tick engine |
| `backend/api/` | REST routes, WebSocket, Pydantic schemas mirroring the contracts |
| `backend/store/` | SQLModel tables and repository helpers |
| `backend/config/` | the loader and the shipped default configs |
| `frontend/src/` | React dashboard |
| `tools/` | the offline artifact export |

### Nothing hardcoded

Costs, thresholds, camera maps, class lists, tick cadence and model paths all live in
`config/*.json`, overridable per-key via `CASCADE_<FILE>_<KEY>` environment variables.
`pnl_config.json` and `mappings.json` hot-reload, and every change is audited.
A test greps the backend to keep it that way.

The one fixed structural fact is the **35-station topology**, loaded from `graph.pt`
because BSTAN is trained for that specific graph. It is served read-only at `GET /line`
and the dashboard renders from that payload, so no component hardcodes 35 tiles. There
is deliberately **no topology-swap endpoint** — a different line is a retraining task.

---

## API

The REST surface is served twice: at the root exactly as specified, and under `/api`
so the dashboard can share one origin with the SPA (without which `/pnl`, `/history`
and `/config` would collide with the frontend's own routes).

| | |
|---|---|
| `GET /health` | status, loaded models, metrics, provenance |
| `GET /line` | the fixed 35-station topology (read-only) |
| `GET /config` · `POST /config/pnl` · `POST /config/mappings` | effective config; audited live edits |
| `GET /twin/state` · `GET /twin/state/{vehicle_id}` | twin-state records |
| `GET /alerts` · `GET /detections` | downstream inspection alerts; YOLO detections |
| `GET /pnl` · `POST /pnl/config/reset` | projection with breakdown, sources and sensitivity |
| `GET /history` | shifts and series for the charts |
| `POST /control/{tick,play,pause,reset}` | drive the twin |
| `WS /ws/live` | `tick` and `status` frames |

## The P&L feature

```
net = bottleneck_flags × minutes_avoided × downtime_cost_per_min
    + defects_caught   × units_carrying  × scrap_cost_per_unit
    + chains_flagged   × defect_caught_value
    − inspections      × inspection_cost_per_check
    − low_confidence_acted × false_alarm_cost
```

Counts are real model outputs; every rate is a user assumption. Each response carries
a `sources` map tagging every term `model_output` or `assumption`, and the disclaimer
sits above every figure in the UI. **A missing assumption leaves its line `null` with
a `missing_config` flag — the engine never invents a value.**

Editing an assumption re-projects the whole session instantly, because the backend
recomputes from the stored per-shift counts. No model re-runs; a test asserts it.
