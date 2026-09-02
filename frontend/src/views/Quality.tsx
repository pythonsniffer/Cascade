/** Quality (/quality) — detections, chain map, model card (§5.2). */
import { useEffect, useState } from "react";

import { EmptyState, Info, SectionTitle } from "../components/primitives";
import { api } from "../lib/api";
import { humanise, pct, stationLabel } from "../lib/format";
import type { DefectEvent, DetectorStatus } from "../lib/types";
import { useTwin } from "../store/twin";

export function Quality() {
  const { health, detections: liveDetections } = useTwin();
  const [detector, setDetector] = useState<DetectorStatus | null>(null);
  const [detections, setDetections] = useState<DefectEvent[]>([]);

  useEffect(() => {
    api.detections().then(d => { setDetections(d.detections); setDetector(d.detector); })
      .catch(() => undefined);
  }, []);

  const shown = liveDetections.length ? liveDetections : detections;
  const det = detector ?? health?.models.defect;
  const detectorLoaded = det?.detector_loaded ?? false;
  const running = det?.state === "ready";
  const metrics = health?.metrics.detector;

  return (
    <div className="space-y-5 p-4 lg:p-6">
      {/* model card */}
      <section>
        <SectionTitle hint="How well the detector performed on its held-out test images.">
          Detector model card
        </SectionTitle>
        {detectorLoaded ? (
          <>
            {metrics && (
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <MetricCard label="mAP50" value={metrics.mAP50.toFixed(3)}
                  help="Mean average precision at 50% overlap — the standard single score for how well a detector finds and places defects." />
                <MetricCard label="Precision" value={metrics.precision.toFixed(3)}
                  help="Of the defects it flagged, how many were real." />
                <MetricCard label="Recall" value={metrics.recall.toFixed(3)}
                  help="Of the real defects present, how many it found." />
                <MetricCard label="F1" value={(metrics.f1 ?? 0).toFixed(3)}
                  help="The balance between precision and recall in one number." />
              </div>
            )}
            {!running && (
              <p className="mt-2 rounded-xl border border-accent/25 bg-accent/[.05] p-2.5
                            text-[11px] leading-relaxed">
                {det?.detail}
              </p>
            )}
          </>
        ) : (
          <EmptyState
            tone="warn"
            title="The detector is not loaded in this instance"
            body={<>
              Its published metrics are deliberately not shown here, because this instance is not
              running the detector and cannot stand behind them.{" "}
              {detector?.error && <span className="font-mono text-[10.5px]">{detector.error}</span>}
            </>}
          />
        )}
      </section>

      {/* detection gallery */}
      <section>
        <SectionTitle
          right={<span className="font-mono text-[10.5px] text-muted tnum">
            {shown.length} detection{shown.length === 1 ? "" : "s"} this session
          </span>}
          hint="Each row is one bounding box the camera model produced on a real image."
        >
          Detections
        </SectionTitle>
        {shown.length === 0 ? (
          <EmptyState
            title="No detections"
            body={running
              ? "Nothing has been detected yet this session. An empty list is not a claim that the line is defect-free."
              : det?.detail ?? "The camera layer is not producing detections."}
          />
        ) : (
          <div className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-3">
            {shown.slice(0, 24).map((d, i) => <DetectionCard key={i} d={d} />)}
          </div>
        )}
      </section>

    </div>
  );
}

function MetricCard({ label, value, help }: { label: string; value: string; help: string }) {
  return (
    <div className="card-solid p-3.5">
      <p className="eyebrow flex items-center">{label}<Info term={label}>{help}</Info></p>
      <p className="mt-1 font-mono text-[26px] font-medium leading-none tnum">{value}</p>
    </div>
  );
}

function DetectionCard({ d }: { d: DefectEvent }) {
  // The detector returns boxes in the ORIGINAL image's pixel space, and the preview
  // letterboxes the image with object-contain. So the overlay has to reproduce that
  // fit — scale by the contained size and offset by the letterbox bars — rather than
  // assume the image fills the frame.
  const [nat, setNat] = useState<{ w: number; h: number } | null>(null);
  const BOX_W = 320, BOX_H = 190;

  let rect: { x: number; y: number; w: number; h: number } | null = null;
  if (d.bbox && nat && nat.w > 0 && nat.h > 0) {
    const k = Math.min(BOX_W / nat.w, BOX_H / nat.h);
    const offX = (BOX_W - nat.w * k) / 2;
    const offY = (BOX_H - nat.h * k) / 2;
    const [x1, y1, x2, y2] = d.bbox;
    rect = {
      x: offX + x1 * k, y: offY + y1 * k,
      w: Math.max(2, (x2 - x1) * k), h: Math.max(2, (y2 - y1) * k),
    };
  }

  return (
    <article className="card-solid overflow-hidden">
      <div className="relative bg-[#F1EFEC]" style={{ height: BOX_H }}>
        {d.frame ? (
          <img
            src={`/frames/${d.frame}`}
            alt={`Camera frame for vehicle ${d.vehicle_id}`}
            className="h-full w-full object-contain"
            onLoad={(e) => setNat({
              w: e.currentTarget.naturalWidth, h: e.currentTarget.naturalHeight })}
          />
        ) : (
          <div className="grid h-full place-items-center px-4 text-center font-mono text-[10px]
                          leading-relaxed text-muted">
            frame image not available in this instance
          </div>
        )}
        {rect && (
          <svg className="pointer-events-none absolute inset-0 h-full w-full"
               viewBox={`0 0 ${BOX_W} ${BOX_H}`} aria-hidden>
            <rect x={rect.x} y={rect.y} width={rect.w} height={rect.h}
                  fill="none" stroke="#F0552B" strokeWidth="1.6" />
          </svg>
        )}
      </div>
      <div className="space-y-1 p-2.5">
        <div className="flex items-baseline justify-between gap-2">
          <span className="text-[12px] font-medium">{humanise(d.defect_class)}</span>
          <span className="font-mono text-[11px] font-medium text-accent tnum">
            {pct(d.confidence)}
          </span>
        </div>
        <p className="font-mono text-[10px] text-muted tnum">
          vehicle {d.vehicle_id} · {stationLabel(d.station_id)} · {d.camera_id ?? "no camera"}
        </p>
        <div className="flex flex-wrap items-center gap-1 pt-0.5">
          <span className="pill border border-hairline bg-black/[.03] font-mono text-[9px]">
            {d.source}
          </span>
          {d.defect_type && (
            <span className="pill border border-hairline bg-black/[.03] text-[9.5px]">
              → {humanise(d.defect_type)}
              <Info term="process defect">
                A rule-based mapping from what the camera sees to the process defect the chain
                engine reasons about. A plant's QA team would validate it.
              </Info>
            </span>
          )}
          {d.station_source === "SIMULATED_default" && (
            <span className="pill border border-hairline bg-black/[.03] text-[9.5px] text-muted">
              station assigned by default
            </span>
          )}
        </div>
      </div>
    </article>
  );
}
