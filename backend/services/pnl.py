"""P&L engine — projected impact = model outputs x user assumptions.

Backend Instructions §7, formula from Architecture & Workflow §5.

Rules enforced here:
  - every term traces to either a model output or a NAMED config assumption
    (the `sources` map ships with every response);
  - a missing config field makes that line `null` with a missing_config flag —
    the engine never invents a value (Architecture §9);
  - cumulative is recomputed from STORED PER-SHIFT COUNTS, so editing an
    assumption re-projects history with no model rerun.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from backend.config.loader import Settings

DISCLAIMER = ("Projected impact = model outputs x your cost assumptions. "
              "These are projections, not measured savings.")


@dataclass
class ShiftCounts:
    """The REAL model outputs for one shift. Nothing here is an assumption."""
    shift_id: int
    confident_bottleneck_flags: int = 0
    defects_caught: int = 0
    chains_flagged: int = 0
    inspections_raised: int = 0
    low_confidence_acted: int = 0

    def as_dict(self) -> dict:
        return asdict(self)


# line -> (count field, [assumption fields], sign)
LINE_SPEC = {
    "value_from_bottleneck": (
        "confident_bottleneck_flags",
        ["downtime_minutes_avoided_per_flag", "downtime_cost_per_min"], +1),
    "value_from_defects": (
        "defects_caught",
        ["avg_units_that_would_carry_it", "scrap_cost_per_unit"], +1),
    "value_from_chains": (
        "chains_flagged", ["defect_caught_value"], +1),
    "cost_of_inspections": (
        "inspections_raised", ["inspection_cost_per_check"], -1),
    "cost_of_false_alarms": (
        "low_confidence_acted", ["false_alarm_cost"], -1),
}


class PnLEngine:
    def __init__(self, settings: Settings):
        self.settings = settings

    def compute(self, counts: ShiftCounts) -> dict:
        """One shift's breakdown. Returns every line item, the net and the sources map."""
        s = self.settings
        breakdown, sources, missing = {}, {}, []

        for line, (count_field, assumptions, sign) in LINE_SPEC.items():
            n = getattr(counts, count_field)
            vals, absent = [], []
            for a in assumptions:
                v = s.pnl_value(a)
                (absent if v is None else vals).append(a if v is None else v)
            if absent:
                # refuse to compute this line rather than assuming a value (§9)
                breakdown[line] = None
                missing.extend(absent)
                sources[line] = {"status": "missing_config", "missing": absent,
                                 "count_field": count_field, "count": n}
                continue
            amount = float(n) * sign
            for v in vals:
                amount *= float(v)
            breakdown[line] = round(amount, 2)
            sources[line] = {
                "status": "ok",
                "count_field": count_field,
                "count": n,
                "count_source": "model_output",
                "assumptions": {a: s.pnl_value(a) for a in assumptions},
                "assumption_source": "assumption",
                "sign": "credit" if sign > 0 else "debit",
                "formula": f"{count_field} x " + " x ".join(assumptions),
            }

        computed = [v for v in breakdown.values() if v is not None]
        net = round(sum(computed), 2)

        return {
            "shift_id": counts.shift_id,
            "counts": counts.as_dict(),
            "breakdown": breakdown,
            "net": net,
            "sources": sources,
            "missing_config": sorted(set(missing)),
            "complete": not missing,
            "currency": s.pnl.get("currency", "USD"),
            "is_projection": True,
            "disclaimer": DISCLAIMER,
        }

    def recompute_series(self, all_counts: list[ShiftCounts]) -> dict:
        """Re-project the whole session from stored counts (no model rerun) — §7."""
        series, cumulative = [], 0.0
        for c in all_counts:
            r = self.compute(c)
            cumulative = round(cumulative + r["net"], 2)
            series.append({"shift_id": c.shift_id, "net": r["net"],
                           "cumulative": cumulative, "breakdown": r["breakdown"],
                           "complete": r["complete"]})
        latest = self.compute(all_counts[-1]) if all_counts else None
        totals: dict = {}
        for line in LINE_SPEC:
            vals = [s["breakdown"][line] for s in series if s["breakdown"][line] is not None]
            totals[line] = round(sum(vals), 2) if vals else None
        return {
            "latest": latest,
            "series": series,
            "cumulative_net": cumulative,
            "cumulative_breakdown": totals,
            "shifts_counted": len(series),
            "assumptions": {k: self.settings.pnl_value(k) for k in Settings.PNL_REQUIRED},
            "missing_config": self.settings.missing_pnl_fields(),
            "currency": self.settings.pnl.get("currency", "USD"),
            "is_projection": True,
            "disclaimer": DISCLAIMER,
        }

    def sensitivity(self, all_counts: list[ShiftCounts], key: str, pct: float = 0.2) -> dict:
        """'if <key> +/- pct, net moves to X-Y' — the §5.3 mini-view."""
        base = self.settings.pnl_value(key)
        if base is None:
            return {"key": key, "status": "missing_config"}
        original = dict(self.settings.pnl)
        out = {}
        try:
            for label, factor in (("low", 1 - pct), ("high", 1 + pct)):
                self.settings.pnl = {**original, key: base * factor}
                out[label] = self.recompute_series(all_counts)["cumulative_net"]
        finally:
            self.settings.pnl = original
        return {"key": key, "base_value": base, "pct": pct,
                "cumulative_low": out["low"], "cumulative_high": out["high"],
                "cumulative_base": self.recompute_series(all_counts)["cumulative_net"],
                "disclaimer": DISCLAIMER}
