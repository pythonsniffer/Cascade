/** Live Twin (/) — the hero (Frontend Instructions §5.1). */
import { useEffect, useState } from "react";

import { AlertRail } from "../components/AlertRail";
import { BlueprintFloor } from "../components/BlueprintFloor";
import { StationCard } from "../components/StationCard";
import { StatusStrip } from "../components/StatusStrip";
import { ConfidencePill, Info, StatusDot } from "../components/primitives";
import { moneyExact, stationLabel, zoneLabel } from "../lib/format";
import { useTwin } from "../store/twin";
import { TwinStateDialog } from "../components/TwinStateDialog";

export function LiveTwin() {
  const {
    line, bottleneck, alerts, health, shiftName, shiftId, cumulativeNet, pnl, config,
    selectedStation, selectStation, selectedVehicle, selectVehicle, tickCount,
  } = useTwin();
  const [clock, setClock] = useState(new Date());

  useEffect(() => {
    const t = setInterval(() => setClock(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  if (!line) {
    return <div className="grid h-full place-items-center text-[13px] text-muted">
      Loading line topology…
    </div>;
  }

  const detectorOn = !!health?.models.defect.detector_loaded;
  const warming = !bottleneck || bottleneck.confidence === "warming_up";
  const currency = pnl?.currency ?? "USD";

  return (
    <div className="flex h-full min-h-0 flex-col gap-3 p-3 lg:p-4">
      <div className="flex min-h-0 flex-1 flex-col gap-3 xl:flex-row">
        {/* ── left: the shift headline ── */}
        <div className="flex shrink-0 flex-row items-start gap-4 xl:w-[190px] xl:flex-col">
          <div>
            <p className="eyebrow">Current shift</p>
            <h2 className="font-display text-[38px] font-light leading-[1.05] tracking-tight
                           lg:text-[46px]">
              {shiftName ?? "Not started"}
            </h2>
            <p className="mt-1 font-mono text-[11px] text-muted tnum">
              {shiftId !== null ? `shift ${shiftId}` : "press Next shift"} ·{" "}
              {clock.toLocaleTimeString(undefined, { hour12: false })}
            </p>
          </div>

          <div className="card p-3 xl:w-full">
            <p className="eyebrow flex items-center">
              Predicted bottleneck
              <Info term="Predicted bottleneck">
                The station the model expects to slow the line next shift.
              </Info>
            </p>
            {warming ? (
              <p className="mt-1.5 text-[12px] leading-snug text-muted">
                Warming up — the forecaster needs {health?.models.bottleneck.T_w ?? 3} shifts
                of history first.
              </p>
            ) : bottleneck.abstained ? (
              <p className="mt-1.5 text-[12px] leading-snug text-muted">
                No confident call this shift. The model abstained rather than guess.
              </p>
            ) : (
              <>
                <p className="mt-1 flex items-baseline gap-2">
                  <StatusDot status="bottleneck" size={9} pulse />
                  <span className="font-mono text-[30px] font-medium leading-none text-accent tnum">
                    {stationLabel(bottleneck.station)}
                  </span>
                </p>
                <p className="mt-1 text-[11.5px] text-muted">{zoneLabel(bottleneck.zone)}</p>
              </>
            )}
            <div className="mt-2">
              <ConfidencePill confidence={bottleneck?.confidence ?? null}
                              abstained={bottleneck?.abstained} />
            </div>
          </div>

          <div className="card p-3 xl:w-full">
            <p className="eyebrow flex items-center">
              Projected impact
              <Info term="Projected impact">
                Model outputs multiplied by your cost assumptions. A projection, not a measured
                saving.
              </Info>
            </p>
            <p className="mt-1 font-mono text-[24px] font-medium leading-none tnum">
              {moneyExact(cumulativeNet, currency)}
            </p>
            <p className="mt-1.5 text-[10.5px] leading-snug text-muted">
              Across {tickCount} shift{tickCount === 1 ? "" : "s"} this session. Projected, not
              measured.
            </p>
          </div>
        </div>

        {/* ── centre: the floor ── */}
        <div className="relative min-h-[380px] flex-1">
          <BlueprintFloor
            line={line} bottleneck={bottleneck} alerts={alerts}
            selected={selectedStation} onSelect={selectStation}
          />
          {selectedStation !== null && (
            <div className="absolute right-4 top-4 z-10">
              <StationCard
                stationId={selectedStation} line={line} bottleneck={bottleneck}
                cameras={config?.config.mappings?.CAMERA_TO_STATION ?? {}}
                onClose={() => selectStation(null)}
              />
            </div>
          )}
        </div>

        {/* ── right: alerts ── */}
        <AlertRail alerts={alerts} detectorOn={detectorOn} onOpen={selectVehicle} />
      </div>

      <div className="shrink-0">
        <StatusStrip line={line} bottleneck={bottleneck}
                     selected={selectedStation} onSelect={selectStation} />
      </div>

      {selectedVehicle !== null && (
        <TwinStateDialog vehicleId={selectedVehicle} onClose={() => selectVehicle(null)} />
      )}
    </div>
  );
}
