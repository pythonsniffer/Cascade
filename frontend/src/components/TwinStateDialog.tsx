/** Full twin-state record — opened from an alert (§5.1 "click → full twin-state record"). */
import { useEffect, useState } from "react";

import { api } from "../lib/api";
import { humanise, stationLabel, zoneLabel } from "../lib/format";
import type { TwinState } from "../lib/types";
import { ConfidencePill } from "./primitives";

export function TwinStateDialog({ vehicleId, onClose }: {
  vehicleId: number; onClose: () => void;
}) {
  const [record, setRecord] = useState<TwinState | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    api.twinState(vehicleId)
      .then(r => alive && setRecord(r))
      .catch(e => alive && setError(e.message));
    return () => { alive = false; };
  }, [vehicleId]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-ink/20 p-4 backdrop-blur-sm
                 animate-fadeIn"
      onClick={onClose} role="presentation"
    >
      <div
        className="card max-h-[82vh] w-full max-w-lg overflow-y-auto p-5"
        role="dialog" aria-modal="true" aria-label={`Twin state for vehicle ${vehicleId}`}
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-start justify-between">
          <div>
            <p className="eyebrow">Twin-state record</p>
            <h2 className="font-display text-[24px] font-light tracking-tight">
              Vehicle <span className="font-mono tnum">{vehicleId}</span>
            </h2>
          </div>
          <button onClick={onClose} aria-label="Close"
                  className="grid h-7 w-7 place-items-center rounded-lg text-muted
                             transition-colors hover:bg-black/[.05] hover:text-ink">×</button>
        </div>

        {error && <p className="mt-4 text-[12px] text-accent">Could not load record: {error}</p>}
        {!record && !error && <p className="mt-4 text-[12px] text-muted">Loading…</p>}

        {record && (
          <div className="mt-4 space-y-4 text-[12px]">
            <section>
              <p className="eyebrow mb-1.5">Line state at the time</p>
              <div className="flex flex-wrap items-center gap-2">
                <span className="pill border border-hairline bg-white/60">
                  Bottleneck {stationLabel(record.bottleneck_station)}
                  {record.bottleneck_zone && ` · ${zoneLabel(record.bottleneck_zone)}`}
                </span>
                <ConfidencePill confidence={record.bottleneck_confidence}
                                abstained={record.bottleneck_abstained} />
              </div>
            </section>

            <section>
              <p className="eyebrow mb-1.5">Defects seen by the camera</p>
              {record.visual_defects.length === 0 ? (
                <p className="text-muted">
                  No detection on this vehicle. That is not a claim it is defect-free.
                </p>
              ) : (
                <ul className="space-y-1">
                  {record.visual_defects.map((v, i) => (
                    <li key={i} className="flex items-baseline justify-between gap-2
                                           rounded-lg border border-hairline bg-white/60 px-2.5 py-1.5">
                      <span>{humanise(v.defect_class)}</span>
                      <span className="font-mono text-[11px] text-muted tnum">
                        {stationLabel(v.station_id)} · {(v.confidence * 100).toFixed(0)}%
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            {record.downstream_inspection_alerts.length > 0 && (
              <section>
                <p className="eyebrow mb-1.5">Predicted downstream chains</p>
                <ul className="space-y-1">
                  {record.downstream_inspection_alerts.map((a, i) => (
                    <li key={i} className="rounded-lg border border-accent/20 bg-accent/[.04]
                                           px-2.5 py-2">
                      <p>
                        {humanise(a.trigger_defect)}
                        <span className="mx-1.5 text-accent">→</span>
                        <span className="font-medium">{humanise(a.predicted_downstream_defect)}</span>
                      </p>
                      <p className="mt-0.5 font-mono text-[10px] text-muted tnum">
                        P={a.P_B_given_A.toFixed(3)} · lift={a.lift.toFixed(2)} ·
                        from {stationLabel(a.origin_station)}
                      </p>
                    </li>
                  ))}
                </ul>
              </section>
            )}

            <section>
              <p className="eyebrow mb-1.5">Provenance</p>
              <dl className="space-y-1 rounded-lg border border-hairline bg-black/[.02] p-2.5
                             font-mono text-[10.5px] text-muted">
                {Object.entries(record._meta).map(([k, v]) => (
                  <div key={k} className="flex gap-2">
                    <dt className="shrink-0">{k}:</dt>
                    <dd className="break-words">{String(v)}</dd>
                  </div>
                ))}
              </dl>
            </section>
          </div>
        )}
      </div>
    </div>
  );
}
