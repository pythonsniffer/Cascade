# Cascade — Integrated Digital Twin for Vehicle Assembly

Cascade is a 3-layer live Digital Twin for a vehicle assembly line, built for
the Accenture Innovation Challenge 2026 (Problem Statement 4: DigitalTwin.ai).
It predicts two things a shift ahead, from data a plant already has:

1. **Bottlenecks** — where the line's throughput will choke next shift.
2. **Defect chains** — which downstream defect a caught defect will trigger,
   so inspection can happen before a batch of vehicles carries the flaw forward.

The core differentiator is **"one shared graph, two predictors"** — throughput
(bottleneck) and quality (defect) prediction on a single live line model, plus
a closed loop where real outcomes feed back to improve accuracy.

**Solution approach.** Three modular layers share one graph representation of a
35-station assembly line (S0–S14 body, S15–S22 paint, S23–S34 final assembly):

| Layer | Name | What it does | Tech |
|-------|------|--------------|------|
| 1 | Sensing | Detect visible defects and derive per-station timing | Fine-tuned YOLOv8 on 1,083 real labelled images |
| 2 | Digital Model | Represent the line as a weighted graph (stations = nodes, buffers = edge weights) | BSTAN graph (Lai et al. 2023) |
| 3 | Prediction | Forecast blockage/starvation, localize the bottleneck, predict defect chains | GAT + GRU, Turning-Point Method, P(B\|A)+lift engine |

**Architecture.** A simulated input stream feeds two services (Bottleneck via
BSTAN ensemble + LiveMonitor, and Defect via fine-tuned YOLO + chain engine).
An Integration Service joins their outputs into a shared twin-state record
keyed on `vehicle_id + station_id + timestamp`. A P&L Engine turns model
outputs into projected financial impact using user-editable cost assumptions.
FastAPI serves REST + WebSocket endpoints; a React dashboard renders the live
line, alerts, defect chains, and P&L breakdown.

```text
┌──────────────────────────────────────────────────────────────────────────┐
│                          CASCADE DIGITAL TWIN                            │
│                                                                          │
│   SIMULATED INPUT STREAM                    EXPORTED MODEL ARTIFACTS     │
│   (shift/vehicle generator)                 (best.pt, bstan_*.pt, graph) │
│         │                                    │                           │
│         ▼                                    ▼                           │
│  ┌───────────────┐                  ┌──────────────────┐                 │
│  │  Line Simulator│ ───────────────► │ BOTTLENECK SERVICE│                 │
│  └───────────────┘                  │ BSTAN + monitor  │                 │
│         │                           └────────┬─────────┘                 │
│         │ vehicle frames                     │ bottleneck alert          │
│         ▼                                    │                           │
│  ┌───────────────┐                  ┌────────▼─────────┐                 │
│  │  Frame feeder  │ ───────────────► │  DEFECT SERVICE  │                 │
│  └───────────────┘                  │  YOLO + chain    │                 │
│                                     └────────┬─────────┘                 │
│                                              │ defect events             │
│                                              ▼                           │
│                                     ┌──────────────────────────┐         │
│                                     │  INTEGRATION / TWIN STATE│         │
│                                     └────────────┬─────────────┘         │
│                                                  │                       │
│               ┌──────────────────────────────────┼──────────────────┐    │
│               ▼            ▼                     ▼                  ▼    │
│          live alerts    P&L engine           persistence         history │
│               └────────────┬────────────────────────────────────────┘    │
│                            ▼                                             │
│                     FASTAPI (REST + WebSocket)                           │
│                            ▼                                             │
│                      REACT DASHBOARD                                     │
└──────────────────────────────────────────────────────────────────────────┘
```

**Key features and validated results.** Every metric below is the printed
output of a specific notebook cell — nothing is estimated or hand-tuned. The
defect detector was validated on 161 real test images spanning 20 classes from
the MVTec-derived dataset:

| Capability | Result |
|------------|--------|
| Defect detection (YOLOv8, fine-tuned) | mAP50 0.901, precision 0.891, recall 0.826, F1 0.857 on 161 real test images across 20 classes |
| Training scale | 1,083 real labelled images from the MVTec-derived dataset (cable, screw, metal-nut, transistor) |
| Defect-chain recovery | 3/3 planted causal chains recovered (lift 1.36–1.53) |
| Live defect-to-chain alerts | 8 of 21 detections raised a downstream-inspection flag |
| Bottleneck forecast (BSTAN) | Test RMSE 2.80 ± 0.03 (beats persistence 3.44 and moving-avg 3.23) |
| Bottleneck localization | ~71% within ±2 stations (excluding edge-station cases) |
| Confidence gating | Abstains on ~63% of hard bottleneck shifts and 100% of anomaly aftermath |

Additional implementation highlights:

- **Graph-native Turning-Point Method** — generalized the original serial-line
  TPM to an arbitrary directed graph using BFS with 0.85^hops distance decay.
  Correctly handles branch points (S13 bypass), merge points, rework loops
  (S20→S18), and edge stations.
- **Ensemble confidence gating** — epistemic uncertainty via variance of 3
  BSTAN models (seeds 0/1/2). If models disagree beyond the 90th percentile
  of normal-shift variance, the system abstains instead of guessing. Directly
  addresses the PS4 complexity that false alarms erode trust.
- **Unlearnable-anomaly ceiling** — deliberately injected anomalies with zero
  input signal to measure the theoretical prediction ceiling, reproducing the
  BSTAN paper's Station S8 case. The model cannot predict these events, and
  the confidence gate handles this honestly.
- **Dynamic P&L engine** — every cost/value is a user-editable assumption;
  P&L = (value from correct predictions) − (cost of false alarms +
  inspections). Every term traces to a model output or a named assumption.

**What is real vs. simulated.** The mechanisms (detection, chaining,
forecasting, gating) are real and validated. The factory around them is a
realistic simulation, exactly as PS4 invites. Specifically: the fine-tuned
YOLOv8, defect-chain engine, BSTAN forecaster, LiveBottleneckMonitor, and
shared-state join are all real. The factory layout, vehicle/station/timestamp
metadata, and inspection history are simulated. Camera-to-station mapping,
visual-to-process defect taxonomy, and P&L cost assumptions are documented
rule-based configuration.

**Business impact.** Forecasting bottlenecks a shift ahead lets teams act
before the line stalls (against $15k–$50k/min unplanned downtime in auto
manufacturing). Catching upstream defects stops propagation across batches.
Deployment is low-cost: existing OT data + a camera, no PLC rewiring. The
phased rollout follows a Shadow → Suggest → Act trust ladder across four
phases: P0 (prototype, now), P1 (single-line pilot), P2 (full dashboards),
P3 (multi-plant via transfer learning + FMEA seeding). One model serves
floor supervisors (live alerts), plant managers (trends), QA teams
(downstream-inspection flags), and leadership (P&L projections).

For the full source, visit the
[project repository](https://github.com/pythonsniffer/Cascade/tree/claude/cascade-digital-twin-6h2s6v).


## Table of contents

- Requirements
- Installation
- Configuration
- Troubleshooting
- FAQ
- Maintainers


## Requirements

### Runtime (deployed application)

- Docker and Docker Compose
- (Optional) NVIDIA GPU + NVIDIA Container Toolkit for accelerated YOLO
  inference

### ML training (Colab notebooks, if retraining)

- Google Colab with GPU runtime (T4 or better)
- Python 3.10+, PyTorch, torch_geometric, ultralytics
- HuggingFace account (free token, read scope) for MVTec dataset download

### Backend

- Python 3.11, FastAPI, Uvicorn
- PyTorch, torch_geometric, ultralytics
- SQLModel / SQLite (Postgres-ready via connection string swap)

### Frontend

- React, Vite, TypeScript, Tailwind CSS
- Recharts (charts), WebSocket (live data)


## Installation

The application is already deployed. To run a local instance:

1. Clone the repository:
   ```bash
   git clone -b claude/cascade-digital-twin-6h2s6v \
     https://github.com/pythonsniffer/Cascade.git
   cd Cascade
   ```

1. Start with Docker Compose:
   ```bash
   docker compose up -d
   ```

1. Access the application:
   - Dashboard (frontend): `http://localhost:3000`
   - API (backend): `http://localhost:8000`
   - API docs (Swagger): `http://localhost:8000/docs`

To retrain models from scratch, open the source-of-truth notebooks
(`Cascade_Integrated.ipynb`) in Google Colab with a
GPU runtime and run all cells. Exported artifacts (`.pt` weights, graph,
normalization, chains) go into the `artifacts/` directory for the backend to
load at startup — no retraining at deploy time.


## Configuration

Nothing that could vary is hardcoded. All configuration lives in JSON files
in the backend `config/` directory, editable without code changes:

- `line_config.json` — station count (35), zone boundaries, buffer sizes, tick
  cadence, vehicles per shift.
- `model_config.json` — paths to `.pt` artifacts, `T_w` (temporal window),
  `CONF_THRESHOLD`, YOLO `imgsz` and `conf`.
- `mappings.json` — `CAMERA_TO_STATION`, `VISUAL_TO_PROCESS`, `VISUAL_CLASSES`,
  `DEFECT_TYPES`.
- `chains.json` — learned chain table (trigger, downstream, P_B_given_A, lift).
- `pnl_config.json` — all cost/value assumptions: `downtime_cost_per_min`,
  `scrap_cost_per_unit`, `inspection_cost_per_check`, `defect_caught_value`,
  `false_alarm_cost`, `vehicles_per_shift`, `shifts_per_day`.

P&L assumptions can be edited live from the dashboard (`/pnl` page) via
`POST /config/pnl`. Changes re-project history instantly with no model rerun.
Every configuration change is audited (who/when/what).

The line topology is fixed at 35 stations because the BSTAN model is trained
for this specific graph. The frontend renders it from the `/line` API endpoint
— the view is data-driven even though the value is fixed. Extending to a
different line requires re-specifying nodes/edges and retraining the forecaster
(the transfer-learning roadmap item, Phase P3).


## Troubleshooting

If the bottleneck monitor shows "warming_up" for the first few shifts, this is
expected. The BSTAN model requires a temporal window of `T_w` shifts (default:
3) to fill its rolling buffer before making predictions. The system honestly
reports this state instead of guessing.

If the confidence gate abstains on a shift you expected it to flag, this means
the 3 ensemble models disagreed beyond the calibrated threshold (90th
percentile of normal-shift variance). The system is working as designed — it
trades coverage for precision. Lowering `CONF_THRESHOLD` in
`model_config.json` will flag more shifts but may increase false alarms.


## FAQ

**Q: Can I change the number of stations or line topology?**

**A:** The topology is fixed at 35 stations because the BSTAN model is trained
for this specific graph. A different line requires re-specifying nodes/edges
and retraining the forecaster. This is the transfer-learning roadmap item
(Phase P3), not a config swap.

**Q: Are the P&L numbers real savings?**
**A:** No. They are projections — real model outputs multiplied by your cost
assumptions. The dashboard always shows the mandatory disclaimer and a
breakdown tagging each number as `model_output` or `assumption`.

**Q: Why does the defect layer use MVTec images instead of real automotive
images?**
**A:** MVTec is a real, public industrial-defect dataset (1,083 labelled
images, 20 classes). We fine-tune YOLOv8 on it to prove the mechanism works.
In a real deployment (Phase P1), the same pipeline consumes real station-camera
frames — `yolo_result_to_events()` is unchanged.

**Q: What happens when the model encounters an event it cannot predict?**
**A:** We measured the unlearnable-anomaly ceiling — events with zero input
signal are provably unforecastable. The confidence gate detects these and
abstains, and the Shadow → Suggest → Act trust ladder ensures the system never
acts autonomously on uncertain predictions.


## Repository structure

```
.
├── artifacts/                      # Exported model weights and config
│   ├── best.pt                     # Fine-tuned YOLOv8 weights
│   ├── bstan_seed0.pt              # BSTAN ensemble seed 0
│   ├── bstan_seed1.pt              # BSTAN ensemble seed 1
│   ├── bstan_seed2.pt              # BSTAN ensemble seed 2
│   ├── chains.json                 # Learned defect-chain table
│   ├── graph.pt                    # Edge index, edge weights, directed graph
│   ├── line_shifts.npz             # Pre-generated shift data for replay
│   ├── mappings.json               # Class lists + visual→process + camera→station
│   ├── metrics.json                # Validated model metrics
│   ├── normalization.json          # xmin/xmax, T_w, CONF_THRESHOLD, FEATURES
│   └── sample_frames/              # Real MVTec test images (cable, metal-nut, screw, transistor)
├── backend/
│   ├── main.py                     # FastAPI app entrypoint
│   ├── api/
│   │   ├── rest.py                 # REST routes
│   │   ├── schemas.py              # Pydantic response models
│   │   ├── state.py                # Shared app state
│   │   └── ws.py                   # WebSocket live stream
│   ├── config/
│   │   ├── defaults/               # Default config JSON files
│   │   └── loader.py               # Config loader (JSON + env overrides)
│   ├── models/
│   │   ├── bstan.py                # BSTAN nn.Module (copied from notebook)
│   │   ├── graph.py                # Directed graph + turning_point_general
│   │   └── loader.py               # Reconstruct models from artifacts
│   ├── services/
│   │   ├── bottleneck.py           # LiveBottleneckMonitor wrapper
│   │   ├── bottleneck_core.py      # Core monitor logic
│   │   ├── defect.py               # YOLO inference + chain engine
│   │   ├── engine.py               # Tick loop orchestrator
│   │   ├── integration.py          # build_twin_state() join
│   │   ├── pnl.py                  # Projected P&L engine
│   │   └── simulator.py            # Line simulator (per-shift features + frames)
│   ├── store/
│   │   ├── db.py                   # SQLModel engine + session
│   │   ├── models.py               # DB tables (Shift, DefectEvent, TwinState, PnL)
│   │   └── repo.py                 # Read/write helpers
│   ├── Dockerfile
│   └── requirements.txt
├── config/                         # Runtime config (editable, not hardcoded)
│   ├── line_config.json
│   ├── mappings.json
│   ├── model_config.json
│   └── pnl_config.json
├── data/
│   └── cascade.db                  # SQLite database
├── deploy/
│   └── huggingface/                # HuggingFace Spaces deployment scripts
├── docs/
│   ├── DEPLOYMENT.md
│   ├── DOCKER_DEPLOYMENT.md
│   ├── HOSTING.md
│   └── WEBAPP_BUILD.md
├── frontend/
│   ├── src/
│   │   ├── App.tsx                 # Root React component
│   │   ├── main.tsx                # Entry point
│   │   ├── index.css               # Global styles
│   │   ├── components/             # UI components
│   │   ├── views/                  # Page-level views
│   │   ├── store/                  # State management
│   │   ├── lib/                    # API client + utilities
│   │   └── assets/                 # Static assets
│   ├── public/
│   ├── Dockerfile
│   ├── nginx.conf
│   ├── package.json
│   ├── tailwind.config.js
│   ├── vite.config.ts
│   └── tsconfig.json
├── scripts/
│   └── run_local.sh                # Local dev startup script
├── tests/
│   ├── test_api.py                 # API endpoint tests
│   ├── test_config.py              # Config loader tests
│   ├── test_contracts.py           # Data contract validation
│   ├── test_defect_layer.py        # Defect service tests
│   ├── test_packaging.py           # Build/package tests
│   ├── test_pnl.py                 # P&L engine tests
│   └── e2e_ui.py                   # End-to-end UI tests
├── tools/
│   └── export_artifacts.py         # Notebook → artifact export script
├── docker-compose.yml
├── docker-compose.postgres.yml
├── Dockerfile
└── README.md
```


## Maintainers

- Arpit 
- Arpita
- Parshv

Team teamName — IIT Roorkee
