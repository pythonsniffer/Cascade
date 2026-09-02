"""Defect service — fine-tuned YOLO inference + event builder + chain engine.

Backend Instructions §6. yolo_result_to_events and predict_chain are the notebook's
functions (cells B6 and B8), with the two mappings read from config instead of being
module literals. The chain engine stays a SEPARATE layer from the detector and from
BSTAN (Project Context §8.5).
"""
from __future__ import annotations

import datetime as _dt
import logging

import pandas as pd

from backend.config.loader import Settings
from backend.models.loader import DefectBundle
from backend.services.simulator import VehicleFrame

log = logging.getLogger("cascade.defect")


# ─── B8 · predict_chain (verbatim) ───────────────────────────────────────
def predict_chain(detected_defect, learned, min_lift=1.2):
    """Given a defect just detected on a vehicle, list likely downstream defects."""
    hits = learned[(learned.trigger == detected_defect) & (learned.lift >= min_lift)]
    return hits[["downstream", "P_B_given_A", "lift"]].reset_index(drop=True)


class DefectService:
    def __init__(self, settings: Settings, bundle: DefectBundle):
        self.settings = settings
        self.bundle = bundle

    @property
    def enabled(self) -> bool:
        return self.bundle.yolo_loaded and bool(self.bundle.sample_frames)

    # ─── B6 · yolo_result_to_events (config-driven mappings) ───
    def _result_to_events(self, result, vehicle_id: int, camera_id=None, ts=None) -> list[dict]:
        cam_map = self.settings.camera_to_station
        station = cam_map.get(camera_id, self.settings.default_station)
        ts = ts or _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        classes = self.settings.visual_classes
        events = []
        for b in result.boxes:
            cls_id = int(b.cls)
            events.append(dict(
                vehicle_id=int(vehicle_id),
                station_id=int(station),
                timestamp=ts,
                defect_class=classes[cls_id],          # REAL YOLO class (fine-tuned)
                confidence=round(float(b.conf), 3),
                bbox=[round(v, 1) for v in b.xyxy[0].tolist()],
                source="FINE_TUNED_YOLO",
                camera_id=camera_id,
                station_source=("camera_map" if camera_id in cam_map else "SIMULATED_default"),
            ))
        return events

    def detect(self, vehicle: VehicleFrame) -> list[dict]:
        """Run the detector on one vehicle frame -> structured events + process type.

        Returns [] when the detector is unavailable or finds nothing. No detection is
        NOT a zero-defect claim (Architecture §9) — the caller must not invent one.
        """
        if not self.enabled or vehicle.frame_path is None:
            return []
        dcfg = self.settings.model["defect"]
        try:
            result = self.bundle.yolo.predict(str(vehicle.frame_path),
                                              imgsz=int(dcfg["imgsz"]),
                                              conf=float(dcfg["conf"]),
                                              verbose=False)[0]
        except Exception as e:                       # noqa: BLE001
            log.error("YOLO inference failed on %s: %s", vehicle.frame_path, e)
            return []
        events = self._result_to_events(result, vehicle.vehicle_id,
                                        camera_id=vehicle.camera_id, ts=vehicle.timestamp)
        v2p = self.settings.visual_to_process
        for e in events:
            e["defect_type"] = v2p.get(e["defect_class"])   # bridge to the chain engine
            e["frame"] = vehicle.frame_path.name
        return events

    def chain(self, events: list[dict]) -> list[dict]:
        """Attach the predicted downstream chain to each event (chain engine layer)."""
        learned = self.bundle.learned_chains
        min_lift = self.settings.min_lift
        for e in events:
            dt = e.get("defect_type")
            if not dt:
                e["chains"] = []
                continue
            hits = predict_chain(dt, learned, min_lift)
            e["chains"] = [
                dict(trigger_defect=dt,
                     predicted_downstream_defect=r.downstream,
                     P_B_given_A=float(r.P_B_given_A),
                     lift=float(r.lift),
                     origin_station=int(e["station_id"]),
                     action=f"Inspect for {r.downstream} downstream of S{int(e['station_id'])}")
                for _, r in hits.iterrows()
            ]
        return events

    def events_frame(self, events: list[dict]) -> pd.DataFrame:
        """DataFrame shaped as build_twin_state expects."""
        return pd.DataFrame(events)

    def status(self) -> dict:
        """Report the layer's exact state. 'detector present but no frames to run it
        on' is a different situation from 'no detector', and the UI must not
        conflate them (Architecture §9)."""
        if not self.bundle.yolo_loaded:
            state, detail = "no_detector", (
                "The fine-tuned detector weights are not loaded, so no detections are "
                "produced. Nothing is shown in their place.")
        elif not self.bundle.sample_frames:
            state, detail = "no_frames", (
                "The fine-tuned detector is loaded and verified, but there are no camera "
                "frames for it to inspect. Detections appear once frames are supplied.")
        else:
            state, detail = "ready", "The fine-tuned detector is running on camera frames."
        return {
            "detector_loaded": self.bundle.yolo_loaded,
            "detector_path": str(self.bundle.yolo_path),
            "frames_available": len(self.bundle.sample_frames),
            "frames_dir": str(self.settings.artifact(
                self.settings.model["defect"].get("sample_images_dir", "sample_frames"))),
            "enabled": self.enabled,
            "state": state,
            "detail": detail,
            "error": self.bundle.yolo_error,
            "chain_rules": int(len(self.bundle.learned_chains)),
            "min_lift": self.settings.min_lift,
        }
