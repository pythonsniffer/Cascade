/** Quality (/quality) — detections, chain map, model card (§5.2). */
import { useEffect, useState } from "react";

import { ChainGraph } from "../components/ChainGraph";
import { EmptyState, Info, SectionTitle } from "../components/primitives";
import { api } from "../lib/api";
import { humanise, pct, stationLabel } from "../lib/format";
import type { DefectEvent, DetectorStatus } from "../lib/types";
import { useTwin } from "../store/twin";

export function Quality() {
  const { health, config, detections: liveDetections } = useTwin();
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
  const firedTriggers = new Set(shown.map(d => d.defect_type).filter(Boolean) as string[]);
  const metrics = health?.metrics.detector;
  // the loaded checkpoint's own recorded numbers, read from best.pt at load time
  const ckpt = health?.metrics.detector_checkpoint;

  return (
    <div className="space-y-5 p-4 lg:p-6">
      {/* model card */}
      <section>
        <SectionTitle hint="How well the detector performed on its held-out test images.">
          Detector model card
        </SectionTitle>
        {detectorLoaded ? (
          <>
            {ckpt && (
              <>
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                  <MetricCard label="mAP50" value={ckpt.mAP50.toFixed(3)}
                    help="Mean average precision at 50% overlap — the standard single score for how well a detector finds and places defects." />
                  <MetricCard label="Precision" value={ckpt.precision.toFixed(3)}
                    help="Of the defects it flagged, how many were real." />
                  <MetricCard label="Recall" value={ckpt.recall.toFixed(3)}
                    help="Of the real defects present, how many it found." />
                  <MetricCard label="F1" value={(ckpt.f1 ?? 0).toFixed(3)}
                    help="The balance between precision and recall in one number." />
                </div>
                <p className="mt-2 text-[11px] leading-relaxed text-muted">
                  Read from the loaded checkpoint itself
                  {ckpt.train_epochs && ` (${ckpt.train_epochs} epochs at ${ckpt.train_imgsz}px)`}.
                  {" "}{ckpt.note}
                </p>
              </>
            )}
            {metrics && (
              <p className="mt-2 rounded-xl border border-hairline bg-black/[.02] p-2.5
                            text-[11px] leading-relaxed text-muted">
                For comparison, the notebook reports mAP50 {metrics.mAP50}, precision{" "}
                {metrics.precision}, recall {metrics.recall}, F1 {metrics.f1} on{" "}
                {metrics.test_images} real test images, trained on {metrics.train_images} real
                labelled images. Source: {metrics.source}.
              </p>
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

      {/* chain map */}
      <section>
        <SectionTitle hint="Learned from inspection history: when the trigger defect appears, the downstream defect follows more often than chance.">
          Defect chains
        </SectionTitle>
        <ChainGraph chains={config?.chains ?? []} fired={firedTriggers} />
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
  const [w, h] = [320, 180];
  const bb = d.bbox;
  // bboxes are in the detector's input pixel space; scale to the preview box
  const scale = bb ? Math.min(w / Math.max(bb[2], 1), h / Math.max(bb[3], 1), 1) : 1;
  return (
    <article className="card-solid overflow-hidden">
      <div className="relative bg-[#F1EFEC]" style={{ height: h }}>
        {d.frame ? (
          <img src={`/frames/${d.frame}`} alt={`Frame for vehicle ${d.vehicle_id}`}
               className="h-full w-full object-contain" />
        ) : (
          <div className="grid h-full place-items-center px-4 text-center font-mono text-[10px]
                          leading-relaxed text-muted">
            frame image not bundled in this instance
          </div>
        )}
        {bb && (
          <svg className="pointer-events-none absolute inset-0 h-full w-full"
               viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" aria-hidden>
            <rect x={bb[0] * scale} y={bb[1] * scale}
                  width={Math.max(2, (bb[2] - bb[0]) * scale)}
                  height={Math.max(2, (bb[3] - bb[1]) * scale)}
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
