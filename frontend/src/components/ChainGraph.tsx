/** ChainGraph — directed trigger → downstream graph, edge label = lift (§5.2).
 *  Chains that fired this session are highlighted in orange. */
import type { ChainRule } from "../lib/types";
import { humanise } from "../lib/format";
import { EmptyState, Info } from "./primitives";

export function ChainGraph({ chains, fired }: { chains: ChainRule[]; fired: Set<string> }) {
  if (!chains.length) {
    return <EmptyState title="No chains learned"
                       body="The chain table is empty, so no downstream inspections are predicted." />;
  }

  const triggers = [...new Set(chains.map(c => c.trigger))];
  const downstream = [...new Set(chains.map(c => c.downstream))];
  const ROW = 62, TOP = 34, LEFT = 20, RIGHT = 400, W = 520;
  const H = TOP + Math.max(triggers.length, downstream.length) * ROW + 20;

  const yOf = (list: string[], name: string) => TOP + list.indexOf(name) * ROW;

  return (
    <div className="card-solid overflow-x-auto p-4">
      <svg width={W} height={H} className="min-w-[520px]"
           role="img" aria-label="Defect chain graph">
        <text x={LEFT} y={16} className="font-mono" fontSize="9.5" fill="#8A8A8A"
              letterSpacing="1.2">TRIGGER (CAUGHT)</text>
        <text x={RIGHT} y={16} className="font-mono" fontSize="9.5" fill="#8A8A8A"
              letterSpacing="1.2">PREDICTED DOWNSTREAM</text>

        {chains.map((c, i) => {
          const y1 = yOf(triggers, c.trigger), y2 = yOf(downstream, c.downstream);
          const active = fired.has(c.trigger);
          const mid = (LEFT + 130 + RIGHT) / 2;
          return (
            <g key={i}>
              <path
                d={`M${LEFT + 132} ${y1} C${mid} ${y1}, ${mid} ${y2}, ${RIGHT - 6} ${y2}`}
                fill="none" stroke={active ? "#F0552B" : "#C9C6C0"}
                strokeWidth={active ? 1.8 : 1.1} opacity={active ? 0.95 : 0.6}
              />
              <text x={mid} y={(y1 + y2) / 2 - 6} textAnchor="middle" className="font-mono"
                    fontSize="10" fill={active ? "#F0552B" : "#8A8A8A"}>
                lift {c.lift.toFixed(2)}
              </text>
            </g>
          );
        })}

        {triggers.map(t => {
          const active = fired.has(t);
          return (
            <g key={t} transform={`translate(${LEFT} ${yOf(triggers, t)})`}>
              <rect x="0" y="-13" width="128" height="26" rx="8"
                    fill={active ? "#FFF3EF" : "#FFFFFF"}
                    stroke={active ? "#F0552B" : "#E2E0DC"} strokeWidth="1" />
              <text x="11" y="4" fontSize="11.5" fill="#141414">{humanise(t)}</text>
            </g>
          );
        })}
        {downstream.map(d => (
          <g key={d} transform={`translate(${RIGHT} ${yOf(downstream, d)})`}>
            <rect x="0" y="-13" width="112" height="26" rx="8" fill="#FFFFFF"
                  stroke="#E2E0DC" strokeWidth="1" />
            <text x="11" y="4" fontSize="11.5" fill="#141414">{humanise(d)}</text>
          </g>
        ))}
      </svg>

      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-hairline
                      pt-3 text-[11px] text-muted">
        <span className="flex items-center gap-1.5">
          <span className="h-[2px] w-5 bg-accent" /> fired this session
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-[2px] w-5 bg-blueprint" /> learned, not yet seen
        </span>
        <span className="flex items-center">
          Lift
          <Info term="lift">
            How much more often the downstream defect follows the trigger than it would by chance.
            Lift 1.4 means 40% more often than random.
          </Info>
        </span>
      </div>
    </div>
  );
}
