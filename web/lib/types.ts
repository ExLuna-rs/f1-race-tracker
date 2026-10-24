// Shapes sent by the backend, see docs/WebServer.md and telemetry.md.
// Replays come from the desktop pipeline and live sessions from the live
// parser, so the live-only fields are optional.

export type Mode = "live" | "replay" | "recording";

export interface PlaybackState {
  t: number;
  duration: number;
  speed: number;
  paused: boolean;
  live: boolean;
  mode: Mode;
}

export interface DriverInfo {
  code: string;
  number: string;
  name: string;
  team: string;
  color: string;
}

export interface Stint {
  compound: string;
  new: boolean;
  laps: number;
  start_laps: number;
  start_lap?: number;
}

export interface RaceControlMessage {
  time: number | null;
  category: string;
  message: string;
  flag: string;
  scope?: string;
  sector?: string;
  racing_number?: string;
  lap?: number | null;
}

export interface TrackStatusPeriod {
  status: string;
  start_time: number | null;
  end_time: number | null;
}

export interface Corner {
  number: number;
  letter: string;
  x: number;
  y: number;
  angle: number;
}

export interface SessionInfo {
  name: string;
  type: string;
  meeting: string;
  circuit: string;
  year?: number;
  round?: number;
  start?: string;
}

export interface Meta {
  session?: SessionInfo;
  drivers?: DriverInfo[];
  total_laps?: number;
  race_control_messages?: RaceControlMessage[];
  track_statuses?: TrackStatusPeriod[];
  stints?: Record<string, Stint[]>;
  track?: [number, number][] | null;
  rotation?: number;
  corners?: Corner[];
}

export interface DriverFrame {
  number?: string;
  x: number | null;
  y: number | null;
  position: number;
  lap: number;
  tyre: number;
  tyre_life?: number;
  speed: number;
  gear: number;
  drs: number;
  throttle: number;
  brake: number;
  rpm?: number;
  in_pit?: boolean;
  dist?: number;
  rel_dist?: number;
  retired?: boolean;
  knocked_out?: boolean;
  gap?: string;
  interval?: string;
  last_lap?: string;
  best_lap?: string;
  sectors?: string[];
}

export interface Weather {
  track_temp: number | null;
  air_temp: number | null;
  humidity: number | null;
  wind_speed: number | null;
  wind_direction: number | null;
  rain_state: string;
}

export interface Frame {
  t: number;
  lap: number;
  drivers: Record<string, DriverFrame>;
  track_status?: string;
  session_status?: string;
  clock?: string;
  weather?: Weather;
  safety_car?: { x: number; y: number; phase: string; alpha: number } | null;
}

export type ServerMessage =
  | { type: "meta"; meta: Meta; state: PlaybackState }
  | { type: "frame"; state: PlaybackState; frame: Frame };

export type ControlMessage =
  | { type: "play" }
  | { type: "pause" }
  | { type: "live" }
  | { type: "seek"; t: number }
  | { type: "skip"; seconds: number }
  | { type: "speed"; value: number };

export interface TokenStatus {
  present: boolean;
  expires_at: number | null;
  expired: boolean | null;
}

export interface Status {
  mode: Mode;
  session: SessionInfo | null;
  duration: number;
  frames: number;
  live_running: boolean;
  live_connected: boolean;
  live_error: string | null;
  loading: string | null;
  error: string | null;
  token?: TokenStatus;
}
