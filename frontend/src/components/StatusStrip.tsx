/** Bottom fleet strip — one card per station, filter tabs with live counts (§5.1). */
import { useMemo, useState } from "react";

import type { BottleneckState, Line } from "../lib/types";
import { stationStatus, type StationStatus } from "../store/twin";
import { STATUS_META, StatusDot } from "./primitives";

const FILTERS: { key: StationStatus | "all"; label: string }[] = [
  { key: "all", label: "All" },
  { key: "running", label: "Running" },
  { key: "watch", label: "Watch" },
  { key: "bottleneck", label: "Bottleneck" },
  { key: "sensor-poor", label: "Sensor-poor" },
];

export function StatusStrip({ line, bottleneck, selected, onSelect }: {
  line: Line; bottleneck: BottleneckState | null;
  selected: number | null; onSelect: (id: number | null) => void;
}) {
  const [filter, setFilter] = useState<StationStatus | "all">("all");

  const rows = useMemo(() => line.nodes.map(n => ({
    ...n, status: stationStatus(n.station_id, bottleneck, n.sensor_poor),
  })), [line, bottleneck]);

  const counts = useMemo(() => {
    const c: Record<string, number> = { all: rows.length };
    for (const r of rows) c[r.status] = (c[r.status] ?? 0) + 1;
    return c;
  }, [rows]);

  const shown = filter === "all" ? rows : rows.filter(r => r.status === filter);

  return (
    <section className="card flex min-h-0 flex-col p-2.5" aria-label="Station status">
      <div className="mb-2 flex shrink-0 flex-wrap items-center gap-1" role="tablist">
        {FILTERS.map(f => {
          const active = filter === f.key;
          return (
            <button
              key={f.key} role="tab" aria-selected={active}
              onClick={() => setFilter(f.key)}
              className={`pill border transition-colors ${
                active ? "border-ink/15 bg-ink text-white"
                       : "border-hairline bg-white/60 text-muted hover:text-ink"}`}
            >
              {f.key !== "all" && <StatusDot status={f.key} size={5} />}
              {f.label}
              <span className="font-mono tnum opacity-70">{counts[f.key] ?? 0}</span>
            </button>
          );
        })}
      </div>

      <div className="flex gap-2 overflow-x-auto pb-1">
        {shown.length === 0 ? (
          <p className="px-2 py-3 text-[11.5px] text-muted">
            No stations in this state right now.
          </p>
        ) : shown.map(r => {
          const blk = bottleneck?.blk?.[r.station_id];
          const stv = bottleneck?.stv?.[r.station_id];
          const isSel = selected === r.station_id;
          return (
            <button
              key={r.station_id}
              onClick={() => onSelect(isSel ? null : r.station_id)}
              aria-pressed={isSel}
              className={`w-[126px] shrink-0 rounded-xl border p-2 text-left transition-colors ${
                isSel ? "border-ink bg-white" : "border-hairline bg-white/60 hover:bg-white"}`}
            >
              <div className="flex items-center gap-1.5">
                <StatusDot status={r.status} size={6} pulse={r.status === "bottleneck"} />
                <span className="font-mono text-[12px] font-medium tnum">S{r.station_id}</span>
                <span className="ml-auto font-mono text-[8.5px] uppercase tracking-wide text-muted">
                  {r.zone}
                </span>
              </div>
              <p className="mt-1 truncate text-[10.5px] text-muted">
                {STATUS_META[r.status].label}
              </p>
              <p className="mt-0.5 font-mono text-[10px] text-muted tnum">
                {blk !== undefined && stv !== undefined
                  ? `blk ${blk.toFixed(1)} · stv ${stv.toFixed(1)}`
                  : "no forecast yet"}
              </p>
            </button>
          );
        })}
      </div>
    </section>
  );
}
