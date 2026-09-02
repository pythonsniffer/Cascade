# Deployment notes

## What was verified, and what was not

Built and tested in an environment whose network policy allowed package registries
(PyPI, npm) but blocked content CDNs. That shaped what could be executed here:

| | Status |
|---|---|
| Backend, frontend, integration, 41 unit tests, 33 browser checks | **run and passing** |
| Production bundle served with SPA fallback + `/api` routing | **run and passing** (`npm run preview`) |
| `docker compose config` (both the base and the Postgres overlay) | **validated** |
| `docker compose build` / `up` | **not run here** — Docker Hub's blob CDN returns 403 under this network policy, so base images could not be pulled |

The Docker setup is therefore reviewed and statically validated but has not been
executed. Run `docker compose up --build` on a machine with normal registry access.
Expect the backend image to take several minutes on its first build: `torch` and
`ultralytics` are large.

## Sizing

- backend image: roughly 2.5–3 GB, dominated by torch + ultralytics
- frontend image: roughly 60 MB (nginx + the built bundle)
- artifacts: about 1 MB total

To shrink the backend materially, install the CPU-only torch wheel from
`https://download.pytorch.org/whl/cpu` in the Dockerfile. It is not the default here
because that host is unreachable under some network policies, including the one this
was built under.

## Ports

| Service | Container | Host | Override |
|---|---|---|---|
| frontend (nginx) | 80 | 3000 | `FRONTEND_PORT` |
| backend (uvicorn) | 8000 | 8000 | `BACKEND_PORT` |

The frontend serves the app and reverse-proxies `/api/` and `/frames/` to the
backend, so a browser only needs port 3000. Port 8000 is published for direct API
access and `/docs`.

## Volumes

| Mount | Mode | Why |
|---|---|---|
| `./artifacts → /app/artifacts` | read-only | exported models; the backend must never write here |
| `cascade-config → /app/config` | read-write | editable config, including the P&L assumptions the dashboard edits live |
| `cascade-data → /app/data` | read-write | the SQLite database |

`config` is a named volume so live edits survive a restart. It is seeded from
`backend/config/defaults/` on first boot. To reset every assumption, remove the
volume: `docker compose down -v`.

## Startup behaviour

The backend validates on boot and **fails fast with a specific message** rather than
starting half-loaded — a missing artifact, a zone map that does not cover every
station, a mapping that references an unknown class, or a camera pointed outside the
line. The healthcheck allows a 90-second start period because loading torch and the
BSTAN ensemble is not instant.

The frontend waits for `service_healthy` on the backend, so it never serves a page
that would immediately fail its first fetch.

## Switching to Postgres

```bash
docker compose -f docker-compose.yml -f docker-compose.postgres.yml up
```

Only `CASCADE_DATABASE_URL` changes. SQLModel creates the same tables; no model,
service or contract code is touched. The two compose files are kept separate so the
default demo path stays a single `docker compose up`.

## Enabling the defect layer

The detector weights are not in this repository (see the README caveat). To turn the
camera layer on:

```bash
cp best.pt artifacts/best.pt
cp -r path/to/test/images/. artifacts/sample_frames/
docker compose restart backend
```

`/health` should then report `models.defect.detector_loaded: true`, the Quality page
shows its metrics, and chain alerts start arriving in the live rail. If the weights
are not the fine-tuned Cascade detector, startup fails with an explicit message
rather than serving a COCO model as a defect detector.

To make an absent detector a hard failure instead of a degraded mode, set
`model_config.defect.required` to `true`.
