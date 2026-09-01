/** Right rail — streaming downstream-inspection alerts (§5.1).
 *  Orange severity bar; newest on top; ARIA live region. */
import { useState } from "react";

import { humanise, stationLabel, timeAgo } from "../lib/format";
import type { ChainAlert } from "../lib/types";
import { EmptyState, Info } from "./primitives";

export function AlertRail({ alerts, detectorOn, onOpen }: {
  alerts: ChainAlert[];
  detectorOn: boolean;
  onOpen: (vehicleId: number) => void;
}) {
  const [collapsed, setCollapsed] = useState(false);

  return (
    <aside
      className={`card flex min-h-0 flex-col transition-[width] duration-200 ${
        collapsed ? "w-[52px]" : "w-[310px]"}`}
      aria-label="Live inspection alerts"
    >
      <header className="flex items-center gap-2 border-b border-hairline/70 px-3 py-2.5">
        {!collapsed && (
          <>
            <h2 className="font-display text-[13px] font-medium">Live alerts</h2>
            <span className="pill border border-hairline bg-white/60 font-mono tnum">
              {alerts.length}
            </span>
            <Info term="Live alerts">
              When a defect is caught, the chain engine names the defect it most often triggers
              further down the line, so that vehicle can be re-inspected before the batch moves on.
            </Info>
          </>
        )}
        <button
          onClick={() => setCollapsed(c => !c)}
          aria-label={collapsed ? "Expand alerts" : "Collapse alerts"}
          className="ml-auto grid h-6 w-6 place-items-center rounded-lg text-muted
                     transition-colors hover:bg-black/[.05] hover:text-ink"
        >
          {collapsed ? "‹" : "›"}
        </button>
      </header>

      {!collapsed && (
        <div
          className="min-h-0 flex-1 space-y-2 overflow-y-auto p-2.5"
          role="log" aria-live="polite" aria-relevant="additions"
        >
          {alerts.length === 0 ? (
            <EmptyState
              title={detectorOn ? "No alerts yet" : "Camera layer is off"}
              tone={detectorOn ? "neutral" : "warn"}
              body={detectorOn
                ? "Alerts appear here when the detector catches a defect that the chain engine links to a downstream one."
                : "The fine-tuned detector weights are not loaded in this instance, so no detections and no chain alerts are produced. Nothing is shown in their place."}
            />
          ) : (
            alerts.map((a, i) => (
              <AlertCard key={`${a.vehicle_id}-${a.origin_station}-${a.predicted_downstream_defect}-${i}`}
                         alert={a} onOpen={onOpen} />
            ))
          )}
        </div>
      )}
    </aside>
  );
}

function AlertCard({ alert, onOpen }: { alert: ChainAlert; onOpen: (v: number) => void }) {
  // severity bar length tracks lift — the model's own strength-of-association number
  const severity = Math.max(0.08, Math.min(1, (alert.lift - 1) / 1.0));
  return (
    <button
      onClick={() => alert.vehicle_id !== undefined && onOpen(alert.vehicle_id)}
      className="w-full animate-slideIn rounded-xl border border-hairline bg-white/70 p-2.5
                 text-left transition-colors hover:bg-white"
    >
      <div className="flex items-baseline justify-between gap-2">
        <span className="font-mono text-[11px] font-medium tnum">
          Vehicle {alert.vehicle_id} @ {stationLabel(alert.origin_station)}
        </span>
        <span className="font-mono text-[9.5px] text-muted">{timeAgo(alert.timestamp)}</span>
      </div>

      <p className="mt-1 text-[12px] leading-snug">
        <span className="font-medium">{humanise(alert.trigger_defect)}</span>
        <span className="text-muted"> caught — inspect for </span>
        <span className="font-medium text-accent">
          {humanise(alert.predicted_downstream_defect)}
        </span>
        <span className="text-muted"> downstream</span>
      </p>

      <div className="mt-2 flex items-center gap-2">
        <div className="h-1 flex-1 overflow-hidden rounded-pill bg-black/[.06]">
          <div className="h-full rounded-pill bg-accent transition-[width] duration-500"
               style={{ width: `${severity * 100}%` }} />
        </div>
        <span className="font-mono text-[9.5px] text-muted tnum">
          lift {alert.lift.toFixed(2)}
        </span>
      </div>
    </button>
  );
}
