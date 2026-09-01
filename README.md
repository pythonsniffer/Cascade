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
| Fine-tuned YOLOv8 detector | mAP50 0.901, precision 0.891, recall 0.826, F1 0.857 on 161 real test images | the notebook validation run — **see the caveat below** |

**Simulated — labelled everywhere**
The line itself: the 35-station layout, buffer sizes, per-shift process features and
the inspection history, generated with seed 42. Also `vehicle_id` / `station_id` /
`timestamp` on defect events — the defect dataset has no automotive context, so a
config layer assigns them.

**Assumed — rule-based and documented**
`CAMERA_TO_STATION`, the `visual → process` defect mapping, and every P&L cost.

> The mechanisms — detection, chaining, forecasting, gating — are real and validated.
> The factory around them is a realistic simulation, exactly as PS4 invites.

### Caveat: the detector artifact is not in this repository

`artifacts/best.pt` is **absent**. Producing it needs the MVTec-derived dataset from
HuggingFace plus a GPU, neither of which was available where this was built.

The consequence is enforced honestly rather than papered over:

- the backend reports `models.defect.detector_loaded: false` on `/health`;
- the defect layer emits **no events at all** — nothing is simulated in its place;
- the UI says "camera layer off" and the Quality page **withholds the detector's
  published metrics**, because this instance is not running it and cannot stand
  behind them.

**To switch the layer on**, drop the fine-tuned weights in and restart:

```bash
cp /path/to/best.pt artifacts/best.pt
cp -r /path/to/test/images artifacts/sample_frames   # real frames for the gallery
docker compose restart backend
```

The loader asserts the weights are the fine-tuned Cascade detector by comparing its
class names against the configured `VISUAL_CLASSES`, and **refuses to start** if
handed a COCO or otherwise foreign model. Set `model_config.defect.required` to
`true` to make an absent detector a hard startup failure instead of a degraded mode.

---

## Run it

```bash
docker compose up --build
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
.venv/bin/python -m pytest tests/ -q                 # 41 backend tests
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
