/** AppShell — left icon rail + top bar + honesty strip (Frontend Instructions §6). */
import { NavLink, useLocation } from "react-router-dom";
import { useEffect, useState } from "react";

import { api } from "../lib/api";
import { useTwin } from "../store/twin";

const NAV = [
  { to: "/", label: "Live twin", icon: FloorIcon,
    hint: "The line right now: predicted bottleneck, alerts and station detail." },
  { to: "/quality", label: "Quality", icon: LensIcon,
    hint: "Camera detections, defect chains and the detector's model card." },
  { to: "/pnl", label: "Profit & loss", icon: CoinIcon,
    hint: "What the predictions are projected to be worth, using your cost assumptions." },
  { to: "/history", label: "History", icon: TrendIcon,
    hint: "How bottlenecks, defects and projected impact moved over the session." },
  { to: "/config", label: "Settings", icon: GearIcon,
    hint: "Cost assumptions, camera mapping and the tick controls." },
];

const TITLES: Record<string, string> = {
  "/": "Production line", "/quality": "Quality", "/pnl": "Profit & loss",
  "/history": "History", "/config": "Settings",
};

export function AppShell({ children }: { children: React.ReactNode }) {
  const { pathname } = useLocation();
  const { connection, playing, tickCount } = useTwin();
  const [now, setNow] = useState(new Date());

  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  return (
    <div className="flex h-full min-h-0">
      {/* ── left icon rail ── */}
      <nav
        aria-label="Main"
        className="z-30 flex w-[60px] shrink-0 flex-col items-center gap-1 border-r border-hairline
                   bg-surface/80 py-4 backdrop-blur"
      >
        <NavLink to="/" aria-label="Cascade home" className="mb-3 block">
          <Logo />
        </NavLink>
        {NAV.map(({ to, label, icon: Icon, hint }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            title={`${label} — ${hint}`}
            aria-label={label}
            className={({ isActive }) =>
              `group relative grid h-10 w-10 place-items-center rounded-xl transition-colors ${
                isActive ? "bg-accent/10 text-accent" : "text-muted hover:bg-black/[.04] hover:text-ink"}`
            }
          >
            <Icon />
          </NavLink>
        ))}
      </nav>

      <div className="flex min-w-0 flex-1 flex-col">
        {/* ── top bar ── */}
        <header className="z-20 flex shrink-0 items-center gap-4 border-b border-hairline
                           bg-surface/70 px-5 py-3 backdrop-blur">
          <h1 className="font-display text-[17px] font-medium tracking-tight">
            {TITLES[pathname] ?? "Cascade"}
          </h1>
          <LivePill connection={connection} playing={playing} />
          <span className="hidden font-mono text-[11px] text-muted sm:inline tnum">
            {now.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" })}
            {" · "}
            {now.toLocaleTimeString(undefined, { hour12: false })}
          </span>

          <div className="ml-auto flex items-center gap-1.5">
            <TickControls />
            <span className="ml-2 hidden items-center gap-2 border-l border-hairline pl-3 md:flex">
              <span className="grid h-7 w-7 place-items-center rounded-full bg-ink text-[10px]
                               font-medium text-white">PJ</span>
              <span className="leading-tight">
                <span className="block text-[11px] font-medium">Plant supervisor</span>
                <span className="block font-mono text-[9px] text-muted">
                  {tickCount} shift{tickCount === 1 ? "" : "s"} this session
                </span>
              </span>
            </span>
          </div>
        </header>

        <main className="min-h-0 flex-1 overflow-auto">{children}</main>
      </div>
    </div>
  );
}

/* ── Live pill — green when streaming, honest when not ── */
function LivePill({ connection, playing }: { connection: string; playing: boolean }) {
  const live = connection === "open";
  const label = !live ? (connection === "connecting" ? "Connecting" : "Offline")
    : playing ? "Live" : "Connected · paused";
  const color = !live ? "#B6B3AD" : playing ? "#4B9B6E" : "#D8A138";
  return (
    <span
      className="pill border border-hairline bg-white/70"
      role="status"
      aria-live="polite"
    >
      <span className="relative inline-flex h-1.5 w-1.5">
        {live && playing && (
          <span className="absolute inset-0 rounded-full animate-pulseRing"
                style={{ background: color }} />
        )}
        <span className="relative h-1.5 w-1.5 rounded-full" style={{ background: color }} />
      </span>
      {label}
    </span>
  );
}

/* ── tick controls (also on /config, same actions) ── */
function TickControls() {
  const { playing, intervalS } = useTwin();
  const [busy, setBusy] = useState(false);
  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    try { await fn(); } finally { setBusy(false); }
  };
  const btn = "rounded-lg border border-hairline bg-white/70 px-2.5 py-1.5 text-[11px] " +
              "font-medium transition-colors hover:bg-white disabled:opacity-40";
  return (
    <>
      <button className={btn} disabled={busy || playing}
              onClick={() => run(() => api.tick())}
              title="Advance the twin by one shift">
        Next shift
      </button>
      <button className={btn} disabled={busy}
              onClick={() => run(() => (playing ? api.pause() : api.play(intervalS)))}
              title={playing ? "Stop auto-advancing" : "Auto-advance one shift at a time"}>
        {playing ? "Pause" : "Play"}
      </button>
    </>
  );
}

/* ── icons: thin architectural line-work, 1.25px strokes ── */
const S = { fill: "none", stroke: "currentColor", strokeWidth: 1.25,
            strokeLinecap: "round" as const, strokeLinejoin: "round" as const };

function Logo() {
  return (
    <svg width="26" height="26" viewBox="0 0 26 26" aria-hidden>
      <rect x="3" y="3" width="20" height="20" rx="5" fill="#141414" />
      <path d="M8 16.5 L11.5 9.5 L14.5 14 L18 10" stroke="#F0552B" strokeWidth="1.6"
            fill="none" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
function FloorIcon() {
  return <svg width="18" height="18" viewBox="0 0 20 20" {...{}}>
    <path d="M2 7.5 10 3l8 4.5-8 4.5z" {...S} /><path d="M2 12.5 10 17l8-4.5" {...S} />
  </svg>;
}
function LensIcon() {
  return <svg width="18" height="18" viewBox="0 0 20 20">
    <circle cx="9" cy="9" r="5.5" {...S} /><path d="m13.5 13.5 3.5 3.5" {...S} />
  </svg>;
}
function CoinIcon() {
  return <svg width="18" height="18" viewBox="0 0 20 20">
    <circle cx="10" cy="10" r="7" {...S} /><path d="M10 6v8M8 8.2h3.4M8.6 11.6h3.4" {...S} />
  </svg>;
}
function TrendIcon() {
  return <svg width="18" height="18" viewBox="0 0 20 20">
    <path d="M3 15V5M3 15h14" {...S} /><path d="m6 12 3.2-3.8L12 11l4-5" {...S} />
  </svg>;
}
function GearIcon() {
  return <svg width="18" height="18" viewBox="0 0 20 20">
    <circle cx="10" cy="10" r="2.6" {...S} />
    <path d="M10 2.6v2M10 15.4v2M17.4 10h-2M4.6 10h-2M15.2 4.8l-1.4 1.4M6.2 13.8l-1.4 1.4M15.2 15.2l-1.4-1.4M6.2 6.2 4.8 4.8" {...S} />
  </svg>;
}
