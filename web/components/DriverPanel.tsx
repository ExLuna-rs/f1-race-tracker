"use client";

import { HISTORY_S, type Sample } from "@/lib/useStream";
import { TYRES, drsState, shortGap } from "@/lib/format";
import type { DriverFrame, DriverInfo } from "@/lib/types";

interface Props {
  code: string | null;
  driver: DriverFrame | undefined;
  info: DriverInfo | undefined;
  samples: Sample[];
  now: number;
}

// Spelled out so the state reads without the colour
const DRS_LABELS = { off: "DRS", eligible: "DRS prêt", open: "DRS ouvert" };

const W = 600;
const H = 160;

function path(samples: Sample[], now: number, value: (s: Sample) => number, max: number) {
  return samples
    .map((s, i) => {
      const x = W - ((now - s.t) / HISTORY_S) * W;
      const y = H - (Math.min(Math.max(value(s), 0), max) / max) * H;
      return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join("");
}

function Bar({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div className="pedal">
      <div className="pedal-track">
        <div className="pedal-fill" style={{ height: `${Math.min(Math.max(value, 0), 100)}%`, background: color }} />
      </div>
      <span>{label}</span>
    </div>
  );
}

export default function DriverPanel({ code, driver, info, samples, now }: Props) {
  if (!code || !driver) {
    return <div className="empty">Cliquez sur un pilote dans le classement ou sur la carte.</div>;
  }
  const hasCarData = samples.some((s) => s.speed > 0 || s.gear > 0);
  // The live feed reports brake as 0 or 100, replays as 0 to 1
  const brake = driver.brake <= 1 ? driver.brake * 100 : driver.brake;
  const drs = drsState(driver.drs);
  const tyre = TYRES[Math.round(driver.tyre)];

  return (
    <div className="driver-panel">
      <div className="driver-head" style={{ borderColor: info?.color }}>
        <div>
          <div className="driver-name">
            <span className="driver-number">{info?.number ?? driver.number}</span> {info?.name || code}
          </div>
          <div className="driver-team">{info?.team}</div>
        </div>
        <div className="driver-facts">
          <span>P{driver.position || "–"}</span>
          <span>Tour {driver.lap}</span>
          {tyre && (
            <span style={{ color: tyre.color }}>
              {tyre.name} · {Math.round(driver.tyre_life ?? 0)} t.
            </span>
          )}
          {driver.gap && <span>Écart {shortGap(driver.gap)}</span>}
          {driver.best_lap && <span>Meilleur {driver.best_lap}</span>}
        </div>
      </div>

      {!hasCarData ? (
        <div className="empty">
          Pas de télémétrie voiture. En direct, elle demande un token F1 TV valide (page Admin).
        </div>
      ) : (
        <div className="telemetry">
          <div className="gauges">
            <div className="gauge">
              <span className="gauge-value">{Math.round(driver.speed)}</span>
              <span className="gauge-unit">km/h</span>
            </div>
            <div className="gauge">
              <span className="gauge-value">{driver.gear || "N"}</span>
              <span className="gauge-unit">rapport</span>
            </div>
            {driver.rpm != null && driver.rpm > 0 && (
              <div className="gauge">
                <span className="gauge-value">{driver.rpm}</span>
                <span className="gauge-unit">tr/min</span>
              </div>
            )}
            <div className={`drs drs-${drs}`}>{DRS_LABELS[drs]}</div>
            <Bar label="Gaz" value={driver.throttle} color="#2fbf71" />
            <Bar label="Frein" value={brake} color="#e8002d" />
          </div>
          <svg className="chart" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img"
               aria-label={`Vitesse, gaz et frein sur les ${HISTORY_S} dernières secondes`}>
            {[100, 200, 300].map((v) => (
              <line key={v} x1={0} x2={W} y1={H - (v / 360) * H} y2={H - (v / 360) * H} className="grid" />
            ))}
            <path d={path(samples, now, (s) => s.throttle, 100)} className="line-throttle" />
            <path d={path(samples, now, (s) => (s.brake <= 1 ? s.brake * 100 : s.brake), 100)} className="line-brake" />
            <path d={path(samples, now, (s) => s.speed, 360)} className="line-speed" />
          </svg>
          <div className="chart-legend">
            <span className="legend-speed">Vitesse</span>
            <span className="legend-throttle">Gaz</span>
            <span className="legend-brake">Frein</span>
            <span className="legend-span">{HISTORY_S} dernières secondes</span>
          </div>
        </div>
      )}
      {driver.sectors && driver.sectors.some(Boolean) && (
        <div className="sectors">
          {driver.sectors.map((s, i) => (
            <span key={i}>
              S{i + 1} <b>{s || "–"}</b>
            </span>
          ))}
          {driver.last_lap && (
            <span>
              Dernier tour <b>{driver.last_lap}</b>
            </span>
          )}
        </div>
      )}
    </div>
  );
}
