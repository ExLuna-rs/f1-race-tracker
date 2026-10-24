"use client";

import { tyreFromCompound } from "@/lib/format";
import type { DriverInfo, Frame, Meta } from "@/lib/types";
import { orderedDrivers } from "./Leaderboard";

interface Props {
  meta: Meta;
  frame: Frame | null;
  selected: string | null;
  onSelect: (code: string) => void;
}

export default function TyreStrategy({ meta, frame, selected, onSelect }: Props) {
  const rows = orderedDrivers(frame);
  const info = new Map<string, DriverInfo>((meta.drivers ?? []).map((d) => [d.code, d]));
  const stints = meta.stints ?? {};
  const currentLap = frame?.lap ?? 0;
  // Replays know every stint in advance, so only show what has happened so far
  const totalLaps = Math.max(meta.total_laps ?? 0, currentLap, 1);

  if (rows.length === 0 || Object.keys(stints).length === 0) {
    return <div className="empty">Pas encore de relais pneus.</div>;
  }

  return (
    <div className="strategy">
      {rows.map(([code, d]) => {
        let start = 1;
        const driverLap = Math.max(d.lap, 1);
        return (
          <button
            key={code}
            className={`strategy-row${code === selected ? " selected" : ""}`}
            onClick={() => onSelect(code)}
          >
            <span className="strategy-code" style={{ borderColor: info.get(code)?.color }}>
              {code}
            </span>
            <span className="strategy-bar">
              {(stints[code] ?? []).map((s, i) => {
                const from = s.start_lap ?? start;
                start = from + s.laps;
                if (from > driverLap) return null;
                const laps = Math.min(s.laps, driverLap - from + 1);
                if (laps <= 0) return null;
                const tyre = tyreFromCompound(s.compound);
                return (
                  <span
                    key={i}
                    className="stint"
                    title={`${tyre.name}${s.new ? " (neufs)" : " (usés)"} · tours ${from} à ${from + laps - 1}`}
                    style={{
                      left: `${((from - 1) / totalLaps) * 100}%`,
                      width: `${(laps / totalLaps) * 100}%`,
                      background: tyre.color,
                      opacity: s.new ? 1 : 0.6,
                    }}
                  >
                    {laps >= 3 ? tyre.label : ""}
                  </span>
                );
              })}
            </span>
          </button>
        );
      })}
      <div className="strategy-axis">
        <span>Tour 1</span>
        <span>Tour {totalLaps}</span>
      </div>
    </div>
  );
}
