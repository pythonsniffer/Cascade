"""
Cascade — model artifact export (Architecture & Workflow §7).

Bridges the notebooks to the backend: runs the training ONCE, OFFLINE, and writes
the artifacts the backend loads at startup. The backend never retrains; Docker never
runs this script.

Every model/graph/chain function below is COPIED VERBATIM from Cascade_Integrated.ipynb
(cells A2/A3/A4/A5/A6/A7/A9/A10 and B8). Do not "improve" them — diverging from the
notebook silently changes the validated results.

Usage:  python tools/export_artifacts.py --out artifacts
"""
import argparse, json, os
from itertools import product
from pathlib import Path

import networkx as nx
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch_geometric.nn import GATConv

# ── config (mirrors backend/config/defaults; kept here so the export is standalone) ──
CFG_DIR = Path(__file__).resolve().parents[1] / "backend" / "config" / "defaults"
LINE_CFG = json.loads((CFG_DIR / "line_config.json").read_text())
MAPPINGS = json.loads((CFG_DIR / "mappings.json").read_text())

SEED = LINE_CFG["simulator"]["seed"]
N_SHIFTS = LINE_CFG["simulator"]["n_shifts"]
BOTTLENECK_RATE = LINE_CFG["simulator"]["bottleneck_rate"]
SENSOR_POOR_FRAC = LINE_CFG["simulator"]["sensor_poor_frac"]
ANOMALY_FRAC = LINE_CFG["simulator"]["anomaly_frac"]
TRAIN_FRAC = LINE_CFG["simulator"]["train_frac"]

_Z = LINE_CFG["zones"]
ZONES = (["body"] * (_Z["body"]["end"] - _Z["body"]["start"] + 1)
         + ["paint"] * (_Z["paint"]["end"] - _Z["paint"]["start"] + 1)
         + ["final"] * (_Z["final_assembly"]["end"] - _Z["final_assembly"]["start"] + 1))
N_STATIONS = len(ZONES)
assert N_STATIONS == LINE_CFG["n_stations"]

FEATURES = ["blockage", "starvation", "downtime", "cycle_time",
            "product_mix", "production_volume", "seq_variability",
            "planned_product_mix", "planned_production_volume", "planned_seq_variability"]
TARGETS = ["blockage", "starvation"]
DEFECT_TYPES = MAPPINGS["DEFECT_TYPES"]

torch.manual_seed(0); np.random.seed(0)


# ─────────────────────── A2 · Line simulator (verbatim) ───────────────────────
def build_graph(rng):
    """Serial line; edge weight = normalized buffer size (BSTAN Eq. 3)."""
    G = nx.DiGraph()
    for i, z in enumerate(ZONES):
        G.add_node(i, zone=z, sensor_poor=bool(rng.random() < SENSOR_POOR_FRAC))
        if i > 0:
            G.add_edge(i - 1, i, buffer=int(rng.integers(2, 15)))
    buffers = [d["buffer"] for *_, d in G.edges(data=True)]
    bmin, bmax = min(buffers), max(buffers)
    for *_, d in G.edges(data=True):
        d["weight"] = (d["buffer"] - bmin) / (bmax - bmin + 1e-9)
    return G


def base_station(rng):
    return dict(blockage=max(0.0, rng.normal(5, 2)),
                starvation=max(0.0, rng.normal(5, 2)),
                downtime=max(0.0, rng.normal(2, 1)),
                cycle_time=rng.normal(60, 5))


def inject_bottleneck(shift, b, rng, intensity=1.0):
    """Degrade station b; propagate blockage upstream, starvation downstream."""
    shift[b]["downtime"] += rng.normal(40, 8) * intensity
    shift[b]["cycle_time"] += rng.normal(30, 5) * intensity
    for i in range(b):
        shift[i]["blockage"] += rng.normal(25, 6) * intensity * (0.85 ** (b - i))
    for i in range(b + 1, N_STATIONS):
        shift[i]["starvation"] += rng.normal(25, 6) * intensity * (0.85 ** (i - b))
    return shift


def simulate():
    rng = np.random.default_rng(SEED)
    G = build_graph(rng)
    rows, truth = [], []
    active_bn, bn_remaining, bn_episode_len = -1, 0, 1
    for s in range(N_SHIFTS):
        shift = {i: base_station(rng) for i in range(N_STATIONS)}
        if bn_remaining == 0 and rng.random() < BOTTLENECK_RATE / 3:
            active_bn = int(rng.integers(0, N_STATIONS))
            bn_remaining = int(rng.integers(2, 5)); bn_episode_len = bn_remaining
        bn = -1
        if bn_remaining > 0:
            frac = 1 - (bn_remaining - 1) / max(1, bn_episode_len)
            intensity = 0.4 + 0.6 * frac
            shift = inject_bottleneck(shift, active_bn, rng, intensity)
            bn = active_bn; bn_remaining -= 1
        truth.append(bn)
        mix, vol, sqv = float(rng.choice([0.4, 0.6])), int(rng.integers(80, 120)), float(abs(rng.normal(10, 3)))
        mix1, vol1, sqv1 = float(rng.choice([0.4, 0.6])), int(rng.integers(80, 120)), float(abs(rng.normal(10, 3)))
        for i, z in enumerate(ZONES):
            rows.append(dict(shift_id=s, station_id=i, zone=z,
                             is_sensor_poor=G.nodes[i]["sensor_poor"],
                             blockage=shift[i]["blockage"], starvation=shift[i]["starvation"],
                             downtime=shift[i]["downtime"], cycle_time=shift[i]["cycle_time"],
                             product_mix=mix, production_volume=vol, seq_variability=sqv,
                             planned_product_mix=mix1, planned_production_volume=vol1,
                             planned_seq_variability=sqv1))
    return pd.DataFrame(rows), G, np.array(truth)


def inject_anomalies(df):
    """A3 · Unlearnable anomaly injection (verbatim)."""
    rng_anom = np.random.default_rng(SEED + 999)
    anomaly_shifts = {}
    n_anom = max(2, int(ANOMALY_FRAC * N_SHIFTS))
    for _ in range(n_anom):
        s = int(rng_anom.integers(10, N_SHIFTS - 10))
        if s in anomaly_shifts:
            continue
        st = int(rng_anom.integers(3, N_STATIONS - 3))
        anomaly_shifts[s] = st
        mask = (df.shift_id == s) & (df.station_id == st)
        df.loc[mask, "blockage"] += rng_anom.normal(45, 5)
        df.loc[mask, "starvation"] += rng_anom.normal(40, 5)
    return anomaly_shifts


# ────────────────── A4/A5/A6 · model + graph (imported from backend) ──────────────────
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.models.bstan import BSTAN                      # noqa: E402
from backend.models.graph import build_directed_process_flow, turning_point  # noqa: E402


# ─────────────────────── A7 · tensors + normalization (verbatim) ───────────────────────
def load_tensors(df, G, train_frac=TRAIN_FRAC):
    """Build [S,N,F] features and [S,N,2] targets.
    NORMALIZATION IS FIT ON TRAINING SHIFTS ONLY (no test leakage).
    """
    N, S = df.station_id.nunique(), df.shift_id.nunique()
    X = np.stack([df[df.shift_id == s].sort_values("station_id")[FEATURES].values for s in range(S)])
    tgt = np.stack([df[df.shift_id == s].sort_values("station_id")[TARGETS].values for s in range(S)])
    n_train = int(S * train_frac)
    xmin = X[:n_train].min((0, 1)); xmax = X[:n_train].max((0, 1))
    Xn = (X - xmin) / (xmax - xmin + 1e-9)
    ei = [[u, v] for u, v in G.edges()]; ew = [G[u][v]["weight"] for u, v in G.edges()]
    ei = ei + [[b, a] for a, b in ei]; ew = ew + ew
    edge_index = torch.tensor(ei, dtype=torch.long).t().contiguous()
    edge_weight = torch.tensor(ew, dtype=torch.float).unsqueeze(1)
    return (torch.tensor(Xn, dtype=torch.float), torch.tensor(tgt, dtype=torch.float),
            edge_index, edge_weight, N, S, xmin, xmax)


# ─────────────────────── B8 · defect-chain engine (verbatim) ───────────────────────
TRUE_CHAINS = {("weld_gap", "misalign"): 0.75,
               ("paint_run", "seal_fail"): 0.65,
               ("torque_low", "rattle"): 0.60}
BASE_RATE = 0.006
N_VEHICLES = 5000


def simulate_inspection_history(stations):
    """Per-vehicle inspection logs with planted causal chains + background noise."""
    rng_d = np.random.default_rng(7)
    rows = []
    for v in range(N_VEHICLES):
        found = []
        for st in stations:
            for dt in DEFECT_TYPES:
                if rng_d.random() < BASE_RATE:
                    found.append((st, dt))
        for (a, b), p in TRUE_CHAINS.items():
            a_stations = [st for st, dt in found if dt == a]
            if a_stations and rng_d.random() < p:
                ds = min(a_stations) + int(rng_d.integers(3, 9))
                if ds <= max(stations):
                    found.append((ds, b))
        for st, dt in found:
            rows.append(dict(vehicle_id=v, station_id=st, defect_type=dt))
    return pd.DataFrame(rows)


def learn_chains(defects):
    """Recover directional chains P(B downstream | A upstream) with lift."""
    first_st = (defects.groupby(["vehicle_id", "defect_type"])["station_id"].min().unstack())
    p = {d: (first_st[d].notna().mean() if d in first_st else 0.0) for d in DEFECT_TYPES}
    out = []
    for a, b in product(DEFECT_TYPES, DEFECT_TYPES):
        if a == b or a not in first_st or b not in first_st:
            continue
        if p[a] == 0:
            continue
        directional = (first_st[a].notna() & first_st[b].notna() & (first_st[a] < first_st[b]))
        p_ab = directional.mean()
        p_b_given_a = p_ab / p[a]
        lift = p_b_given_a / p[b] if p[b] > 0 else 0.0
        out.append(dict(trigger=a, downstream=b,
                        P_B_given_A=round(p_b_given_a, 3), lift=round(lift, 2)))
    chains = pd.DataFrame(out)
    return chains[chains.lift > 1].sort_values("lift", ascending=False).reset_index(drop=True)


# ─────────────────────── A9 · training (verbatim loss + loop) ───────────────────────
def train_variant(X, Y, edge_index, edge_weight, train_idx, T_w, N, seed, epochs):
    torch.manual_seed(seed); np.random.seed(seed)
    m = BSTAN(in_dim=len(FEATURES), n_stations=N)
    opt = torch.optim.Adam(m.parameters(), lr=0.005)

    def loss_on(t):
        p = m(X[t - T_w:t], edge_index, edge_weight)
        with torch.no_grad():
            dev = (Y[t] - Y[t].median(0, keepdim=True).values).abs()
            w = 1 + 3 * (dev / (dev.max() + 1e-6))
        return (w * (p - Y[t]) ** 2).mean()

    for ep in range(epochs):
        m.train()
        order = np.random.permutation(train_idx)
        for k in range(0, len(order), 8):
            opt.zero_grad()
            torch.stack([loss_on(int(t)) for t in order[k:k + 8]]).mean().backward()
            opt.step()
        if ep % 10 == 0:
            print(f"    seed {seed} epoch {ep}/{epochs}", flush=True)
    m.eval()
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="artifacts")
    ap.add_argument("--epochs", type=int, default=60, help="notebook agg() uses 60")
    ap.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 2])
    ap.add_argument("--t-w", type=int, default=3)
    args = ap.parse_args()
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)

    print("[1/6] simulating line (seed %d) ..." % SEED, flush=True)
    df, G, truth = simulate()
    anomaly_shifts = inject_anomalies(df)
    print(f"      {N_STATIONS} stations, {N_SHIFTS} shifts, "
          f"{(truth >= 0).sum()} bottleneck shifts, {len(anomaly_shifts)} anomalies")

    X, Y, edge_index, edge_weight, N, S, xmin, xmax = load_tensors(df, G)
    G_dir = build_directed_process_flow(G)
    T_w = args.t_w
    idx = list(range(T_w, S)); split = int(len(idx) * 0.6)
    train_idx, test_idx = idx[:split], idx[split:]
    print(f"      X{tuple(X.shape)} edges={edge_index.shape[1]} "
          f"train={len(train_idx)} test={len(test_idx)}")

    print(f"[2/6] training BSTAN ensemble, seeds={args.seeds}, epochs={args.epochs} ...", flush=True)
    ensemble = []
    for s in args.seeds:
        m = train_variant(X, Y, edge_index, edge_weight, train_idx, T_w, N, s, args.epochs)
        torch.save(m.state_dict(), out / f"bstan_seed{s}.pt")
        ensemble.append(m)
        print(f"    -> wrote bstan_seed{s}.pt", flush=True)

    # ── A10 · calibrate confidence threshold on NORMAL test shifts (verbatim logic) ──
    print("[3/6] calibrating confidence gate ...", flush=True)
    from backend.services.bottleneck_core import forecast_with_confidence
    normal_test = [t for t in test_idx if truth[t] < 0 and t not in anomaly_shifts]
    variances = [forecast_with_confidence(ensemble, X[t - T_w:t], edge_index, edge_weight,
                                          threshold=np.inf)[2] for t in normal_test]
    conf_threshold = float(np.percentile(variances, 90))
    print(f"      CONF_THRESHOLD = {conf_threshold:.6f} (90th pct of {len(normal_test)} normal shifts)")

    # ── honest evaluation of THIS exported ensemble ──
    print("[4/6] evaluating exported ensemble ...", flush=True)
    rmses, hits, nbn, hits_ne, nbn_ne = [], 0, 0, 0, 0
    for t in test_idx:
        mp, _, _ = forecast_with_confidence(ensemble, X[t - T_w:t], edge_index, edge_weight, np.inf)
        rmses.append(float(np.sqrt(((mp - Y[t].numpy()) ** 2).mean())))
        if truth[t] >= 0:
            loc = turning_point(mp[:, 0], mp[:, 1])
            nbn += 1; hits += abs(loc - truth[t]) <= 2
            if not (truth[t] <= 1 or truth[t] >= N - 2):
                nbn_ne += 1; hits_ne += abs(loc - truth[t]) <= 2
    persistence_rmse = float(np.mean([np.sqrt(((Y[t - 1].numpy() - Y[t].numpy()) ** 2).mean()) for t in test_idx]))
    movavg_rmse = float(np.mean([np.sqrt(((Y[t - T_w:t].mean(0).numpy() - Y[t].numpy()) ** 2).mean()) for t in test_idx]))
    metrics = {
        "bottleneck": {
            "test_rmse": round(float(np.mean(rmses)), 3),
            "localization_within_2_all": round(hits / max(1, nbn), 3),
            "localization_within_2_no_edge": round(hits_ne / max(1, nbn_ne), 3),
            "n_bottleneck_test_shifts": int(nbn),
            "baseline_persistence_rmse": round(persistence_rmse, 3),
            "baseline_moving_avg_rmse": round(movavg_rmse, 3),
            "source": "measured_at_export",
        },
        "detector": {
            "mAP50": 0.901, "precision": 0.891, "recall": 0.826, "f1": 0.857,
            "test_images": 161, "train_images": 1083,
            "source": "notebook_validation_run",
            "note": "Measured in Cascade_DefectLayer/Cascade_Integrated on the MVTec-derived "
                    "test split. Not re-measured at export (dataset not bundled).",
        },
        "chains": {"source": "measured_at_export"},
    }
    print(f"      RMSE {metrics['bottleneck']['test_rmse']} | "
          f"loc {metrics['bottleneck']['localization_within_2_all']:.0%} all / "
          f"{metrics['bottleneck']['localization_within_2_no_edge']:.0%} no-edge | "
          f"baselines {persistence_rmse:.2f}/{movavg_rmse:.2f}")

    print("[5/6] learning defect chains ...", flush=True)
    history = simulate_inspection_history(list(range(N_STATIONS)))
    learned = learn_chains(history)
    recovered = set(zip(learned.trigger, learned.downstream)) & set(TRUE_CHAINS.keys())
    metrics["chains"].update({
        "planted": len(TRUE_CHAINS), "recovered": len(recovered),
        "recovered_pairs": [f"{a}->{b}" for a, b in sorted(recovered)],
        "history_vehicles": N_VEHICLES, "history_records": int(len(history)),
    })
    print(f"      recovered {len(recovered)}/{len(TRUE_CHAINS)} planted chains, "
          f"{len(learned)} associations with lift>1")

    print("[6/6] writing artifacts ...", flush=True)
    torch.save({
        "edge_index": edge_index, "edge_weight": edge_weight,
        "G_dir": nx.node_link_data(G_dir, edges="edges"),
        "G": nx.node_link_data(G, edges="edges"),
        "zones": ZONES, "n_stations": N_STATIONS,
    }, out / "graph.pt")
    (out / "normalization.json").write_text(json.dumps({
        "xmin": [float(v) for v in xmin], "xmax": [float(v) for v in xmax],
        "T_w": T_w, "CONF_THRESHOLD": conf_threshold, "FEATURES": FEATURES,
        "TARGETS": TARGETS, "train_frac": TRAIN_FRAC, "seeds": args.seeds,
        "epochs": args.epochs,
    }, indent=2))
    (out / "chains.json").write_text(learned.to_json(orient="records", indent=2))
    (out / "mappings.json").write_text(json.dumps(MAPPINGS, indent=2))
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2))
    # shift-level ground truth + normalized features, so the backend can REPLAY the exact
    # simulated line without re-running the simulator (replay mode).
    np.savez_compressed(out / "line_shifts.npz", X=X.numpy(), Y=Y.numpy(), truth=truth,
                        anomaly_shifts=np.array(sorted(anomaly_shifts.items())).reshape(-1, 2))
    print("done ->", out.resolve())
    for f in sorted(out.iterdir()):
        print(f"   {f.name:24s} {f.stat().st_size/1024:9.1f} KB")


if __name__ == "__main__":
    main()
