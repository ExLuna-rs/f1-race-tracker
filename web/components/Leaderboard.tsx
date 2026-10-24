"use client";

import { useState } from "react";
import { TYRES, estimatedGap, shortGap, type SessionKind } from "@/lib/format";
import type { DriverFrame, DriverInfo, Frame, Meta } from "@/lib/types";

interface Props {
  meta: Meta;
  frame: Frame | null;
  kind: SessionKind;
  selected: string | null;
  onSelect: (code: string) => void;
}

export function orderedDrivers(frame: Frame | null) {
  if (!frame) return [];
  return Object.entries(frame.drivers).sort(([, a], [, b]) => {
    if (!!a.retired !== !!b.retired) return a.retired ? 1 : -1;
    return (a.position || 99) - (b.position || 99);
  });
}

function Tyre({ driver }: { driver: DriverFrame }) {
  const tyre = TYRES[Math.round(driver.tyre)];
  if (!tyre) return <span />;
  return (
    <span className="tyre-cell" title={tyre.name}>
      <span className="tyre" style={{ borderColor: tyre.color, color: tyre.color }}>
        {tyre.label}
      </span>
      {driver.tyre_life != null && <span className="tyre-age">{Math.round(driver.tyre_life)}</span>}
    </span>
  );
}

export default function Leaderboard({ meta, frame, kind, selected, onSelect }: Props) {
  const [showInterval, setShowInterval] = useState(false);
  const rows = orderedDrivers(frame);
  const info = new Map<string, DriverInfo>((meta.drivers ?? []).map((d) => [d.code, d]));
  const leader = rows[0]?.[1];
  const isRace = kind === "race";
  const gapLabel = isRace ? (showInterval ? "Intervalle" : "Écart") : "Écart";

  return (
    <div className="leaderboard">
      <div className="lb-row lb-head">
        <span>P</span>
        <span />
        <span>Pilote</span>
        <button
          className="lb-gap-toggle"
          onClick={() => setShowInterval((v) => !v)}
          disabled={!isRace}
          title={isRace ? "Basculer écart au leader / intervalle" : undefined}
        >
          {gapLabel}
        </button>
        <span>{isRace ? "Dernier" : "Meilleur"}</span>
        <span>Pneu</span>
      </div>
      {rows.length === 0 && <div className="empty">Aucune donnée pour l&apos;instant</div>}
      {rows.map(([code, d]) => {
        const driver = info.get(code);
        let gap = shortGap(isRace && showInterval ? d.interval : d.gap);
        if (!gap && isRace && frame && d.gap == null) gap = estimatedGap(d, leader, frame);
        if (d === leader && isRace) gap = `T${d.lap}`;
        const status = d.retired ? "OUT" : d.knocked_out ? "ÉLIM." : d.in_pit ? "PIT" : "";
        return (
          <button
            key={code}
            className={`lb-row${code === selected ? " selected" : ""}${d.retired || d.knocked_out ? " out" : ""}`}
            onClick={() => onSelect(code)}
          >
            <span className="lb-pos">{d.position || "–"}</span>
            <span className="lb-team" style={{ background: driver?.color ?? "#555" }} />
            <span className="lb-code" title={driver?.name}>
              {code}
              {status && <span className={`lb-status lb-status-${status === "PIT" ? "pit" : "out"}`}>{status}</span>}
            </span>
            <span className="lb-gap">{gap}</span>
            <span className="lb-lap">{(isRace ? d.last_lap : d.best_lap) || ""}</span>
            <Tyre driver={d} />
          </button>
        );
      })}
    </div>
  );
}
