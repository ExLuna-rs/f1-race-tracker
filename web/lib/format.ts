import type { DriverFrame, Frame, SessionInfo } from "./types";

export const TYRES: Record<number, { label: string; name: string; color: string }> = {
  0: { label: "S", name: "Tendre", color: "#e8002d" },
  1: { label: "M", name: "Medium", color: "#ffd12e" },
  2: { label: "H", name: "Dur", color: "#f0f0f0" },
  3: { label: "I", name: "Intermédiaire", color: "#43b02a" },
  4: { label: "W", name: "Pluie", color: "#0067ad" },
};

export function tyreFromCompound(compound: string) {
  const index = ["SOFT", "MEDIUM", "HARD", "INTERMEDIATE", "WET"].indexOf(compound.toUpperCase());
  return TYRES[index] ?? { label: "?", name: compound || "Inconnu", color: "#777" };
}

export const TRACK_STATUS: Record<string, { label: string; color: string }> = {
  "1": { label: "Piste dégagée", color: "#2fbf71" },
  "2": { label: "Drapeau jaune", color: "#ffd12e" },
  "4": { label: "Safety car", color: "#ff9f1c" },
  "5": { label: "Drapeau rouge", color: "#e8002d" },
  "6": { label: "Virtual safety car", color: "#ff9f1c" },
  "7": { label: "Fin de VSC", color: "#ffc857" },
};

export function formatTime(seconds: number) {
  const s = Math.max(Math.floor(seconds), 0);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  const mm = String(m).padStart(2, "0");
  const ss = String(sec).padStart(2, "0");
  return h > 0 ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
}

export type SessionKind = "race" | "qualifying" | "practice";

export function sessionKind(session?: SessionInfo): SessionKind {
  const type = (session?.type ?? "").toLowerCase();
  const name = (session?.name ?? "").toLowerCase();
  if (type === "r" || type === "s" || type === "race") return "race";
  if (type.startsWith("qualifying") || name.includes("qualifying") || name.includes("shootout")) {
    return "qualifying";
  }
  if (type.startsWith("practice") || name.includes("practice")) return "practice";
  return "race";
}

// DRS channel values: 8 = eligible, 10/12/14 = flap open
export function drsState(value: number): "off" | "eligible" | "open" {
  if (value >= 10) return "open";
  if (value === 8) return "eligible";
  return "off";
}

// Replays have no timing gaps, so estimate them from the distance between
// cars and the leader's average speed since the start.
export function estimatedGap(driver: DriverFrame, leader: DriverFrame | undefined, frame: Frame) {
  if (!leader || driver === leader || driver.dist == null || leader.dist == null) return "";
  const lapsDown = leader.lap - driver.lap;
  const delta = leader.dist - driver.dist;
  const avgSpeed = frame.t > 60 ? leader.dist / frame.t : 0;
  if (avgSpeed <= 10) return "";
  const seconds = delta / avgSpeed;
  if (lapsDown >= 1 && seconds > 60) return `+${lapsDown} T`;
  return `+${seconds.toFixed(1)}`;
}

export function shortGap(value?: string) {
  if (!value) return "";
  // The feed writes lapped cars as "1L" or "+1 LAP"
  const lap = value.match(/^\+?(\d+)\s*L/i);
  if (lap) return `+${lap[1]} T`;
  return value;
}
