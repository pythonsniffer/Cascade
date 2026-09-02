# Hosting Cascade live

Three ways to run it, in increasing order of setup. All three run the same application
and the same models.

| | Command | Serves |
|---|---|---|
| No Docker | `./scripts/run_local.sh` | backend :8000 + dashboard :4173 |
| Docker, one container | `docker build -t cascade . && docker run -p 7860:7860 cascade` | everything on :7860 |
| Docker Compose, two containers | `docker compose up --build` | nginx :3000 → backend :8000 |

The single-container image is the one to use for a hosted deployment: most platforms give
you one container and one port.

---

## Hugging Face Spaces

The best fit for this project — free, no credit card, Docker-native, and 16 GB RAM / 2 vCPU
on the free CPU tier, which comfortably fits torch plus the YOLO detector.

```bash
pip install -U "huggingface_hub[cli]"
hf auth login                                    # token needs WRITE scope
./deploy/huggingface/push_to_space.sh <your-hf-username>
```

That creates the Space, swaps `deploy/huggingface/README.md` in as the Space card (your
GitHub README is untouched), and pushes. The build takes **10–25 minutes** the first time
— it is installing torch and ultralytics. Watch the *Logs* tab.

When it finishes the dashboard is at `https://<username>-cascade-digital-twin.hf.space`.

**Things to know**

- The Space card must stay at the top of the Space's `README.md`, with `sdk: docker` and
  `app_port: 7860`. The push script handles this; if you push by hand, do not lose it.
- Spaces run the container as a non-root user. The Dockerfile already `chmod`s
  `/app/config` and `/app/data`, which the app writes to at runtime.
- **Storage is ephemeral.** The SQLite database and any live config edits are lost when the
  Space restarts or sleeps. That is fine for a demo — the twin regenerates its session from
  the first tick. For persistence, attach a Space volume and point `CASCADE_DATA_DIR` at it.
- Free Spaces sleep after inactivity and take ~30 s to wake. Press Play again after a wake.
- The repo carries ~170 MB of detector frames, so the first push is slow.

## Any other single-container host

The same image works on Fly.io, Railway, Render, Cloud Run or a plain VM. Two requirements:

- **Bind the platform's port.** The image reads `PORT` (default 7860) — set it if the
  platform assigns one.
- **Give it enough memory.** torch plus the YOLO detector needs roughly **2 GB**. Render's
  512 MB free tier will OOM; this is the most common hosting failure.

```bash
docker run -p 8080:8080 -e PORT=8080 cascade
```

`GET /healthz` is the liveness probe — it answers before the models finish loading, so set
a start period of at least 120 s on any healthcheck.

## Environment variables

| | |
|---|---|
| `PORT` | port to bind (default 7860) |
| `CASCADE_FRONTEND_DIST` | path to the built dashboard. **Set it and the app serves the SPA and moves the API under `/api`**; leave it unset and the app is API-only with routes at the root |
| `CASCADE_ARTIFACTS_DIR` | model artifacts (default `/app/artifacts`) |
| `CASCADE_CONFIG_DIR` · `CASCADE_DATA_DIR` | writable runtime dirs |
| `CASCADE_DATABASE_URL` | SQLite by default; `postgresql+psycopg://…` to switch |
| `CASCADE_<FILE>_<KEY>` | override any single config value, e.g. `CASCADE_PNL_CONFIG_DOWNTIME_COST_PER_MIN=1200` |

## Why the API is served twice

The dashboard's own routes — `/pnl`, `/history`, `/config` — share names with API
endpoints. Serving both at the root meant a page reload returned JSON instead of the app.

So the API is mounted at `/api`, which is what the dashboard calls. The root-level routes
from the spec are also registered, but **only when this process is not serving the SPA** —
otherwise they would shadow the dashboard's own pages. `CASCADE_FRONTEND_DIST` is what
decides. A test asserts both shapes behave correctly.
