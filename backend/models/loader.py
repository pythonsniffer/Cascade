"""Model loader — reconstruct the notebook's models from exported artifacts.

Backend Instructions §4. Loads only; NEVER trains (Architecture §7).
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

import networkx as nx
import numpy as np
import pandas as pd
import torch

from backend.config.loader import ConfigError, Settings
from backend.models.bstan import BSTAN
from backend.services.bottleneck_core import LiveBottleneckMonitor

log = logging.getLogger("cascade.models")


@dataclass
class BottleneckBundle:
    ensemble: list
    edge_index: torch.Tensor
    edge_weight: torch.Tensor
    G_dir: nx.DiGraph
    G: nx.DiGraph
    T_w: int
    conf_threshold: float
    xmin: np.ndarray
    xmax: np.ndarray
    features: list[str]
    zones: list[str]
    n_stations: int
    monitor: LiveBottleneckMonitor


@dataclass
class DefectBundle:
    yolo: object | None
    yolo_path: Path
    yolo_loaded: bool
    yolo_error: str | None
    visual_classes: list[str]
    visual_to_process: dict
    camera_to_station: dict
    learned_chains: pd.DataFrame
    sample_frames: list[Path] = field(default_factory=list)


def load_bottleneck(settings: Settings) -> BottleneckBundle:
    """Reconstruct BSTAN×3 + monitor from artifacts. §4."""
    bcfg = settings.model["bottleneck"]

    graph_blob = torch.load(settings.artifact(bcfg["graph"]), weights_only=False)
    edge_index = graph_blob["edge_index"]
    edge_weight = graph_blob["edge_weight"]
    G_dir = nx.node_link_graph(graph_blob["G_dir"], directed=True, edges="edges")
    G = nx.node_link_graph(graph_blob["G"], directed=True, edges="edges")
    zones = list(graph_blob["zones"])
    n_stations = int(graph_blob["n_stations"])

    if n_stations != settings.n_stations:
        raise ConfigError(
            f"graph.pt has {n_stations} stations but line_config says {settings.n_stations}. "
            f"Topology is fixed and comes from the artifact — align the config.")

    norm = json.loads(settings.artifact(bcfg["normalization"]).read_text())
    features = list(norm["FEATURES"])
    T_w = int(norm["T_w"])
    conf_threshold = float(norm["CONF_THRESHOLD"])
    xmin = np.array(norm["xmin"], dtype=np.float64)
    xmax = np.array(norm["xmax"], dtype=np.float64)

    ensemble = []
    for wname in bcfg["bstan_weights"]:
        m = BSTAN(in_dim=len(features), n_stations=n_stations,
                  gat_hidden=int(bcfg["gat_hidden"]), gru_hidden=int(bcfg["gru_hidden"]),
                  heads=int(bcfg["heads"]))
        state = torch.load(settings.artifact(wname), map_location="cpu", weights_only=True)
        m.load_state_dict(state)      # strict: a shape change fails loudly
        m.eval()
        ensemble.append(m)
    log.info("loaded BSTAN ensemble: %d members, T_w=%d, thr=%.6f",
             len(ensemble), T_w, conf_threshold)

    monitor = LiveBottleneckMonitor(ensemble, edge_index, edge_weight,
                                    G_dir, T_w, conf_threshold)

    return BottleneckBundle(ensemble=ensemble, edge_index=edge_index, edge_weight=edge_weight,
                            G_dir=G_dir, G=G, T_w=T_w, conf_threshold=conf_threshold,
                            xmin=xmin, xmax=xmax, features=features, zones=zones,
                            n_stations=n_stations, monitor=monitor)


def load_defect(settings: Settings) -> DefectBundle:
    """Load fine-tuned YOLO + chain table. §4.

    The detector is optional-by-config. When absent the defect layer stays OFF and
    emits nothing — no fabricated detections (Architecture §9, honesty rules).
    """
    dcfg = settings.model["defect"]
    chains_path = settings.artifact(settings.model["chains"]["table"])
    learned = pd.DataFrame(json.loads(chains_path.read_text()))
    for col in ("trigger", "downstream", "P_B_given_A", "lift"):
        if col not in learned.columns:
            raise ConfigError(f"{chains_path} missing column '{col}' required by predict_chain")

    yolo_path = settings.artifact(dcfg["yolo_weights"])
    yolo, err = None, None
    if not yolo_path.exists():
        err = (f"fine-tuned detector not present at {yolo_path}. The defect layer is OFF: no "
               f"detections are emitted. Drop in the exported best.pt to enable it.")
        log.warning(err)
    else:
        try:
            from ultralytics import YOLO
            yolo = YOLO(str(yolo_path))
            names = [yolo.names[i] for i in sorted(yolo.names)]
            expected = settings.visual_classes
            # §4: assert this is NOT a COCO model — class names must equal VISUAL_CLASSES.
            if sorted(names) != sorted(expected):
                raise ConfigError(
                    f"{yolo_path} is not the fine-tuned Cascade detector. Its classes "
                    f"({len(names)}) do not match the configured VISUAL_CLASSES "
                    f"({len(expected)}). Refusing to serve a COCO/foreign model as the "
                    f"defect detector. Got: {names[:6]}...")
            log.info("loaded fine-tuned YOLO: %d classes from %s", len(names), yolo_path)
        except ConfigError:
            raise
        except Exception as e:                      # noqa: BLE001 - surfaced, not swallowed
            err = f"failed to load {yolo_path}: {e}"
            log.error(err)
            yolo = None

    frames_dir = settings.artifact(dcfg.get("sample_images_dir", "sample_frames"))
    sample_frames = sorted(
        p for p in frames_dir.glob("*") if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".bmp"}
    ) if frames_dir.exists() else []

    return DefectBundle(yolo=yolo, yolo_path=yolo_path, yolo_loaded=yolo is not None,
                        yolo_error=err, visual_classes=settings.visual_classes,
                        visual_to_process=settings.visual_to_process,
                        camera_to_station=settings.camera_to_station,
                        learned_chains=learned, sample_frames=sample_frames)


def load_metrics(settings: Settings) -> dict:
    """Validated metrics recorded at export. Never typed into code."""
    p = settings.artifact(settings.model.get("metrics", "metrics.json"))
    if not p.exists():
        return {}
    return json.loads(p.read_text())
