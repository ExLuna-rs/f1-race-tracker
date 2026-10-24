import Link from "next/link";
import type { ReactNode } from "react";
import { TRACK_STATUS, type SessionKind } from "@/lib/format";
import type { Frame, Meta, PlaybackState } from "@/lib/types";

const MODE_LABELS = { live: "DIRECT", replay: "REPLAY", recording: "ENREGISTREMENT" };

interface Props {
  meta: Meta;
  frame: Frame | null;
  playback: PlaybackState | null;
  connected: boolean;
  kind: SessionKind;
  nav: ReactNode;
}

export default function Header({ meta, frame, playback, connected, kind, nav }: Props) {
  const session = meta.session;
  const status = TRACK_STATUS[frame?.track_status ?? ""];
  const weather = frame?.weather;
  const mode = playback?.mode;
  const title = session?.meeting
    ? `${session.meeting}${session.name ? ` · ${session.name}` : ""}`
    : session?.name || "Chargement…";

  return (
    <header className="header">
      <div className="header-title">
        {mode && (
          <span className={`mode mode-${mode}${mode === "live" && !playback?.live ? " behind" : ""}`}>
            {MODE_LABELS[mode]}
          </span>
        )}
        <h1>{title}</h1>
      </div>
      <div className="header-info">
        {kind === "race" && frame && (
          <span className="pill">
            Tour <b>{frame.lap}</b>
            {meta.total_laps ? ` / ${meta.total_laps}` : ""}
          </span>
        )}
        {frame?.clock && <span className="pill mono">{frame.clock}</span>}
        {status && (
          <span className="pill" style={{ color: status.color, borderColor: status.color }}>
            {status.label}
          </span>
        )}
        {weather && (
          <span className="pill" title={`Humidité ${weather.humidity ?? "?"} %, vent ${weather.wind_speed ?? "?"} m/s`}>
            Air {weather.air_temp?.toFixed(0) ?? "?"}° · Piste {weather.track_temp?.toFixed(0) ?? "?"}°
            {weather.rain_state === "RAINING" ? " · Pluie" : ""}
          </span>
        )}
        {nav}
        <span className={`dot${connected ? " on" : ""}`} title={connected ? "Connecté" : "Déconnecté"} />
        <Link href="/admin" className="admin-link">
          Admin
        </Link>
      </div>
    </header>
  );
}
