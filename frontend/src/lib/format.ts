/** Presentation helpers. No domain values — currency and labels come from the API. */

export function money(v: number | null | undefined, currency = "USD"): string {
  if (v === null || v === undefined) return "—";
  const abs = Math.abs(v);
  const sign = v < 0 ? "−" : "";
  const fmt = (n: number, d = 0) =>
    n.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
  const symbol = { USD: "$", EUR: "€", GBP: "£", INR: "₹" }[currency] ?? "";
  if (abs >= 1_000_000) return `${sign}${symbol}${fmt(abs / 1_000_000, 2)}M`;
  if (abs >= 10_000) return `${sign}${symbol}${fmt(abs / 1000, 1)}k`;
  return `${sign}${symbol}${fmt(abs)}`;
}

export function moneyExact(v: number | null | undefined, currency = "USD"): string {
  if (v === null || v === undefined) return "—";
  const symbol = { USD: "$", EUR: "€", GBP: "£", INR: "₹" }[currency] ?? "";
  const sign = v < 0 ? "−" : "";
  return `${sign}${symbol}${Math.abs(v).toLocaleString("en-US", {
    minimumFractionDigits: 0, maximumFractionDigits: 0 })}`;
}

/** "value_from_bottleneck" → "Value from bottleneck" */
export function humanise(key: string): string {
  const s = key.replace(/_/g, " ");
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export function stationLabel(id: number | null | undefined): string {
  return id === null || id === undefined ? "—" : `S${id}`;
}

export function zoneLabel(zone: string | null | undefined): string {
  if (!zone) return "—";
  return zone.split("_").map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(" ");
}

export function timeAgo(iso: string | undefined): string {
  if (!iso) return "";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const secs = Math.max(0, Math.round((Date.now() - then) / 1000));
  if (secs < 60) return `${secs}s ago`;
  if (secs < 3600) return `${Math.round(secs / 60)}m ago`;
  return `${Math.round(secs / 3600)}h ago`;
}

export function pct(v: number | null | undefined, digits = 0): string {
  return v === null || v === undefined ? "—" : `${(v * 100).toFixed(digits)}%`;
}
