/** Typed REST client. Every domain value the UI shows comes through here. */
import type {
  ConfigPayload, DefectEvent, DetectorStatus, Health, History, Line, PnL, TwinState,
} from "./types";

const BASE = import.meta.env.VITE_API_BASE ?? "";

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? body.error ?? detail;
    } catch { /* keep statusText */ }
    throw new Error(`${res.status} ${detail}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => req<Health>("/health"),
  line: () => req<Line>("/line"),
  config: () => req<ConfigPayload>("/config"),
  pnl: (key?: string) =>
    req<PnL>(`/pnl${key ? `?sensitivity_key=${encodeURIComponent(key)}` : ""}`),
  history: () => req<History>("/history"),
  twinStates: (limit = 50) =>
    req<{ twin_states: TwinState[] }>(`/twin/state?limit=${limit}`),
  twinState: (vehicleId: number) => req<TwinState>(`/twin/state/${vehicleId}`),
  alerts: (limit = 50) => req<{ alerts: TwinState["downstream_inspection_alerts"] }>(
    `/alerts?limit=${limit}`),
  detections: (limit = 60) =>
    req<{ detections: DefectEvent[]; detector: DetectorStatus }>(`/detections?limit=${limit}`),

  updatePnlConfig: (values: Record<string, number>, note?: string) =>
    req<{ ok: boolean; cumulative_net: number; missing_config: string[] }>(
      "/config/pnl", { method: "POST", body: JSON.stringify({ values, note }) }),
  resetPnlConfig: () => req<{ ok: boolean }>("/pnl/config/reset", { method: "POST" }),
  updateMappings: (body: Record<string, unknown>) =>
    req<{ ok: boolean }>("/config/mappings", { method: "POST", body: JSON.stringify(body) }),

  tick: () => req<unknown>("/control/tick", { method: "POST" }),
  play: (interval_s?: number) =>
    req<{ playing: boolean; interval_s: number }>(
      "/control/play", { method: "POST", body: JSON.stringify({ interval_s }) }),
  pause: () => req<{ playing: boolean }>("/control/pause", { method: "POST" }),
  reset: () => req<unknown>("/control/reset", { method: "POST" }),
};

export function wsUrl(): string {
  if (import.meta.env.VITE_WS_URL) return import.meta.env.VITE_WS_URL as string;
  const base = BASE || window.location.origin;
  return base.replace(/^http/, "ws") + "/ws/live";
}
