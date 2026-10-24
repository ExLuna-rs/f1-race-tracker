"use client";

import { useEffect, useRef, useState } from "react";
import { TRACK_STATUS, formatTime } from "@/lib/format";
import type { ControlMessage, Meta, PlaybackState } from "@/lib/types";

const SPEEDS = [0.5, 1, 2, 4, 8, 16, 32, 64];
// While scrubbing, seek this often so the map follows the thumb
const SCRUB_SEEK_MS = 150;

interface Props {
  meta: Meta;
  playback: PlaybackState | null;
  send: (message: ControlMessage) => void;
}

export default function Controls({ meta, playback, send }: Props) {
  const [dragging, setDragging] = useState<number | null>(null);
  const lastSeek = useRef(0);
  const duration = playback?.duration ?? 0;
  const t = dragging ?? playback?.t ?? 0;
  const isLive = playback?.mode === "live";

  const scrub = (value: number) => {
    setDragging(value);
    const now = performance.now();
    if (now - lastSeek.current >= SCRUB_SEEK_MS) {
      lastSeek.current = now;
      send({ type: "seek", t: value });
    }
  };
  const endScrub = () => {
    if (dragging != null) send({ type: "seek", t: dragging });
    setDragging(null);
  };

  // Space toggles play, arrows skip 5 s (30 s with shift)
  useEffect(() => {
    const isField = (target: EventTarget | null) =>
      ["INPUT", "TEXTAREA", "SELECT"].includes((target as HTMLElement)?.tagName);
    const onKey = (event: KeyboardEvent) => {
      if (isField(event.target)) return;
      if (event.code === "Space") {
        event.preventDefault();
        if (!event.repeat) send({ type: playback?.paused ? "play" : "pause" });
      } else if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
        const step = event.shiftKey ? 30 : 5;
        send({ type: "skip", seconds: event.key === "ArrowLeft" ? -step : step });
      }
    };
    // A focused button is clicked on Space's keyup: cancel it, otherwise the
    // play button would toggle a second time right after the shortcut
    const onKeyUp = (event: KeyboardEvent) => {
      if (event.code === "Space" && !isField(event.target)) event.preventDefault();
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("keyup", onKeyUp);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("keyup", onKeyUp);
    };
  }, [send, playback?.paused]);

  const bands = (meta.track_statuses ?? []).filter(
    (s) => s.status !== "1" && s.start_time != null && TRACK_STATUS[s.status] && duration > 0,
  );

  return (
    <div className="controls">
      <div className="controls-buttons">
        <button onClick={() => send({ type: "skip", seconds: -30 })} title="Reculer de 30 s" aria-label="Reculer de 30 secondes">−30</button>
        <button onClick={() => send({ type: "skip", seconds: -10 })} title="Reculer de 10 s" aria-label="Reculer de 10 secondes">−10</button>
        <button
          className="play"
          onClick={() => send({ type: playback?.paused ? "play" : "pause" })}
          title={playback?.paused ? "Lecture (espace)" : "Pause (espace)"}
          aria-label={playback?.paused ? "Lecture" : "Pause"}
        >
          <span aria-hidden>{playback?.paused ? "▶" : "❚❚"}</span>
        </button>
        <button onClick={() => send({ type: "skip", seconds: 10 })} title="Avancer de 10 s" aria-label="Avancer de 10 secondes">+10</button>
        <button onClick={() => send({ type: "skip", seconds: 30 })} title="Avancer de 30 s" aria-label="Avancer de 30 secondes">+30</button>
        <select
          value={playback?.speed ?? 1}
          onChange={(e) => send({ type: "speed", value: Number(e.target.value) })}
          title="Vitesse de lecture"
        >
          {SPEEDS.map((s) => (
            <option key={s} value={s}>
              ×{s}
            </option>
          ))}
        </select>
        {isLive && (
          <button
            className={`live-button${playback?.live ? " on" : ""}`}
            onClick={() => send({ type: "live" })}
            title="Revenir au direct"
            aria-pressed={!!playback?.live}
          >
            <span aria-hidden>●</span> DIRECT
          </button>
        )}
      </div>
      <div className="timeline">
        <span className="time">{formatTime(t)}</span>
        <div className="scrubber">
          <div className="bands">
            {bands.map((s, i) => {
              const start = s.start_time! / duration;
              const end = (s.end_time ?? duration) / duration;
              return (
                <span
                  key={i}
                  title={TRACK_STATUS[s.status].label}
                  style={{
                    left: `${start * 100}%`,
                    width: `${Math.max(end - start, 0.002) * 100}%`,
                    background: TRACK_STATUS[s.status].color,
                  }}
                />
              );
            })}
          </div>
          <input
            type="range"
            min={0}
            max={Math.max(duration, 1)}
            step={1}
            value={Math.min(t, Math.max(duration, 1))}
            onChange={(e) => scrub(Number(e.target.value))}
            onPointerUp={endScrub}
            onKeyUp={endScrub}
            aria-label="Position dans la session"
          />
        </div>
        <span className="time">{formatTime(duration)}</span>
      </div>
    </div>
  );
}
