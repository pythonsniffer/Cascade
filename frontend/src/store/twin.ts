/** Central live store — one WebSocket client, one source of truth for the UI.
 *  Frontend Instructions §7: current shift, line state, alerts, latest P&L,
 *  connection status. No polling. */
import { create } from "zustand";

import { api, wsUrl } from "../lib/api";
import type {
  BottleneckState, ChainAlert, ConfigPayload, DefectEvent, Health, Line, PnL,
  TickMessage, TwinState, WsMessage,
} from "../lib/types";

const MAX_ALERTS = 60;
const MAX_TWIN = 80;
const MAX_EVENTS = 120;

export type Connection = "connecting" | "open" | "closed";

interface TwinStore {
  // static-ish, loaded once
  health: Health | null;
  line: Line | null;
  config: ConfigPayload | null;
  bootError: string | null;

  // live
  connection: Connection;
  playing: boolean;
  intervalS: number;
  tickCount: number;
  shiftId: number | null;
  shiftName: string | null;
  bottleneck: BottleneckState | null;
  twinStates: TwinState[];
  alerts: ChainAlert[];
  detections: DefectEvent[];
  pnl: PnL | null;
  latestNet: number | null;
  cumulativeNet: number;
  lastMeta: Record<string, unknown> | null;
  /** stations touched by the most recent chain, for the downstream trace animation */
  chainTrace: { from: number; to: number[] } | null;

  // ui
  selectedStation: number | null;
  selectedVehicle: number | null;

  boot: () => Promise<void>;
  connect: () => void;
  disconnect: () => void;
  refreshPnl: () => Promise<void>;
  refreshConfig: () => Promise<void>;
  selectStation: (id: number | null) => void;
  selectVehicle: (id: number | null) => void;
}

let socket: WebSocket | null = null;
let retry = 0;
let retryTimer: ReturnType<typeof setTimeout> | null = null;
let closedByUs = false;

export const useTwin = create<TwinStore>((set, get) => ({
  health: null, line: null, config: null, bootError: null,
  connection: "connecting", playing: false, intervalS: 2, tickCount: 0,
  shiftId: null, shiftName: null, bottleneck: null,
  twinStates: [], alerts: [], detections: [], pnl: null,
  latestNet: null, cumulativeNet: 0, lastMeta: null, chainTrace: null,
  selectedStation: null, selectedVehicle: null,

  boot: async () => {
    try {
      const [health, line, config, pnl] = await Promise.all([
        api.health(), api.line(), api.config(), api.pnl(),
      ]);
      set({
        health, line, config, pnl, bootError: null,
        playing: health.playing, intervalS: health.interval_s,
        tickCount: health.tick_count, cumulativeNet: pnl.cumulative_net,
      });
      // seed from history so a page reload doesn't look like an empty line
      const [{ twin_states, last_tick }, { detections }] = await Promise.all([
        api.twinStates(MAX_TWIN), api.detections(MAX_EVENTS),
      ]);
      const seededAlerts = twin_states.flatMap(t =>
        t.downstream_inspection_alerts.map(a => ({
          ...a, vehicle_id: t.vehicle_id, shift_id: t.shift_id, timestamp: t.timestamp })));
      set({
        twinStates: twin_states, detections,
        alerts: seededAlerts.slice(0, MAX_ALERTS),
      });
      // Prefer last_tick: it carries the per-station blk/stv arrays, so a reload
      // shows the same station detail as a live tick instead of "no forecast yet".
      if (last_tick) {
        set({
          shiftId: last_tick.shift_id, shiftName: last_tick.shift_name,
          bottleneck: last_tick.bottleneck, lastMeta: last_tick._meta,
          latestNet: last_tick.pnl_delta?.net ?? null,
        });
      } else if (twin_states[0]) {
        const last = twin_states[0];
        set({
          shiftId: last.shift_id ?? null,
          bottleneck: {
            station: last.bottleneck_station, zone: last.bottleneck_zone,
            confidence: last.bottleneck_confidence ?? "warming_up",
            uncertainty: null, abstained: last.bottleneck_abstained ?? true,
            blk: null, stv: null,
          },
        });
      }
    } catch (e) {
      set({ bootError: e instanceof Error ? e.message : String(e) });
    }
  },

  connect: () => {
    closedByUs = false;
    if (socket && (socket.readyState === WebSocket.OPEN ||
                   socket.readyState === WebSocket.CONNECTING)) return;
    set({ connection: "connecting" });
    const ws = new WebSocket(wsUrl());
    socket = ws;

    ws.onopen = () => { retry = 0; set({ connection: "open" }); };

    ws.onmessage = (ev) => {
      let msg: WsMessage;
      try { msg = JSON.parse(ev.data); } catch { return; }
      if (msg.type === "ping") return;

      if (msg.type === "status") {
        set({ playing: msg.playing, intervalS: msg.interval_s, tickCount: msg.tick_count });
        if (msg.state === "reset") {
          set({
            twinStates: [], alerts: [], detections: [], bottleneck: null,
            latestNet: null, cumulativeNet: 0, shiftId: null, shiftName: null,
            chainTrace: null, selectedVehicle: null,
          });
          void get().refreshPnl();
        }
        return;
      }

      const tick = msg as TickMessage;
      const trace = tick.new_alerts.length
        ? { from: tick.new_alerts[0].origin_station,
            to: tick.new_alerts.map(a => a.origin_station) }
        : null;
      set(s => ({
        shiftId: tick.shift_id,
        shiftName: tick.shift_name,
        tickCount: tick.tick_count,
        bottleneck: tick.bottleneck,
        twinStates: [...tick.twin_states, ...s.twinStates].slice(0, MAX_TWIN),
        alerts: [...tick.new_alerts, ...s.alerts].slice(0, MAX_ALERTS),
        detections: [...tick.defect_events, ...s.detections].slice(0, MAX_EVENTS),
        latestNet: tick.pnl_delta.net,
        cumulativeNet: tick.pnl_delta.cumulative ?? s.cumulativeNet,
        lastMeta: tick._meta,
        chainTrace: trace ?? s.chainTrace,
      }));
    };

    ws.onclose = () => {
      set({ connection: "closed" });
      if (closedByUs) return;
      // exponential backoff, capped — a paused demo shouldn't hammer the backend
      const delay = Math.min(1000 * 2 ** retry++, 15000);
      retryTimer = setTimeout(() => get().connect(), delay);
    };
    ws.onerror = () => ws.close();
  },

  disconnect: () => {
    closedByUs = true;
    if (retryTimer) clearTimeout(retryTimer);
    socket?.close();
    socket = null;
  },

  refreshPnl: async () => {
    const pnl = await api.pnl();
    set({ pnl, cumulativeNet: pnl.cumulative_net });
  },
  refreshConfig: async () => set({ config: await api.config() }),
  selectStation: (id) => set({ selectedStation: id }),
  selectVehicle: (id) => set({ selectedVehicle: id }),
}));

/** Derived: per-station status for the floor and the strip.
 *  Status comes from the model's own outputs — never invented. */
export type StationStatus = "bottleneck" | "watch" | "running" | "sensor-poor" | "idle";

export function stationStatus(
  stationId: number,
  bottleneck: BottleneckState | null,
  sensorPoor: boolean,
): StationStatus {
  if (!bottleneck || bottleneck.confidence === "warming_up") {
    return sensorPoor ? "sensor-poor" : "idle";
  }
  if (!bottleneck.abstained && bottleneck.station === stationId) return "bottleneck";
  if (sensorPoor) return "sensor-poor";
  const blk = bottleneck.blk?.[stationId];
  const stv = bottleneck.stv?.[stationId];
  if (blk === undefined || stv === undefined) return "idle";
  // "watch" = this station's predicted congestion sits in the top decile of the line
  const all = (bottleneck.blk ?? []).map((b, i) => b + (bottleneck.stv?.[i] ?? 0));
  const sorted = [...all].sort((a, b) => b - a);
  const cutoff = sorted[Math.max(0, Math.floor(sorted.length * 0.1) - 1)] ?? Infinity;
  return blk + stv >= cutoff ? "watch" : "running";
}
