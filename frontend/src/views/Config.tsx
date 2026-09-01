/** Settings (/config) — assumptions, camera map, tick controls, audit trail (§5.5). */
import { useEffect, useState } from "react";

import { AssumptionsPanel } from "../components/AssumptionsPanel";
import { Info, SectionTitle } from "../components/primitives";
import { api } from "../lib/api";
import { stationLabel, zoneLabel } from "../lib/format";
import { useTwin } from "../store/twin";

export function Config() {
  const { config, pnl, line, health, playing, intervalS, refreshConfig, refreshPnl } = useTwin();
  const [pending, setPending] = useState(false);
  const [interval, setIntervalS] = useState(intervalS);
  const [cameraDraft, setCameraDraft] = useState<Record<string, string>>({});
  const [cameraError, setCameraError] = useState<string | null>(null);

  useEffect(() => setIntervalS(intervalS), [intervalS]);
  useEffect(() => {
    const map = config?.config.mappings?.CAMERA_TO_STATION ?? {};
    setCameraDraft(Object.fromEntries(Object.entries(map).map(([k, v]) => [k, String(v)])));
  }, [config]);

  const saveCamera = async (cam: string) => {
    const value = Number(cameraDraft[cam]);
    const current = config?.config.mappings?.CAMERA_TO_STATION?.[cam];
    if (Number.isNaN(value) || cameraDraft[cam] === "") {
      setCameraError(`${cam} needs a station number.`); return;
    }
    if (value === current) return;
    setCameraError(null);
    setPending(true);
    try {
      await api.updateMappings({ CAMERA_TO_STATION: { ...(config?.config.mappings
        ?.CAMERA_TO_STATION ?? {}), [cam]: value } });
      await refreshConfig();
    } catch (e) {
      setCameraError(e instanceof Error ? e.message : String(e));
      setCameraDraft(d => ({ ...d, [cam]: String(current ?? "") }));
    } finally { setPending(false); }
  };

  const run = async (fn: () => Promise<unknown>) => {
    setPending(true);
    try { await fn(); await refreshPnl(); } finally { setPending(false); }
  };

  const btn = "rounded-lg border border-hairline bg-white px-3 py-1.5 text-[12px] font-medium " +
              "transition-colors hover:bg-black/[.03] disabled:opacity-40";

  return (
    <div className="space-y-5 p-4 lg:p-6">
      <p className="rounded-card border border-hairline bg-black/[.02] px-4 py-2.5 text-[12px]
                    leading-relaxed text-muted">
        These settings drive the whole demo — nothing here is hardcoded. Every change is recorded
        in the audit trail below.
      </p>

      <div className="grid gap-5 xl:grid-cols-[1fr_1fr]">
        {pnl && <AssumptionsPanel pnl={pnl} pending={pending} setPending={setPending} />}

        <div className="space-y-5">
          {/* tick controls */}
          <section className="card-solid p-4">
            <SectionTitle hint="One tick advances the twin by one shift.">Line controls</SectionTitle>
            <div className="flex flex-wrap items-center gap-2">
              <button className={btn} disabled={pending || playing}
                      onClick={() => run(() => api.tick())}>Next shift</button>
              <button className={btn} disabled={pending}
                      onClick={() => run(() => (playing ? api.pause() : api.play(interval)))}>
                {playing ? "Pause" : "Play"}
              </button>
              <button className={btn} disabled={pending}
                      onClick={() => run(() => api.reset())}
                      title="Clear this session's shifts, alerts and projection">
                Reset session
              </button>
            </div>
            <label className="mt-3 block">
              <span className="flex items-center text-[11.5px] text-muted">
                Seconds between shifts
                <Info term="tick cadence">
                  How fast the twin advances when playing. Config, not a fixed value.
                </Info>
              </span>
              <div className="mt-0.5 flex gap-2">
                <input
                  type="number" min={0.2} step={0.2} value={interval}
                  onChange={e => setIntervalS(Number(e.target.value))}
                  aria-label="Seconds between shifts"
                  className="w-28 rounded-lg border border-hairline bg-white px-2.5 py-1.5
                             font-mono text-[13px] tnum focus:border-ink"
                />
                <button className={btn} disabled={pending}
                        onClick={() => run(() => api.play(interval))}>Apply</button>
              </div>
            </label>
          </section>

          {/* camera → station */}
          <section className="card-solid p-4">
            <SectionTitle hint="Which of the 35 stations each camera feed belongs to. An assumption a plant would confirm from its own layout.">
              Camera to station
            </SectionTitle>
            {cameraError && (
              <p role="alert" className="mb-2 rounded-lg border border-accent/30 bg-accent/[.06]
                                         px-2.5 py-1.5 text-[11.5px] text-accent">{cameraError}</p>
            )}
            <div className="space-y-2">
              {Object.keys(cameraDraft).length === 0 && (
                <p className="text-[12px] text-muted">No cameras configured.</p>
              )}
              {Object.entries(cameraDraft).map(([cam, value]) => {
                const stationId = Number(value);
                const node = line?.nodes.find(n => n.station_id === stationId);
                return (
                  <div key={cam} className="flex items-center gap-2">
                    <span className="flex-1 truncate font-mono text-[12px]">{cam}</span>
                    <input
                      type="number" min={0} max={(line?.n_stations ?? 35) - 1} value={value}
                      disabled={pending} aria-label={`Station for ${cam}`}
                      onChange={e => setCameraDraft(d => ({ ...d, [cam]: e.target.value }))}
                      onBlur={() => saveCamera(cam)}
                      onKeyDown={e => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }}
                      className="w-20 rounded-lg border border-hairline bg-white px-2.5 py-1.5
                                 font-mono text-[13px] tnum focus:border-ink disabled:opacity-50"
                    />
                    <span className="w-[112px] shrink-0 text-right text-[11px] text-muted">
                      {node ? `${stationLabel(stationId)} · ${zoneLabel(node.zone)}` : "out of range"}
                    </span>
                  </div>
                );
              })}
            </div>
          </section>

          {/* fixed facts */}
          <section className="card-solid p-4">
            <SectionTitle>Fixed by design</SectionTitle>
            <dl className="space-y-1.5 text-[12px]">
              <Row label="Stations">{line?.n_stations ?? "—"} (from graph.pt, read-only)</Row>
              <Row label="Forecast window">
                {health?.models.bottleneck.T_w ?? "—"} shifts
              </Row>
              <Row label="Confidence threshold">
                <span className="font-mono tnum">
                  {health?.models.bottleneck.conf_threshold.toFixed(4) ?? "—"}
                </span>
              </Row>
              <Row label="Simulator mode">{health?.mode ?? "—"}</Row>
            </dl>
            <p className="mt-2.5 text-[11px] leading-relaxed text-muted">
              {line?.note}
            </p>
          </section>
        </div>
      </div>

      {/* audit trail */}
      <section>
        <SectionTitle>Change history</SectionTitle>
        <div className="card-solid divide-y divide-hairline">
          {(config?.audits ?? []).length === 0 ? (
            <p className="p-4 text-[12px] text-muted">No changes recorded yet.</p>
          ) : config!.audits.map((a, i) => (
            <div key={i} className="flex flex-wrap items-baseline gap-x-3 gap-y-1 px-3.5 py-2.5">
              <span className="font-mono text-[10.5px] text-muted tnum">
                {new Date(a.created_at).toLocaleString()}
              </span>
              <span className="pill border border-hairline bg-black/[.03] font-mono text-[9.5px]">
                {a.config_name}
              </span>
              <span className="text-[11.5px] text-muted">by {a.actor}</span>
              <span className="w-full font-mono text-[10.5px] text-muted">
                {Object.entries(a.changes).map(([k, v]: [string, any]) =>
                  `${k}: ${JSON.stringify(v?.from)} → ${JSON.stringify(v?.to)}`).join("  ·  ")}
              </span>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt className="text-muted">{label}</dt><dd className="text-right">{children}</dd>
    </div>
  );
}
