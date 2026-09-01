/** Editable cost assumptions — the un-hardcoded core (§5.3).
 *  Optimistic UI, reconciled by the API response; the view re-projects with no
 *  model rerun because the backend recomputes from stored per-shift counts. */
import { useEffect, useState } from "react";

import { api } from "../lib/api";
import { humanise } from "../lib/format";
import type { PnL } from "../lib/types";
import { useTwin } from "../store/twin";
import { Info } from "./primitives";

const HELP: Record<string, string> = {
  downtime_cost_per_min: "What one minute of unplanned line stoppage costs you.",
  downtime_minutes_avoided_per_flag:
    "How many minutes of stoppage you expect to avoid each time you act on a bottleneck call.",
  scrap_cost_per_unit: "What one scrapped or reworked vehicle costs you.",
  avg_units_that_would_carry_it:
    "How many vehicles would have carried the defect before someone noticed it.",
  defect_caught_value: "What it is worth to catch one chained defect before it spreads.",
  inspection_cost_per_check: "What it costs to raise and carry out one extra inspection.",
  false_alarm_cost: "What it costs you when someone acts on a call that turns out to be wrong.",
  vehicles_per_shift: "Vehicles produced per shift. Used for extrapolation only.",
  shifts_per_day: "Shifts per production day. Used for extrapolation only.",
};

export function AssumptionsPanel({ pnl, pending, setPending }: {
  pnl: PnL; pending: boolean; setPending: (v: boolean) => void;
}) {
  const { refreshPnl, refreshConfig } = useTwin();
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setDraft(Object.fromEntries(
      Object.entries(pnl.assumptions).map(([k, v]) => [k, v === null ? "" : String(v)])));
  }, [pnl.assumptions]);

  const commit = async (key: string) => {
    const raw = draft[key];
    const value = Number(raw);
    if (raw === "" || Number.isNaN(value)) {
      setError(`${humanise(key)} needs a number.`);
      return;
    }
    if (value === pnl.assumptions[key]) return;
    setError(null);
    setPending(true);
    try {
      await api.updatePnlConfig({ [key]: value });
      await Promise.all([refreshPnl(), refreshConfig()]);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setDraft(d => ({ ...d, [key]: String(pnl.assumptions[key] ?? "") }));
    } finally {
      setPending(false);
    }
  };

  const resetAll = async () => {
    setPending(true);
    try {
      await api.resetPnlConfig();
      await Promise.all([refreshPnl(), refreshConfig()]);
    } finally { setPending(false); }
  };

  return (
    <aside className="card-solid h-fit p-4">
      <div className="flex items-baseline justify-between gap-2">
        <h2 className="font-display text-[15px] font-medium">Your assumptions</h2>
        <button onClick={resetAll} disabled={pending}
                className="text-[11px] text-muted underline underline-offset-2
                           transition-colors hover:text-ink disabled:opacity-40">
          Reset to defaults
        </button>
      </div>
      <p className="mt-1 text-[11.5px] leading-relaxed text-muted">
        These are yours to set — nothing here is measured or hardcoded. Change one and the
        projection updates straight away, without re-running any model.
      </p>

      {error && (
        <p role="alert" className="mt-2 rounded-lg border border-accent/30 bg-accent/[.06]
                                   px-2.5 py-1.5 text-[11.5px] text-accent">{error}</p>
      )}

      <div className="mt-3 space-y-2">
        {Object.keys(pnl.assumptions).map(key => (
          <label key={key} className="block">
            <span className="flex items-center text-[11.5px] text-muted">
              {humanise(key)}
              {HELP[key] && <Info term={humanise(key)}>{HELP[key]}</Info>}
            </span>
            <input
              type="number"
              inputMode="decimal"
              value={draft[key] ?? ""}
              disabled={pending}
              aria-label={humanise(key)}
              onChange={e => setDraft(d => ({ ...d, [key]: e.target.value }))}
              onBlur={() => commit(key)}
              onKeyDown={e => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }}
              className="mt-0.5 w-full rounded-lg border border-hairline bg-white px-2.5 py-1.5
                         font-mono text-[13px] tnum transition-colors focus:border-ink
                         disabled:opacity-50"
            />
          </label>
        ))}
      </div>

      {pnl.last_changed && (
        <p className="mt-3 border-t border-hairline pt-2.5 font-mono text-[10px] leading-relaxed
                      text-muted">
          Last changed {new Date(pnl.last_changed.at).toLocaleString()} by{" "}
          {pnl.last_changed.actor}.
        </p>
      )}
    </aside>
  );
}
