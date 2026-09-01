/** History (/history) — trends over shifts (§5.4). Monochrome charts; orange only
 *  for the alert series. */
import { useEffect, useMemo, useState } from "react";
import {
  Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";

import { EmptyState, SectionTitle } from "../components/primitives";
import { api } from "../lib/api";
import { money, zoneLabel } from "../lib/format";
import type { History as HistoryPayload } from "../lib/types";
import { useTwin } from "../store/twin";

const AXIS = { fontSize: 10, fill: "#8A8A8A" };
const TIP = { borderRadius: 12, border: "1px solid #E2E0DC", fontSize: 12, fontFamily: "Inter" };

export function History() {
  const { tickCount, pnl } = useTwin();
  const [data, setData] = useState<HistoryPayload | null>(null);
  const [range, setRange] = useState(50);

  useEffect(() => { api.history().then(setData).catch(() => undefined); }, [tickCount]);

  const shifts = useMemo(() => (data?.shifts ?? []).slice(-range), [data, range]);
  const stationBars = useMemo(() => Object.entries(data?.station_counts ?? {})
    .map(([station, count]) => ({ station: `S${station}`, count }))
    .sort((a, b) => b.count - a.count).slice(0, 12), [data]);
  const zoneBars = useMemo(() => Object.entries(data?.zone_counts ?? {})
    .map(([zone, count]) => ({ zone: zoneLabel(zone), count })), [data]);
  const currency = pnl?.currency ?? "USD";

  if (!data || data.shifts.length === 0) {
    return <div className="p-4 lg:p-6">
      <EmptyState title="Nothing to chart yet"
                  body="Run a few shifts and the trends will appear here." />
    </div>;
  }

  return (
    <div className="space-y-5 p-4 lg:p-6">
      <div className="flex flex-wrap items-center gap-2">
        <span className="eyebrow">Show last</span>
        {[25, 50, 100, 500].map(n => (
          <button key={n} onClick={() => setRange(n)} aria-pressed={range === n}
                  className={`pill border transition-colors ${
                    range === n ? "border-ink/15 bg-ink text-white"
                                : "border-hairline bg-white/60 text-muted hover:text-ink"}`}>
            {n} shifts
          </button>
        ))}
        <span className="ml-auto font-mono text-[10.5px] text-muted tnum">
          {data.shifts.length} shift{data.shifts.length === 1 ? "" : "s"} recorded
        </span>
      </div>

      <section>
        <SectionTitle hint="Defects the camera caught, and how many of those triggered a downstream inspection.">
          Defects and inspections per shift
        </SectionTitle>
        <div className="card-solid p-3" style={{ height: 230 }}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={shifts} margin={{ top: 8, right: 10, bottom: 4, left: 0 }}>
              <CartesianGrid stroke="#E2E0DC" vertical={false} />
              <XAxis dataKey="shift_id" tick={AXIS} stroke="#E2E0DC" tickLine={false} />
              <YAxis tick={AXIS} stroke="#E2E0DC" tickLine={false} width={34} allowDecimals={false} />
              <Tooltip contentStyle={TIP} labelFormatter={l => `Shift ${l}`} />
              <Line type="monotone" dataKey="n_defect_events" name="Defects caught"
                    stroke="#141414" strokeWidth={1.5} dot={false} isAnimationActive={false} />
              <Line type="monotone" dataKey="n_chain_alerts" name="Inspections raised"
                    stroke="#F0552B" strokeWidth={1.7} dot={false} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </section>

      <div className="grid gap-5 lg:grid-cols-2">
        <section>
          <SectionTitle hint="Only confident calls are counted. Shifts where the model abstained are excluded.">
            Where bottlenecks were called
          </SectionTitle>
          <div className="card-solid p-3" style={{ height: 230 }}>
            {stationBars.length === 0 ? (
              <div className="grid h-full place-items-center px-4 text-center text-[12px] text-muted">
                No confident bottleneck calls yet.
              </div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={stationBars} margin={{ top: 8, right: 10, bottom: 4, left: 0 }}>
                  <CartesianGrid stroke="#E2E0DC" vertical={false} />
                  <XAxis dataKey="station" tick={AXIS} stroke="#E2E0DC" tickLine={false} />
                  <YAxis tick={AXIS} stroke="#E2E0DC" tickLine={false} width={30}
                         allowDecimals={false} />
                  <Tooltip contentStyle={TIP} cursor={{ fill: "rgba(20,20,20,.04)" }} />
                  <Bar dataKey="count" name="Times called" fill="#141414" radius={[3, 3, 0, 0]}
                       isAnimationActive={false} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </section>

        <section>
          <SectionTitle>By zone</SectionTitle>
          <div className="card-solid p-3" style={{ height: 230 }}>
            {zoneBars.length === 0 ? (
              <div className="grid h-full place-items-center px-4 text-center text-[12px] text-muted">
                No confident bottleneck calls yet.
              </div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={zoneBars} layout="vertical"
                          margin={{ top: 8, right: 14, bottom: 4, left: 8 }}>
                  <CartesianGrid stroke="#E2E0DC" horizontal={false} />
                  <XAxis type="number" tick={AXIS} stroke="#E2E0DC" tickLine={false}
                         allowDecimals={false} />
                  <YAxis type="category" dataKey="zone" tick={AXIS} stroke="#E2E0DC"
                         tickLine={false} width={96} />
                  <Tooltip contentStyle={TIP} cursor={{ fill: "rgba(20,20,20,.04)" }} />
                  <Bar dataKey="count" name="Times called" fill="#141414" radius={[0, 3, 3, 0]}
                       isAnimationActive={false} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </section>
      </div>

      <section>
        <SectionTitle hint="Cumulative projected impact. A projection from your assumptions, not a measured saving.">
          Projected impact, cumulative
        </SectionTitle>
        <div className="card-solid p-3" style={{ height: 230 }}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data.pnl_series.slice(-range)}
                       margin={{ top: 8, right: 10, bottom: 4, left: 4 }}>
              <CartesianGrid stroke="#E2E0DC" vertical={false} />
              <XAxis dataKey="shift_id" tick={AXIS} stroke="#E2E0DC" tickLine={false} />
              <YAxis tick={AXIS} stroke="#E2E0DC" tickLine={false} width={54}
                     tickFormatter={v => money(v, currency)} />
              <Tooltip contentStyle={TIP} labelFormatter={l => `Shift ${l}`}
                       formatter={(v) => money(Number(v), currency)} />
              <Line type="monotone" dataKey="cumulative" name="Cumulative" stroke="#141414"
                    strokeWidth={1.6} dot={false} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </section>
    </div>
  );
}
