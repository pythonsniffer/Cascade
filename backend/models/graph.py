"""Directed process-flow graph + Turning Point Method.

COPIED VERBATIM from Cascade_Integrated.ipynb cells A4 (turning_point),
A5 (build_directed_process_flow) and A6 (turning_point_general). Do not modify.
"""
import networkx as nx
import numpy as np


# ─── A5 · Directed Process-Flow Graph ────────────────────────────────────
def build_directed_process_flow(G_undirected):
    """Build a directed graph encoding material flow direction.

    Returns a nx.DiGraph with:
      - Serial edges:  lower_index → higher_index
      - Branch at S13: succs = {S14, S15}  (parallel bypass)
      - Merge at S15:  preds = {S14, S13}
      - Loop S20→S18:  paint rework cycle 18→19→20→18
    """
    G_dir = nx.DiGraph()

    for i, data in G_undirected.nodes(data=True):
        G_dir.add_node(i, **data)

    for u, v, data in G_undirected.edges(data=True):
        src, dst = (u, v) if u < v else (v, u)
        G_dir.add_edge(src, dst, **data)

    bypass_wt = 0.5 * (G_undirected[13][14]["weight"] + G_undirected[14][15]["weight"])
    bypass_buf = int(0.5 * (G_undirected[13][14]["buffer"] + G_undirected[14][15]["buffer"]))
    G_dir.add_edge(13, 15, buffer=bypass_buf, weight=bypass_wt)

    G_dir.add_edge(20, 18,
                   buffer=G_undirected[18][19]["buffer"],
                   weight=G_undirected[18][19]["weight"])

    return G_dir


# ─── A4 · Turning Point Method (serial form, used for evaluation) ────────
def turning_point(blk, stv):
    """Turning Point Method with endpoint handling — paper Eq. 14-19."""
    n = len(blk)
    d = blk - stv                       # TB - TS per station
    scores = np.full(n, -np.inf)

    if n >= 2:
        scores[0] = d[0] + (-d[1])          # Eq 18
        scores[n - 1] = d[n - 2] + (-d[n - 1])  # Eq 19

    for j in range(1, n - 1):               # Eq 14-17: interior
        up_blocked = np.mean(d[:j])
        down_starved = -np.mean(d[j + 1:])
        crossover = d[j - 1] - d[j + 1]
        scores[j] = up_blocked + down_starved + 0.5 * crossover

    return int(np.argmax(scores))


# ─── A6 · Graph-Native Turning Point Method ─────────────────────────────
def _weighted_bfs(G_dir, start, direction, max_hops, values):
    """BFS upstream or downstream with exponential distance decay."""
    visited = {start}
    frontier = [start]
    total_w, total_v = 0.0, 0.0

    for hop in range(1, max_hops + 1):
        decay = 0.85 ** hop
        next_frontier = []
        for node in frontier:
            nbrs = (list(G_dir.predecessors(node)) if direction == "up"
                    else list(G_dir.successors(node)))
            for nbr in nbrs:
                if nbr not in visited and 0 <= nbr < len(values):
                    visited.add(nbr)
                    total_w += decay
                    total_v += decay * values[nbr]
                    next_frontier.append(nbr)
        frontier = next_frontier
        if not frontier:
            break

    return total_w, total_v


def turning_point_general(G_dir, blk, stv, max_hops=12):
    """Graph-native Turning Point Method for arbitrary topology."""
    N = len(blk)
    diff = blk - stv
    scores = np.full(N, -np.inf)

    for j in range(N):
        up_w, up_v = _weighted_bfs(G_dir, j, "up", max_hops, diff)
        up_score = (up_v / up_w) if up_w > 0 else 0.0

        dn_w, dn_v = _weighted_bfs(G_dir, j, "down", max_hops, diff)
        dn_score = -(dn_v / dn_w) if dn_w > 0 else 0.0

        preds = [p for p in G_dir.predecessors(j) if 0 <= p < N]
        succs = [s for s in G_dir.successors(j) if 0 <= s < N]

        if preds and succs:
            cross = np.mean([diff[p] for p in preds]) - np.mean([diff[s] for s in succs])
        elif succs:
            cross = diff[j] - np.mean([diff[s] for s in succs])
        elif preds:
            cross = np.mean([diff[p] for p in preds]) - diff[j]
        else:
            cross = 0.0

        scores[j] = up_score + dn_score + 0.5 * max(cross, 0.0)

    return int(np.argmax(scores))
