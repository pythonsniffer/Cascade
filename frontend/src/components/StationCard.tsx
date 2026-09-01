/** Frosted floating detail card — appears over the floor on station click (§5.1). */
import type { BottleneckState, Line } from "../lib/types";
import { stationStatus } from "../store/twin";
import { ConfidencePill, Info, STATUS_META, StatusDot } from "./primitives";

export function StationCard({ stationId, line, bottleneck, cameras, onClose }: {
  stationId: number;
  line: Line;
  bottleneck: BottleneckState | null;
  cameras: Record<string, number>;
  onClose: () => void;
}) {
  const node = line.nodes.find(n => n.station_id === stationId);
  if (!node) return null;

  const status = stationStatus(stationId, bottleneck, node.sensor_poor);
  const meta = STATUS_META[status];
  const blk = bottleneck?.blk?.[stationId];
  const stv = bottleneck?.stv?.[stationId];
  const camera = Object.entries(cameras).find(([, s]) => s === stationId)?.[0];
  const warming = !bottleneck || bottleneck.confidence === "warming_up";

  return (
    <aside
      className="card w-[290px] animate-slideIn p-4"
      role="dialog"
      aria-label={`Station S${stationId} detail`}
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="eyebrow">{node.zone_label}</p>
          <h3 className="font-display text-[22px] font-light leading-tight tracking-tight">
            Station <span className="font-mono text-[20px] tnum">S{stationId}</span>
          </h3>
        </div>
        <button
          onClick={onClose}
          aria-label="Close station detail"
          className="grid h-6 w-6 place-items-center rounded-lg text-muted transition-colors
                     hover:bg-black/[.05] hover:text-ink"
        >
          ×
        </button>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-1.5">
        <span className="pill border border-hairline bg-white/70">
          <StatusDot status={status} size={6} pulse={status === "bottleneck"} />
          {meta.label}
          <Info term={meta.label}>{meta.help}</Info>
        </span>
        <ConfidencePill confidence={bottleneck?.confidence ?? null}
                        abstained={bottleneck?.abstained} />
      </div>

      {warming ? (
        <p className="mt-3 rounded-xl border border-dashed border-hairline bg-black/[.02]
                      p-3 text-[11.5px] leading-relaxed text-muted">
          The forecaster is still filling its history window. No prediction for this station yet.
        </p>
      ) : blk === undefined || stv === undefined ? (
        <p className="mt-3 rounded-xl border border-dashed border-hairline bg-black/[.02]
                      p-3 text-[11.5px] leading-relaxed text-muted">
          The model abstained this shift, so there are no per-station figures to show.
        </p>
      ) : (
        <dl className="mt-3 grid grid-cols-2 gap-2">
          <Metric label="Blockage" value={blk}
                  help="How much this station is predicted to be held up by the station after it." />
          <Metric label="Starvation" value={stv}
                  help="How much this station is predicted to sit waiting for work from upstream." />
        </dl>
      )}

      <dl className="mt-3 space-y-1.5 border-t border-hairline pt-3 text-[11.5px]">
        <Row label="Zone">{node.zone_label}</Row>
        <Row label="Camera">
          {camera ? (
            <span className="font-mono text-[11px]">{camera}</span>
          ) : (
            <span className="text-muted">No camera mapped</span>
          )}
        </Row>
        <Row label="Instrumentation">
          {node.sensor_poor
            ? <span className="text-muted">Sparse — readings less reliable</span>
            : "Normal"}
        </Row>
      </dl>
    </aside>
  );
}

function Metric({ label, value, help }: { label: string; value: number; help: string }) {
  return (
    <div className="rounded-xl border border-hairline bg-white/60 p-2.5">
      <dt className="eyebrow flex items-center">{label}<Info term={label}>{help}</Info></dt>
      <dd className="mt-0.5 font-mono text-[19px] font-medium tnum">{value.toFixed(2)}</dd>
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt className="text-muted">{label}</dt>
      <dd className="text-right">{children}</dd>
    </div>
  );
}
