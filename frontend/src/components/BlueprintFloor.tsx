/** BlueprintFloor — the hero. A stylised isometric schematic generated from the
 *  /line topology payload (Frontend Instructions §5.1 + the honest-rendering note:
 *  this is a drawing built from data, NOT a 3D scan of a real plant).
 *
 *  Nothing here hardcodes a station count: rows, columns and every marker derive
 *  from the nodes and edges the API returns. */
import { useMemo, useRef, useState } from "react";

import type { BottleneckState, ChainAlert, Line, LineNode } from "../lib/types";
import { stationStatus, type StationStatus } from "../store/twin";
import { STATUS_META, StatusDot } from "./primitives";

/* isometric projection */
const TILE_W = 116;
const TILE_H = 58;
const ROW_GAP = 132;
const ORIGIN = { x: 520, y: 150 };

function iso(col: number, row: number) {
  return {
    x: ORIGIN.x + (col - row) * (TILE_W / 2),
    y: ORIGIN.y + (col + row) * (TILE_H / 2) + row * (ROW_GAP - TILE_H),
  };
}

export interface Placed extends LineNode { px: number; py: number; col: number; row: number }

/** Lay the line out as one serpentine row per zone, so it reads as a floor plan. */
export function layout(line: Line): Placed[] {
  const zoneOrder = Object.keys(line.zones);
  const perZone: Record<string, LineNode[]> = {};
  for (const n of line.nodes) (perZone[n.zone] ??= []).push(n);

  const out: Placed[] = [];
  zoneOrder.forEach((zone, row) => {
    const nodes = (perZone[zone] ?? []).sort((a, b) => a.station_id - b.station_id);
    nodes.forEach((n, i) => {
      // alternate direction per row: the material physically snakes back
      const col = row % 2 === 0 ? i : nodes.length - 1 - i;
      const { x, y } = iso(col, row);
      out.push({ ...n, px: x, py: y, col, row });
    });
  });
  return out.sort((a, b) => a.station_id - b.station_id);
}

interface Props {
  line: Line;
  bottleneck: BottleneckState | null;
  alerts: ChainAlert[];
  selected: number | null;
  onSelect: (id: number | null) => void;
}

export function BlueprintFloor({ line, bottleneck, alerts, selected, onSelect }: Props) {
  const [view, setView] = useState({ x: 0, y: 0, k: 0.78 });
  const drag = useRef<{ x: number; y: number; ox: number; oy: number } | null>(null);
  const placed = useMemo(() => layout(line), [line]);
  const byId = useMemo(() => new Map(placed.map(p => [p.station_id, p])), [placed]);

  const bounds = useMemo(() => {
    const xs = placed.map(p => p.px), ys = placed.map(p => p.py);
    return { minX: Math.min(...xs) - 140, maxX: Math.max(...xs) + 140,
             minY: Math.min(...ys) - 130, maxY: Math.max(...ys) + 130 };
  }, [placed]);

  /* stations that a chain alert points downstream from, for the trace */
  const traced = useMemo(() => {
    const set = new Set<number>();
    for (const a of alerts.slice(0, 6)) set.add(a.origin_station);
    return set;
  }, [alerts]);

  const nudge = (dx: number, dy: number) =>
    setView(v => ({ ...v, x: v.x + dx, y: v.y + dy }));
  const zoom = (f: number) =>
    setView(v => ({ ...v, k: Math.min(1.8, Math.max(0.4, v.k * f)) }));

  const onDown = (e: React.PointerEvent) => {
    drag.current = { x: e.clientX, y: e.clientY, ox: view.x, oy: view.y };
    (e.target as Element).setPointerCapture?.(e.pointerId);
  };
  const onMove = (e: React.PointerEvent) => {
    if (!drag.current) return;
    setView(v => ({ ...v,
      x: drag.current!.ox + (e.clientX - drag.current!.x),
      y: drag.current!.oy + (e.clientY - drag.current!.y) }));
  };
  const onUp = () => { drag.current = null; };

  const vb = `${bounds.minX} ${bounds.minY} ${bounds.maxX - bounds.minX} ${bounds.maxY - bounds.minY}`;

  return (
    <div className="relative h-full w-full overflow-hidden rounded-card bg-gradient-to-b
                    from-[#FBFBFA] to-[#F1EFEC]">
      <svg
        className="h-full w-full cursor-grab touch-none active:cursor-grabbing"
        viewBox={vb}
        preserveAspectRatio="xMidYMid meet"
        role="img"
        aria-label={`Schematic of the ${line.n_stations}-station assembly line`}
        onPointerDown={onDown} onPointerMove={onMove}
        onPointerUp={onUp} onPointerLeave={onUp}
      >
        <defs>
          <pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">
            <path d="M40 0H0v40" fill="none" stroke="#E6E3DE" strokeWidth="0.6" />
          </pattern>
          <marker id="arrow" viewBox="0 0 8 8" refX="7" refY="4"
                  markerWidth="5" markerHeight="5" orient="auto-start-reverse">
            <path d="M0 1.2 7 4 0 6.8z" fill="#C9C6C0" />
          </marker>
          <marker id="arrowAccent" viewBox="0 0 8 8" refX="7" refY="4"
                  markerWidth="5" markerHeight="5" orient="auto-start-reverse">
            <path d="M0 1.2 7 4 0 6.8z" fill="#F0552B" />
          </marker>
        </defs>

        <g transform={`translate(${view.x} ${view.y}) scale(${view.k})
                       translate(${(1 - 1) * 0} 0)`}
           style={{ transformOrigin: "center" }}>
          <rect x={bounds.minX} y={bounds.minY} width={bounds.maxX - bounds.minX}
                height={bounds.maxY - bounds.minY} fill="url(#grid)" opacity={0.55} />

          {/* zone bands + labels */}
          {Object.entries(line.zones).map(([zone, z], row) => {
            const nodes = placed.filter(p => p.zone === zone);
            if (!nodes.length) return null;
            const xs = nodes.map(n => n.px), ys = nodes.map(n => n.py);
            return (
              <g key={zone}>
                <rect
                  x={Math.min(...xs) - 70} y={Math.min(...ys) - 46}
                  width={Math.max(...xs) - Math.min(...xs) + 140}
                  height={Math.max(...ys) - Math.min(...ys) + 92}
                  rx="18" fill="#141414" opacity={row % 2 ? 0.018 : 0.032}
                  stroke="#E2E0DC" strokeWidth="1"
                />
                <text
                  x={Math.min(...xs) - 62} y={Math.min(...ys) - 54}
                  className="font-mono" fontSize="11" fill="#8A8A8A"
                  letterSpacing="1.6"
                >
                  {z.label.toUpperCase()} · S{z.start}–S{z.end}
                </text>
              </g>
            );
          })}

          {/* edges: serial hairlines, bypass and rework drawn as real arcs */}
          <g>
            {line.edges.map((e, i) => {
              const a = byId.get(e.source), b = byId.get(e.target);
              if (!a || !b) return null;
              const isSpecial = e.kind !== "serial";
              const dy = b.py - a.py;
              const bow = e.kind === "rework" ? -62 : e.kind === "bypass" ? -46 : 0;
              const mx = (a.px + b.px) / 2 + (bow ? -dy * 0.16 : 0);
              const my = (a.py + b.py) / 2 + bow;
              const d = isSpecial
                ? `M${a.px} ${a.py} Q${mx} ${my} ${b.px} ${b.py}`
                : `M${a.px} ${a.py} L${b.px} ${b.py}`;
              return (
                <path
                  key={i} d={d} fill="none"
                  stroke={isSpecial ? "#9A9793" : "#C9C6C0"}
                  strokeWidth={isSpecial ? 1.3 : 1 + e.weight * 1.6}
                  strokeDasharray={e.kind === "rework" ? "5 4" : e.kind === "bypass" ? "3 3" : undefined}
                  markerEnd={isSpecial ? "url(#arrow)" : undefined}
                  opacity={isSpecial ? 0.85 : 0.7}
                />
              );
            })}
          </g>

          {/* labels for the two structural exceptions — they explain the drawing */}
          {(() => {
            const bypass = line.edges.find(e => e.kind === "bypass");
            const rework = line.edges.find(e => e.kind === "rework");
            const tag = (e: typeof bypass, text: string, key: string) => {
              if (!e) return null;
              const a = byId.get(e.source), b = byId.get(e.target);
              if (!a || !b) return null;
              return (
                <text key={key} x={(a.px + b.px) / 2} y={(a.py + b.py) / 2 - 56}
                      textAnchor="middle" className="font-mono" fontSize="9.5"
                      fill="#8A8A8A" letterSpacing="0.6">
                  {text}
                </text>
              );
            };
            return <>
              {tag(bypass, `bypass S${bypass?.source}→S${bypass?.target}`, "bp")}
              {tag(rework, `rework loop S${rework?.source}→S${rework?.target}`, "rw")}
            </>;
          })()}

          {/* stations */}
          {placed.map(n => {
            const status = stationStatus(n.station_id, bottleneck, n.sensor_poor);
            const isBn = status === "bottleneck";
            const isSel = selected === n.station_id;
            const hasChain = traced.has(n.station_id);
            return (
              <StationMarker
                key={n.station_id} node={n} status={status} isBottleneck={isBn}
                selected={isSel} hasChain={hasChain}
                onSelect={() => onSelect(isSel ? null : n.station_id)}
              />
            );
          })}
        </g>
      </svg>

      {/* legend */}
      <div className="pointer-events-none absolute left-4 top-4 flex flex-wrap gap-x-3 gap-y-1
                      rounded-xl border border-white/60 bg-white/70 px-3 py-2 backdrop-blur">
        {["running", "watch", "bottleneck", "sensor-poor"].map(k => (
          <span key={k} className="flex items-center gap-1.5 text-[10px] text-muted">
            <StatusDot status={k} size={6} />{STATUS_META[k].label}
          </span>
        ))}
      </div>

      <PanZoomControls onNudge={nudge} onZoom={zoom}
                       onReset={() => setView({ x: 0, y: 0, k: 0.78 })} />

      <p className="pointer-events-none absolute bottom-3 right-4 max-w-[240px] text-right
                    font-mono text-[9px] leading-snug text-muted/80">
        Schematic drawn from the /line topology. Not a scan of a physical plant.
      </p>
    </div>
  );
}

/* ── one station on the floor ── */
function StationMarker({ node, status, isBottleneck, selected, hasChain, onSelect }: {
  node: Placed; status: StationStatus; isBottleneck: boolean;
  selected: boolean; hasChain: boolean; onSelect: () => void;
}) {
  const meta = STATUS_META[status];
  const label = `Station S${node.station_id}, ${node.zone_label}, ${meta.label}`;
  return (
    <g
      transform={`translate(${node.px} ${node.py})`}
      className="cursor-pointer"
      role="button" tabIndex={0} aria-label={label}
      onClick={(e) => { e.stopPropagation(); onSelect(); }}
      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onSelect(); } }}
    >
      {/* machine footprint — thin architectural line-work */}
      <path d={`M0 -${TILE_H / 2} L${TILE_W / 2} 0 L0 ${TILE_H / 2} L-${TILE_W / 2} 0 Z`}
            fill={selected ? "#FFFFFF" : "#FBFAF9"}
            stroke={selected ? "#141414" : "#C9C6C0"}
            strokeWidth={selected ? 1.5 : 1} opacity={0.95} />
      <path d={`M-${TILE_W / 2} 0 L-${TILE_W / 2} 13 L0 ${TILE_H / 2 + 13} L0 ${TILE_H / 2} Z`}
            fill="#EEEBE7" stroke="#C9C6C0" strokeWidth="0.8" />
      <path d={`M${TILE_W / 2} 0 L${TILE_W / 2} 13 L0 ${TILE_H / 2 + 13} L0 ${TILE_H / 2} Z`}
            fill="#E5E2DD" stroke="#C9C6C0" strokeWidth="0.8" />
      {/* a small machine block, so the tile reads as equipment not a floor tile */}
      <path d={`M0 -16 L22 -5 L0 6 L-22 -5 Z`} fill="#FFFFFF" stroke="#D5D2CD" strokeWidth="0.9" />
      <path d="M-22 -5 L-22 2 L0 13 L0 6 Z" fill="#EDEAE6" stroke="#D5D2CD" strokeWidth="0.7" />
      <path d="M22 -5 L22 2 L0 13 L0 6 Z" fill="#E4E1DC" stroke="#D5D2CD" strokeWidth="0.7" />

      {/* chain trace: a caught defect points downstream */}
      {hasChain && !isBottleneck && (
        <circle r="17" fill="none" stroke="#F0552B" strokeWidth="1.1"
                strokeDasharray="4 4" opacity="0.75" className="animate-dash" />
      )}

      {/* status dot sits ON the machine, Velluto-style */}
      {isBottleneck && (
        <circle cx="0" cy="-26" r="5" fill={meta.color} opacity="0.5"
                className="animate-pulseRing" style={{ transformOrigin: "0px -26px" }} />
      )}
      <circle cx="0" cy="-26" r="4.5" fill={meta.color}
              stroke="#FFFFFF" strokeWidth="1.4" />

      <text y="-36" textAnchor="middle" className="font-mono pointer-events-none"
            fontSize="10.5" fill={isBottleneck ? "#F0552B" : "#5C5A56"}
            fontWeight={isBottleneck ? 500 : 400}>
        S{node.station_id}
      </text>
      {node.sensor_poor && (
        <text y="30" textAnchor="middle" className="font-mono pointer-events-none"
              fontSize="8" fill="#B6B3AD">sensor-poor</text>
      )}
    </g>
  );
}

/* ── PanZoomControls ── */
function PanZoomControls({ onNudge, onZoom, onReset }: {
  onNudge: (dx: number, dy: number) => void;
  onZoom: (f: number) => void;
  onReset: () => void;
}) {
  const b = "grid h-7 w-7 place-items-center rounded-lg border border-hairline bg-white/80 " +
            "text-[13px] leading-none text-ink backdrop-blur transition-colors hover:bg-white";
  const STEP = 70;
  return (
    <div className="absolute bottom-4 left-4 flex items-end gap-2">
      <div className="grid grid-cols-3 grid-rows-3 gap-1">
        <span /><button className={b} onClick={() => onNudge(0, STEP)} aria-label="Pan up">↑</button><span />
        <button className={b} onClick={() => onNudge(STEP, 0)} aria-label="Pan left">←</button>
        <button className={b} onClick={onReset} aria-label="Reset view" title="Reset view">·</button>
        <button className={b} onClick={() => onNudge(-STEP, 0)} aria-label="Pan right">→</button>
        <span /><button className={b} onClick={() => onNudge(0, -STEP)} aria-label="Pan down">↓</button><span />
      </div>
      <div className="flex flex-col gap-1">
        <button className={b} onClick={() => onZoom(1.22)} aria-label="Zoom in">+</button>
        <button className={b} onClick={() => onZoom(1 / 1.22)} aria-label="Zoom out">−</button>
      </div>
    </div>
  );
}
