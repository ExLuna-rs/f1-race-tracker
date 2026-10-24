"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { ControlMessage, Frame, Meta, PlaybackState, ServerMessage } from "./types";

// Seconds of telemetry kept per driver for the charts
export const HISTORY_S = 90;

export interface Sample {
  t: number;
  speed: number;
  throttle: number;
  brake: number;
  gear: number;
}

export interface Motion {
  // Recent frames, oldest first
  frames: Frame[];
  // Playback position as of `at` (performance.now()), advanced locally between messages
  clock: { t: number; at: number; speed: number; paused: boolean };
  // Seconds of race time the map is drawn behind the clock, so the frame it
  // moves towards has always arrived already
  lag: number;
  // Session time the map last drew, and when
  shown: { t: number; at: number } | null;
}

export interface MotionSample {
  frames: Frame[];
  // Index of the last frame at or before t
  i: number;
  t: number;
}

type Point = { x: number | null; y: number | null } | null | undefined;

function clockTime(clock: Motion["clock"], now: number) {
  return clock.paused ? clock.t : clock.t + ((now - clock.at) / 1000) * clock.speed;
}

// The session time to draw now. It runs at playback speed and only eases
// towards the target, so lag and clock corrections never make cars jump.
export function sampleMotion(m: Motion, now: number): MotionSample | null {
  const { frames, clock } = m;
  if (!frames.length) return null;
  // Paused, the map catches up with the latest frame
  if (clock.paused) m.lag *= 0.92;
  const target = clockTime(clock, now) - m.lag;
  const shown = m.shown;
  if (!shown || Math.abs(target - shown.t) > 1.5 * Math.max(clock.speed, 1)) {
    m.shown = { t: target, at: now };
  } else {
    const dt = Math.min((now - shown.at) / 1000, 0.1);
    const speed = clock.paused ? 0 : clock.speed;
    // Close the gap over a couple of seconds, never more than a quarter faster
    // or slower than playback, which the eye reads as cars surging
    const limit = 0.25 * Math.max(speed, 1);
    const fix = Math.min(Math.max((target - shown.t) * 0.5, -limit), limit);
    m.shown = { t: shown.t + dt * (speed + fix), at: now };
  }
  const t = m.shown.t;
  let i = frames.length - 1;
  while (i > 0 && frames[i].t > t) i--;
  return { frames, i, t };
}

function valid(p: Point): p is { x: number; y: number } {
  return p != null && p.x != null && p.y != null && (p.x !== 0 || p.y !== 0);
}

// Where a car (or the safety car) is at the sample's time. FastF1 only has
// a few GPS fixes a second, at uneven times, so passing exactly through every
// frame makes cars surge and slow. A cubic B-spline passes near them instead,
// evening out the speed for about a metre off the line, under a pixel here.
export function positionAt(s: MotionSample, get: (f: Frame) => Point): [number, number] | null {
  const { frames, i, t } = s;
  const f1 = frames[i];
  const f2 = frames[i + 1];
  const p1 = get(f1);
  const p2 = f2 ? get(f2) : null;
  if (!valid(p1)) return valid(p2) ? [p2.x, p2.y] : null;
  if (!f2 || !valid(p2) || t <= f1.t) return [p1.x, p1.y];
  const h = f2.t - f1.t;
  const u = Math.min((t - f1.t) / h, 1);
  // Neighbours far off in time, after a gap in the data, are left out
  const f0 = frames[i - 1];
  const f3 = frames[i + 2];
  const n0 = f0 && f1.t - f0.t < 2 * h ? get(f0) : null;
  const n3 = f3 && f3.t - f2.t < 2 * h ? get(f3) : null;
  const p0 = valid(n0) ? n0 : { x: 2 * p1.x - p2.x, y: 2 * p1.y - p2.y };
  const p3 = valid(n3) ? n3 : { x: 2 * p2.x - p1.x, y: 2 * p2.y - p1.y };
  const v = 1 - u;
  const u2 = u * u;
  const u3 = u2 * u;
  const w0 = (v * v * v) / 6;
  const w1 = (3 * u3 - 6 * u2 + 4) / 6;
  const w2 = (-3 * u3 + 3 * u2 + 3 * u + 1) / 6;
  const w3 = u3 / 6;
  return [
    w0 * p0.x + w1 * p1.x + w2 * p2.x + w3 * p3.x,
    w0 * p0.y + w1 * p1.y + w2 * p2.y + w3 * p3.y,
  ];
}

export interface Stream {
  connected: boolean;
  // Set when the server can't open the session asked for
  error: string | null;
  meta: Meta;
  frame: Frame | null;
  playback: PlaybackState | null;
  motion: React.RefObject<Motion>;
  history: React.RefObject<Map<string, Sample[]>>;
  send: (message: ControlMessage) => void;
}

function streamUrl(session: string) {
  const query = `?session=${encodeURIComponent(session)}`;
  const override = process.env.NEXT_PUBLIC_WS_URL;
  if (override) return override + query;
  const scheme = window.location.protocol === "https:" ? "wss" : "ws";
  return `${scheme}://${window.location.host}/ws${query}`;
}

function newMotion(): Motion {
  return { frames: [], clock: { t: 0, at: 0, speed: 1, paused: true }, lag: 0, shown: null };
}

// `session` is "live" to follow the session on now, or a library session id
export function useStream(session: string): Stream {
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [meta, setMeta] = useState<Meta>({});
  const [frame, setFrame] = useState<Frame | null>(null);
  const [playback, setPlayback] = useState<PlaybackState | null>(null);
  const socket = useRef<WebSocket | null>(null);
  const motion = useRef<Motion>(newMotion());
  const history = useRef(new Map<string, Sample[]>());

  useEffect(() => {
    let closed = false;
    let retry = 1000;
    // Another session: start from a clean slate
    motion.current = newMotion();
    history.current.clear();
    setMeta({});
    setFrame(null);
    setPlayback(null);
    setError(null);
    let timer: ReturnType<typeof setTimeout> | undefined;

    const syncClock = (state: PlaybackState) => {
      const m = motion.current;
      const now = performance.now();
      const { clock } = m;
      const predicted = clockTime(clock, now);
      const drift = state.t - predicted;
      // Small drifts are network jitter, so ease towards the server instead of jumping
      const snap =
        state.paused !== clock.paused || state.speed !== clock.speed || Math.abs(drift) > Math.max(1, state.speed);
      m.clock = { t: snap ? state.t : predicted + drift * 0.1, at: now, speed: state.speed, paused: state.paused };
    };

    // `between` holds the frames the server skipped since the last one, oldest first
    const onFrames = (between: Frame[], next: Frame) => {
      const m = motion.current;
      const speed = Math.max(m.clock.speed, 1);
      const last = m.frames[m.frames.length - 1];
      const first = between[0] ?? next;
      // A seek or a new session: drop the in-between motion and history
      const jumped = !last || first.t < last.t || first.t - last.t > 5 * speed;
      if (jumped) {
        history.current.clear();
        m.frames = [];
        m.lag = 0.5 * speed;
      } else if (next.t > last.t) {
        // How far the clock had run past the newest frame by the time the next
        // ones came: drawing that far behind, plus a margin for network jitter,
        // keeps a frame ahead to move towards. Grows at once, shrinks slowly.
        const needed = clockTime(m.clock, performance.now()) - last.t + 0.1 * speed;
        m.lag = Math.min(needed > m.lag ? needed : m.lag * 0.995 + needed * 0.005, 3 * speed);
      }

      for (const f of [...between, next]) {
        const newest = m.frames[m.frames.length - 1];
        if (newest && f.t <= newest.t) continue;
        m.frames.push(f);
        for (const [code, d] of Object.entries(f.drivers)) {
          let samples = history.current.get(code);
          if (!samples) history.current.set(code, (samples = []));
          samples.push({ t: f.t, speed: d.speed, throttle: d.throttle, brake: d.brake, gear: d.gear });
          while (samples.length && samples[0].t < f.t - HISTORY_S) samples.shift();
        }
      }
      if (m.frames.length > 256) m.frames.splice(0, m.frames.length - 256);
      setFrame(next);
    };

    const connect = () => {
      const ws = new WebSocket(streamUrl(session));
      socket.current = ws;
      ws.onopen = () => {
        retry = 1000;
        setConnected(true);
      };
      ws.onmessage = (event) => {
        if (socket.current !== ws) return;
        let message: ServerMessage;
        try {
          message = JSON.parse(event.data);
        } catch {
          return;
        }
        if (message.type === "error") {
          // Not found: retrying won't help
          closed = true;
          setError(message.message);
          return;
        }
        setPlayback(message.state);
        syncClock(message.state);
        if (message.type === "meta") {
          setMeta(message.meta ?? {});
        } else if (message.type === "frame") {
          onFrames(message.between ?? [], message.frame);
        }
      };
      ws.onclose = () => {
        // A socket closed when switching sessions mustn't touch the new one
        if (socket.current !== ws) return;
        setConnected(false);
        socket.current = null;
        if (closed) return;
        timer = setTimeout(connect, retry);
        retry = Math.min(retry * 2, 15000);
      };
    };

    connect();
    return () => {
      closed = true;
      clearTimeout(timer);
      socket.current?.close();
    };
  }, [session]);

  const send = useCallback((message: ControlMessage) => {
    if (socket.current?.readyState === WebSocket.OPEN) {
      socket.current.send(JSON.stringify(message));
    }
  }, []);

  return { connected, error, meta, frame, playback, motion, history, send };
}
