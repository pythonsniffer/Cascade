# How the Cascade web app was built

A record of what was built, in what order, and **why** each non-obvious decision was
made — enough for someone else to extend it without re-deriving the reasoning, or to
challenge a choice knowing what it was weighed against.

---

## 1. Sources of truth

Three specification files and `Cascade_Integrated.ipynb`. The notebook owns all model
code; the specs own architecture, API surface, and visual language. Where they were
explicit, they were followed rather than reinterpreted.

**What was copied verbatim, and why.** `BSTAN`, `build_directed_process_flow`,
`turning_point`, `turning_point_general`, `forecast_with_confidence`,
`LiveBottleneckMonitor`, `predict_chain`, `build_twin_state`. Reimplementing any of them
would silently invalidate the validated results — the exported `state_dict`s are fitted to
exactly that architecture. These files carry a header saying so.

The only permitted deviations: `station_zone()` reads zone boundaries from config instead
of hardcoded `<= 14` / `<= 22`, and `yolo_result_to_events` reads the two mappings from
config instead of module globals. Both preserve behaviour; both were required by the
"nothing hardcoded" rule.

## 2. The artifact problem, and how it was resolved

The repository was empty — no `best.pt`, no BSTAN checkpoints, no `graph.pt`. The specs
assume artifacts already exported (Architecture §7).

`tools/export_artifacts.py` is that missing bridge: it copies the notebook's simulator,
anomaly injection, tensor construction and training loop verbatim, runs them **once,
offline**, and writes what the backend loads. It is never invoked at startup or in Docker.

**How we know the copy is faithful** — the export reproduces the notebook's own numbers:

| | exported here | notebook / spec |
|---|---|---|
| persistence baseline RMSE | 3.44 | 3.44 |
| moving-average baseline RMSE | 3.23 | 3.23 |
| chain lifts | 1.53 / 1.44 / 1.36 | "1.36–1.53" |
| planted chains recovered | 3/3 | 3/3 |
| BSTAN test RMSE | 2.689 | ~2.80 |

The baselines are deterministic given seed 42, so matching them exactly confirms the
simulator is bit-identical. BSTAN differs slightly because weights are re-trained.

**One honest divergence.** Localization came out 66% excluding edge stations vs the spec's
~71%. The notebook averages per-seed accuracy across three seeds; this evaluates the
*ensemble mean* — what the monitor actually serves. Different methodology, so the measured
number is reported rather than the spec's.

Every metric carries a `source` field: `measured_at_export`, `notebook_validation_run`, or
`checkpoint_train_metrics`. Nothing is typed into source code.

## 3. Backend

FastAPI + SQLModel. Layering follows the spec exactly: config loader → model loader →
services → tick engine → API.

**Config loader first, deliberately.** Everything else reads from `Settings`, so no module
ever holds a literal. Env overrides are `CASCADE_<FILE>_<KEY>`; `pnl_config` and
`mappings` hot-reload. It **fails fast** on a missing artifact, a zone map that does not
cover every station, or a camera pointed off the line — a half-loaded twin that silently
serves wrong numbers is worse than one that refuses to start.

**The detector is optional-by-config.** Absent weights do not crash the backend; the layer
reports itself off and emits nothing. But a *wrong* model is fatal: the loader compares
YOLO's class names against `VISUAL_CLASSES` and refuses a COCO model outright. Silently
serving COCO as a defect detector was the single worst failure available.

**Three states, not two.** Once `best.pt` arrived, "detector loaded but no frames to
inspect" turned out to be a genuinely different situation from "no detector", and
reporting both as "camera layer off" was misleading. The service now reports
`no_detector` / `no_frames` / `ready` with a plain sentence, and every surface renders it.

**P&L sourcing.** Each line traces to a count (model output) and named rates (assumptions),
returned in a `sources` map. A missing assumption yields `null` plus a `missing_config`
flag — never an invented value. Cumulative is recomputed from **stored per-shift counts**,
which is what lets an assumption edit re-project history instantly without re-running any
model. A test asserts the detector's call count does not move across an edit.

## 4. Frontend

React + Vite + TypeScript + Tailwind, Recharts, one WebSocket into a Zustand store.

The spec pinned the Velluto language precisely, so it was followed, not reinterpreted:
light monochrome canvas, near-black text, and a single orange **reserved for meaning
only** — live dot, predicted bottleneck, alert severity, assumption tags. Because orange
is rare, the eye goes where the model is pointing.

Design judgment was spent only where the spec left room:

- **Type.** Archivo light for large calm headings, Inter for body, IBM Plex Mono for
  station IDs, lifts and metrics — the CAD/engineering register the blueprint calls for.
  Tabular numerics wherever figures are compared down a column. Fonts are bundled via
  `@fontsource`, not fetched at runtime, so Docker needs no external network.
- **The floor.** The signature element: an isometric SVG schematic generated entirely
  from `/line` — zone aisles, hairline edges weighted by buffer size, and the S13→S15
  bypass and S20→S18 rework loop drawn as labelled arcs. Captioned "not a scan of a
  physical plant", because the spec's honest-rendering note forbids implying a 3D scan.

**Honesty is in the components, not a banner.** The provenance strip reads `/health`; the
P&L disclaimer sits above every figure; warming-up and abstained say so instead of naming
a station; an empty detection list states it is not a zero-defect claim; and with no
detector the Quality page **withholds its published metrics** rather than showing numbers
the instance cannot stand behind.

## 5. Bugs found by testing

Every one of these was found by running the thing, not by reading it.

| Bug | Cause | Fix |
|---|---|---|
| Deep link to `/pnl` returned JSON | SPA routes collide with API paths of the same name | also mount the API under `/api`; SPA uses that |
| `DetachedInstanceError` from repo reads | `session_scope` committed with default `expire_on_commit` | `expire_on_commit=False` |
| "no forecast yet" on every station after reload | boot seeded from twin-states, which carry no per-station arrays | seed from `last_tick` |
| 13 bottleneck flags displayed as "1 × your rate" | cumulative amount labelled with the latest shift's count | API returns `cumulative_counts` |
| Cumulative chart drew over itself | plotted against `shift_id`, which repeats after a reset | plot against position |
| Floor was an unreadable jumble | three zone rows overlapped on the isometric diagonal | aisles of ≤8 separated along the depth axis |
| Zoom threw the drawing off-screen | SVG transforms ignore CSS `transform-origin` | scale about the computed content centre |

**A false pass worth remembering.** The first smoke test reported `/pnl` as rendering
fine. Chromium renders raw JSON in a built-in viewer, which has text content and looked
like a page. Asserting "the body has text" was too weak an assertion to catch a completely
broken route. The check now verifies the served content type.

## 6. Testing

- **44 backend tests** (`tests/`) — offline, seconds. Contracts (the `[35,10]` feature
  order, monitor output keys, twin-state shape), honesty rules (warming-up never names a
  station; a missing P&L field yields `null`), the P&L formula term by term, the real
  detector's inference path, and a grep asserting no hardcoded costs, class lists, camera
  maps or model paths — plus that the forbidden topology-swap route does not exist.
- **33 browser checks** (`tests/e2e_ui.py`) — needs two live servers and a browser, so it
  is deliberately outside the pytest run. Navigation, 35 markers from `/line`, station
  interaction, live WebSocket ticks, play/pause, the P&L edit loop, charts, detector
  honesty states, config editing with audit, the backend-down error state, three viewports.

Tests assert *shape and honesty*, not model outputs. The one test that runs the real
detector on an arbitrary photograph asserts only that events are well-formed — whatever
it detects there is meaningless, so nothing about content is claimed, and that image is
never used as a demo frame.

## 7. Deployment

Backend image loads artifacts read-only. Frontend is nginx serving the Vite build and
reverse-proxying `/api/` and `/frames/`, with the WebSocket upgrade wired through and an
SPA fallback. `docker compose up --build` starts everything.

**The Docker images were never built** — Docker Hub's blob CDN was blocked. Compose files
validate and the routing contract was checked against the running backend, but the build
is unverified. See `docs/DOCKER_DEPLOYMENT.md`.

What *was* verified instead: the production bundle served via `vite preview` with the same
routing nginx provides, passing all 33 browser checks including the deep-link behaviour.

## 8. If you extend this

- **Adding a metric?** It goes in an artifact with a `source` field, never in source code.
- **Adding a config value?** `backend/config/defaults/`, read through `Settings`. A test
  greps for literals.
- **Changing model code?** Read the notebook cell that owns it first. Files marked copied
  verbatim should not drift.
- **Adding a UI number?** It comes from the API. And if the backing model is not running,
  the UI must say so rather than showing a stale or borrowed figure.
- **Replacing the simulator with real data?** The `[35,10]` contract is unchanged — that
  is the whole point of the seam. Same for real cameras: `yolo_result_to_events` does not
  change.
