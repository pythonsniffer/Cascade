/** Shared UI primitives. Plain language first; every technical term gets a tooltip
 *  (Frontend Instructions §3.5 / §8). */
import { useState, type ReactNode } from "react";

import type { Confidence } from "../lib/types";

/* ── Tooltip ─────────────────────────────────────────────────────────── */
export function Info({ term, children }: { term: string; children: ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <span className="relative inline-flex items-center">
      <button
        type="button"
        aria-label={`What does "${term}" mean?`}
        aria-expanded={open}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onClick={(e) => { e.stopPropagation(); setOpen(v => !v); }}
        className="ml-1 grid h-3.5 w-3.5 place-items-center rounded-full border border-hairline
                   text-[8px] font-medium text-muted transition-colors hover:border-muted
                   hover:text-ink"
      >
        i
      </button>
      {open && (
        <span
          role="tooltip"
          className="absolute bottom-full left-1/2 z-50 mb-2 w-56 -translate-x-1/2 rounded-xl
                     border border-hairline bg-ink px-3 py-2 text-[11px] font-normal leading-snug
                     text-white shadow-float animate-fadeIn"
        >
          {children}
        </span>
      )}
    </span>
  );
}

/* ── Confidence pill ─────────────────────────────────────────────────── */
const CONFIDENCE_COPY: Record<string, { label: string; help: string; tone: string }> = {
  high: {
    label: "Confident call",
    tone: "bg-accent/10 text-accent border-accent/25",
    help: "The three forecasters agree closely, so the model is naming a station.",
  },
  low: {
    label: "No confident call",
    tone: "bg-black/[.04] text-muted border-hairline",
    help: "The forecasters disagreed, so the model abstained rather than guess a station.",
  },
  warming_up: {
    label: "Warming up",
    tone: "bg-black/[.04] text-muted border-hairline",
    help: "The model needs a few shifts of history before it can forecast. It is not predicting yet.",
  },
};

export function ConfidencePill({ confidence, abstained }: {
  confidence: Confidence | null; abstained?: boolean | null;
}) {
  const key = confidence ?? "warming_up";
  const c = CONFIDENCE_COPY[key] ?? CONFIDENCE_COPY.warming_up;
  const label = key === "high" && abstained ? "Abstained" : c.label;
  return (
    <span className={`pill border ${c.tone}`}>
      {label}
      <Info term={label}>{c.help}</Info>
    </span>
  );
}

/* ── Status dot ──────────────────────────────────────────────────────── */
export const STATUS_META: Record<string, { label: string; color: string; help: string }> = {
  bottleneck: {
    label: "Bottleneck", color: "#F0552B",
    help: "The model expects this station to slow the line next shift.",
  },
  watch: {
    label: "Watch", color: "#D8A138",
    help: "Predicted congestion here is among the highest on the line, but it is not the bottleneck.",
  },
  running: {
    label: "Running", color: "#4B9B6E",
    help: "Normal predicted flow — nothing to act on.",
  },
  "sensor-poor": {
    label: "Sensor-poor", color: "#B6B3AD",
    help: "This station has sparse instrumentation, so its readings are less reliable.",
  },
  idle: {
    label: "Idle", color: "#B6B3AD",
    help: "No forecast yet for this station.",
  },
};

export function StatusDot({ status, size = 8, pulse = false }: {
  status: string; size?: number; pulse?: boolean;
}) {
  const meta = STATUS_META[status] ?? STATUS_META.idle;
  return (
    <span className="relative inline-flex shrink-0" style={{ width: size, height: size }}>
      {pulse && (
        <span
          className="absolute inset-0 rounded-full animate-pulseRing"
          style={{ background: meta.color }}
        />
      )}
      <span
        className="relative rounded-full"
        style={{ width: size, height: size, background: meta.color }}
      />
    </span>
  );
}

/* ── Section heading ─────────────────────────────────────────────────── */
export function SectionTitle({ children, hint, right }: {
  children: ReactNode; hint?: ReactNode; right?: ReactNode;
}) {
  return (
    <div className="mb-3 flex items-baseline justify-between gap-3">
      <h2 className="font-display text-[15px] font-medium tracking-tight">
        {children}
        {hint && <Info term={String(children)}>{hint}</Info>}
      </h2>
      {right}
    </div>
  );
}

/* ── Empty / degraded states — never a zero-defect claim ─────────────── */
export function EmptyState({ title, body, tone = "neutral" }: {
  title: string; body: ReactNode; tone?: "neutral" | "warn";
}) {
  return (
    <div className={`rounded-card border border-dashed p-5 text-center ${
      tone === "warn" ? "border-accent/30 bg-accent/[.03]" : "border-hairline bg-black/[.015]"}`}>
      <p className="font-display text-[13px] font-medium">{title}</p>
      <p className="mx-auto mt-1 max-w-md text-[12px] leading-relaxed text-muted">{body}</p>
    </div>
  );
}
