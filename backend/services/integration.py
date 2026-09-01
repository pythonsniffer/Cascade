"""Integration service — build_twin_state() join.

COPIED VERBATIM from Cascade_Integrated.ipynb cell C1, with the two changes the
spec requires: station_zone reads zones from config, and predict_chain/min_lift are
injected rather than module globals. The record SHAPE is unchanged
(Project Context §5).
"""
from __future__ import annotations

from backend.config.loader import Settings
from backend.services.defect import predict_chain


class IntegrationService:
    def __init__(self, settings: Settings, learned, min_lift: float | None = None):
        self.settings = settings
        self.learned = learned
        self.min_lift = settings.min_lift if min_lift is None else min_lift

    def station_zone(self, sid: int) -> str:
        return self.settings.zone_of(int(sid))

    def build_twin_state(self, vehicle_id, timestamp, bottleneck_alert, vehicle_events):
        """Combine ONE vehicle's defect events with the shift's bottleneck prediction.

        bottleneck_alert : dict returned by LiveBottleneckMonitor.step() (or None).
        vehicle_events   : DataFrame rows for this vehicle (YOLO defect events).
        """
        visual_defects, process_defects, chain_alerts = [], [], []
        for _, e in vehicle_events.iterrows():
            visual_defects.append(dict(station_id=int(e["station_id"]),
                                       zone=self.station_zone(int(e["station_id"])),
                                       defect_class=e["defect_class"],
                                       confidence=float(e["confidence"]), bbox=e["bbox"]))
            process_defects.append(dict(station_id=int(e["station_id"]),
                                        defect_type=e["defect_type"]))
            for _, r in predict_chain(e["defect_type"], self.learned, self.min_lift).iterrows():
                chain_alerts.append(dict(
                    trigger_defect=e["defect_type"],
                    predicted_downstream_defect=r.downstream,
                    P_B_given_A=float(r.P_B_given_A), lift=float(r.lift),
                    origin_station=int(e["station_id"]),
                    action=f"Inspect for {r.downstream} downstream of S{int(e['station_id'])}"))

        bn = bottleneck_alert.get("predicted_bottleneck_station") if bottleneck_alert else None
        return dict(
            vehicle_id=int(vehicle_id), timestamp=timestamp,
            bottleneck_station=bn,
            bottleneck_zone=(self.station_zone(bn) if bn is not None else None),
            bottleneck_confidence=(bottleneck_alert.get("confidence") if bottleneck_alert else None),
            bottleneck_abstained=(bottleneck_alert.get("abstained") if bottleneck_alert else None),
            visual_defects=visual_defects,
            process_defects=process_defects,
            downstream_inspection_alerts=chain_alerts,
            _meta=dict(ids="SIMULATED_prototype_metadata",
                       defect_source="FINE_TUNED_YOLO",
                       bottleneck_source="BSTAN_LiveBottleneckMonitor",
                       mapping="visual->process is a RULE-BASED prototype mapping"),
        )
