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

export interface Stream {
  connected: boolean;
  meta: Meta;
  frame: Frame | null;
  playback: PlaybackState | null;
  // Previous frame and when the current one arrived, for smooth car movement
  motion: React.RefObject<{ prev: Frame | null; cur: Frame | null; arrived: number; interval: number }>;
  history: React.RefObject<Map<string, Sample[]>>;
  send: (message: ControlMessage) => void;
}

function streamUrl() {
  const override = process.env.NEXT_PUBLIC_WS_URL;
  if (override) return override;
  const scheme = window.location.protocol === "https:" ? "wss" : "ws";
  return `${scheme}://${window.location.host}/ws`;
}

export function useStream(): Stream {
  const [connected, setConnected] = useState(false);
  const [meta, setMeta] = useState<Meta>({});
  const [frame, setFrame] = useState<Frame | null>(null);
  const [playback, setPlayback] = useState<PlaybackState | null>(null);
  const socket = useRef<WebSocket | null>(null);
  const motion = useRef({ prev: null as Frame | null, cur: null as Frame | null, arrived: 0, interval: 250 });
  const history = useRef(new Map<string, Sample[]>());

  useEffect(() => {
    let closed = false;
    let retry = 1000;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const onFrame = (next: Frame) => {
      const m = motion.current;
      const now = performance.now();
      const last = m.cur;
      // A seek or a new session: drop the in-between motion and history
      const jumped = !last || next.t < last.t || next.t - last.t > 5;
      if (jumped) {
        history.current.clear();
        m.prev = next;
      } else {
        m.prev = last;
        m.interval = Math.min(Math.max(now - m.arrived, 50), 1000);
      }
      m.cur = next;
      m.arrived = now;

      for (const [code, d] of Object.entries(next.drivers)) {
        let samples = history.current.get(code);
        if (!samples) history.current.set(code, (samples = []));
        samples.push({ t: next.t, speed: d.speed, throttle: d.throttle, brake: d.brake, gear: d.gear });
        while (samples.length && samples[0].t < next.t - HISTORY_S) samples.shift();
      }
      setFrame(next);
    };

    const connect = () => {
      const ws = new WebSocket(streamUrl());
      socket.current = ws;
      ws.onopen = () => {
        retry = 1000;
        setConnected(true);
      };
      ws.onmessage = (event) => {
        let message: ServerMessage;
        try {
          message = JSON.parse(event.data);
        } catch {
          return;
        }
        setPlayback(message.state);
        if (message.type === "meta") {
          setMeta(message.meta ?? {});
        } else if (message.type === "frame") {
          onFrame(message.frame);
        }
      };
      ws.onclose = () => {
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
  }, []);

  const send = useCallback((message: ControlMessage) => {
    if (socket.current?.readyState === WebSocket.OPEN) {
      socket.current.send(JSON.stringify(message));
    }
  }, []);

  return { connected, meta, frame, playback, motion, history, send };
}
