"use client";

import { formatTime } from "@/lib/format";
import type { Meta } from "@/lib/types";

const FLAG_COLORS: Record<string, string> = {
  GREEN: "#2fbf71",
  CLEAR: "#2fbf71",
  YELLOW: "#ffd12e",
  "DOUBLE YELLOW": "#ffd12e",
  RED: "#e8002d",
  BLUE: "#3b82f6",
  "BLACK AND WHITE": "#d6d9df",
  CHEQUERED: "#d6d9df",
};

export default function RaceControl({ meta, t }: { meta: Meta; t: number }) {
  // Only what had been announced at the time being watched
  const messages = (meta.race_control_messages ?? [])
    .filter((m) => m.time == null || m.time <= t)
    .slice()
    .reverse();

  if (messages.length === 0) return <div className="empty">Aucun message de la direction de course.</div>;

  return (
    <ul className="race-control">
      {messages.map((m, i) => (
        <li key={i}>
          <span className="rc-time">{m.time != null ? formatTime(m.time) : ""}</span>
          {m.flag ? (
            <span className="rc-flag" style={{ background: FLAG_COLORS[m.flag.toUpperCase()] ?? "#4a5160" }}>
              {m.flag}
            </span>
          ) : (
            <span className="rc-category">{m.category}</span>
          )}
          <span className="rc-message">{m.message}</span>
        </li>
      ))}
    </ul>
  );
}
