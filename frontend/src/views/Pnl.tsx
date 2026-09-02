/** Profit & Loss (/pnl) — the requested feature (§5.3).
 *  Never a bare number: the disclaimer and the breakdown are always on screen. */
import { useEffect, useMemo, useState } from "react";
import {
  Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";

import { AssumptionsPanel } from "../components/AssumptionsPanel";
import { EmptyState, Info, SectionTitle } from "../components/primitives";
import { humanise, money, moneyExact } from "../lib/format";
import { useTwin } from "../store/twin";

export function Pnl() {
  const { pnl, refreshPnl } = useTwin();
  const [pending, setPending] = useState(false);

  useEffect(() => { void refreshPnl(); }, [refreshPnl]);

  if (!pnl) {
    return <div className="grid h-full place-items-center text-[13px] text-muted">Loading…</div>;
  }

  const currency = pnl.currency;
  const lines = Object.entries(pnl.cumulative_breakdown);
  const hasData = pnl.shifts_counted > 0;

  return (
    <div className="space-y-5 p-4 lg:p-6">
      {/* ── headline ── */}
      <section className="flex flex-wrap items-end gap-x-8 gap-y-3">
        <div>
          <p className="eyebrow flex items-center">
            Net projected impact this session
            <Info term="Net projected impact">
              Value the model's correct calls are projected to create, minus the projected cost of
              the inspections and false alarms they cause.
            </Info>
          </p>
          <p className="font-display text-[54px] font-light leading-none tracking-tight tnum
                        lg:text-[64px]">
            {moneyExact(pnl.cumulative_net, currency)}
          </p>
          <p className="mt-1.5 text-[11.5px] text-muted">
            Over {pnl.shifts_counted} shift{pnl.shifts_counted === 1 ? "" : "s"} ·{" "}
            {currency} · projected, not measured
          </p>
        </div>

        {pnl.sensitivity && (
          <div className="card-solid p-3.5">
            <p className="eyebrow">Sensitivity</p>
            <p className="mt-1 text-[12px] leading-snug">
              If <span className="font-mono">{humanise(pnl.sensitivity.key).toLowerCase()}</span>{" "}
              moves ±{(pnl.sensitivity.pct * 100).toFixed(0)}%, net lands between{" "}
              <span className="font-mono font-medium tnum">
                {money(pnl.sensitivity.cumulative_low, currency)}
              </span>{" "}and{" "}
              <span className="font-mono font-medium tnum">
                {money(pnl.sensitivity.cumulative_high, currency)}
              </span>.
            </p>
          </div>
        )}
      </section>

      {pnl.missing_config.length > 0 && (
        <div className="rounded-card border border-accent/30 bg-accent/[.05] p-3 text-[12px]">
          <p className="font-medium">Some lines could not be computed.</p>
          <p className="mt-0.5 text-muted">
            These assumptions are missing, so those lines are left blank rather than guessed:{" "}
            <span className="font-mono">{pnl.missing_config.join(", ")}</span>
          </p>
        </div>
      )}

      {!hasData ? (
        <EmptyState title="No shifts yet"
                    body="Advance the twin a shift or two and the breakdown will fill in." />
      ) : (
        <div className="grid gap-5 xl:grid-cols-[1.35fr_1fr]">
          <div className="space-y-5">
            {/* ── waterfall breakdown ── */}
            <section>
              <SectionTitle hint="Each bar is one term of the projection. The count comes from the model; the rate is your assumption.">
                Where the number comes from
              </SectionTitle>
              <Waterfall lines={lines} net={pnl.cumulative_net} currency={currency}
                         sources={pnl.latest?.sources ?? {}}
                         counts={pnl.cumulative_counts ?? {}} />
              <div className="mt-2.5 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-muted">
                <span className="flex items-center gap-1.5">
                  <span className="h-2.5 w-2.5 rounded-sm bg-ink/70" /> count from model output
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="h-2.5 w-2.5 rounded-sm bg-accent" /> rate is your assumption
                </span>
              </div>
            </section>

            {/* ── cumulative chart ── */}
            <section>
              <SectionTitle>Projected impact over the session</SectionTitle>
              <div className="card-solid p-3" style={{ height: 240 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={pnl.series.map((d, i) => ({ ...d, i: i + 1 }))}
                             margin={{ top: 8, right: 8, bottom: 4, left: 4 }}>
                    <defs>
                      <linearGradient id="cum" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#141414" stopOpacity={0.16} />
                        <stop offset="100%" stopColor="#141414" stopOpacity={0.01} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid stroke="#E2E0DC" vertical={false} />
                    <XAxis dataKey="i" tick={{ fontSize: 10, fill: "#8A8A8A" }}
                           stroke="#E2E0DC" tickLine={false} allowDecimals={false}
                           label={{ value: "shifts elapsed", position: "insideBottomRight",
                                    fontSize: 9, fill: "#8A8A8A", dy: 10 }} />
                    <YAxis tick={{ fontSize: 10, fill: "#8A8A8A" }} stroke="#E2E0DC"
                           tickLine={false} width={54}
                           tickFormatter={(v) => money(v, currency)} />
                    <Tooltip
                      contentStyle={{ borderRadius: 12, border: "1px solid #E2E0DC",
                                      fontSize: 12, fontFamily: "Inter" }}
                      formatter={(v) => [moneyExact(Number(v), currency), "Cumulative"]}
                      labelFormatter={(_l, payload) =>
                        `Shift ${payload?.[0]?.payload?.shift_id ?? "?"}`} />
                    <Area type="monotone" dataKey="cumulative" stroke="#141414" strokeWidth={1.6}
                          fill="url(#cum)" dot={false} isAnimationActive={false} />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </section>
          </div>

          <AssumptionsPanel pnl={pnl} pending={pending} setPending={setPending} />
        </div>
      )}
    </div>
  );
}

/* ── waterfall: credits up, debits down, net at the end ── */
function Waterfall({ lines, net, currency, sources, counts }: {
  lines: [string, number | null][];
  net: number; currency: string;
  sources: Record<string, { status: string; count_field?: string; formula?: string }>;
  /** cumulative counts — the amounts shown are cumulative, so the counts must be too */
  counts: Record<string, number>;
}) {
  const max = useMemo(
    () => Math.max(...lines.map(([, v]) => Math.abs(v ?? 0)), Math.abs(net), 1),
    [lines, net]);

  return (
    <div className="card-solid divide-y divide-hairline">
      {lines.map(([key, value]) => {
        const src = sources[key];
        const missing = value === null;
        const credit = (value ?? 0) >= 0;
        return (
          <div key={key} className="flex items-center gap-3 px-3.5 py-2.5">
            <div className="w-[190px] shrink-0">
              <p className="text-[12px] font-medium leading-tight">{humanise(key)}</p>
              <p className="font-mono text-[9.5px] leading-tight text-muted">
                {missing ? "missing assumption"
                  : src?.count_field
                    ? `${counts[src.count_field] ?? 0} × your rate`
                    : " "}
              </p>
            </div>
            <div className="relative h-5 flex-1 rounded-md bg-black/[.03]">
              {!missing && (
                <div
                  className={`absolute top-0 h-full rounded-md ${credit ? "bg-ink/70" : "bg-accent"}`}
                  style={{
                    width: `${(Math.abs(value!) / max) * 100}%`,
                    left: credit ? "0" : undefined,
                    right: credit ? undefined : "0",
                  }}
                />
              )}
            </div>
            <span className={`w-[92px] shrink-0 text-right font-mono text-[12px] tnum ${
              missing ? "text-muted" : credit ? "" : "text-accent"}`}>
              {missing ? "—" : moneyExact(value!, currency)}
            </span>
          </div>
        );
      })}
      <div className="flex items-center gap-3 bg-black/[.02] px-3.5 py-3">
        <span className="w-[190px] shrink-0 font-display text-[13px] font-medium">
          Net projected impact
        </span>
        <span className="flex-1" />
        <span className="w-[92px] shrink-0 text-right font-mono text-[15px] font-medium tnum">
          {moneyExact(net, currency)}
        </span>
      </div>
    </div>
  );
}
