"""
Turns raw live timing messages into replay-style frames.

Frames use the same shape as the desktop replay (see telemetry.md) so the web
client can draw live and replayed sessions the same way, plus a few live-only
fields (gaps, lap times, retired flags).
"""

from datetime import datetime, timezone

from src.lib.tyres import get_tyre_compound_int

from server.live.feed import as_list, decode_z, deep_merge, topic_name

# CarData channel ids used by the feed
CHANNEL_RPM = "0"
CHANNEL_SPEED = "2"
CHANNEL_GEAR = "3"
CHANNEL_THROTTLE = "4"
CHANNEL_BRAKE = "5"
CHANNEL_DRS = "45"

# Without position data we still emit frames, just less often
FALLBACK_FRAME_INTERVAL_S = 1.0
# How long without a Position message before switching to the fallback clock
POSITION_STALE_S = 10.0
# Minimum points for a lap trace to be used as the track outline
MIN_TRACK_POINTS = 150


def parse_utc(value):
    """Parse feed timestamps such as '2025-03-16T04:03:12.1234567Z'."""
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    text = value.rstrip("Z")
    if "." in text:
        head, frac = text.split(".", 1)
        # Python 3.10 only accepts 3 or 6 fractional digits
        text = f"{head}.{frac[:6].ljust(6, '0')}"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _value(field):
    """Timing fields are either plain strings or {"Value": "..."} objects."""
    if isinstance(field, dict):
        return field.get("Value", "")
    return field if field is not None else ""


def _as_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value, default=None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_duration(text):
    """Parse 'HH:MM:SS' into seconds."""
    try:
        h, m, s = str(text).split(":")
        return int(h) * 3600 + int(m) * 60 + float(s)
    except (TypeError, ValueError):
        return None


def _format_duration(seconds):
    seconds = max(int(seconds), 0)
    return f"{seconds // 3600:02d}:{seconds // 60 % 60:02d}:{seconds % 60:02d}"


def _race_control_message(message, time):
    """Same keys as the replay pipeline's messages, plus the raw feed fields."""
    out = dict(message)
    out.update({
        "time": time,
        "category": str(message.get("Category", "")),
        "message": str(message.get("Message", "")),
        "flag": str(message.get("Flag", "")),
        "scope": str(message.get("Scope", "")),
        "sector": str(message.get("Sector", "")),
        "racing_number": str(message.get("RacingNumber", "")),
        "lap": _as_int(message.get("Lap"), None),
    })
    return out


class LiveState:
    """Accumulates the feed and emits frames through `on_frame(t, frame)`."""

    def __init__(self, on_frame=None, on_meta=None, circuit_provider=None):
        self.topics = {}
        self.on_frame = on_frame or (lambda t, frame: None)
        self.on_meta = on_meta or (lambda meta: None)
        # circuit_provider(circuit_key, year) -> {"track", "rotation", "corners"}
        self.circuit_provider = circuit_provider
        self.circuit = None
        self._circuit_requested = False

        self.positions = {}  # racing number -> {"x", "y", "status"}
        self.car_data = {}  # racing number -> channels dict
        self.origin_utc = None
        self.last_emit_utc = None
        self.last_position_utc = None

        self.track = None
        self._lap_traces = {}  # racing number -> (lap, [[x, y], ...])
        self.track_statuses = []
        self._meta_dirty = False

    # Feed input ---------------------------------------------------------

    def apply_snapshot(self, snapshot, utc=None):
        """Apply the full state sent in reply to the Subscribe call."""
        for topic, data in snapshot.items():
            self.apply(topic, data, utc)

    def apply(self, topic, data, utc=None):
        name = topic_name(topic)
        if topic.endswith(".z"):
            data = decode_z(data)
        utc = parse_utc(utc)

        if name == "Position":
            self._apply_positions(data)
            return
        if name == "CarData":
            self._apply_car_data(data)
        else:
            self.topics[name] = deep_merge(self.topics.get(name), data)
            if name in ("DriverList", "SessionInfo", "RaceControlMessages",
                        "TimingAppData", "LapCount"):
                self._meta_dirty = True
            if name == "TrackStatus":
                self._record_track_status(utc)
            if name == "SessionInfo":
                self._load_circuit()

        if utc is not None and self._position_is_stale(utc):
            if (self.last_emit_utc is None
                    or (utc - self.last_emit_utc).total_seconds() >= FALLBACK_FRAME_INTERVAL_S):
                self._emit(utc)
        self._flush_meta()

    def _position_is_stale(self, utc):
        if self.last_position_utc is None:
            return True
        return (utc - self.last_position_utc).total_seconds() > POSITION_STALE_S

    def _apply_positions(self, data):
        for sample in (data or {}).get("Position", []):
            utc = parse_utc(sample.get("Timestamp"))
            for number, entry in (sample.get("Entries") or {}).items():
                x, y = entry.get("X"), entry.get("Y")
                self.positions[number] = {
                    "x": float(x or 0),
                    "y": float(y or 0),
                    "status": entry.get("Status", ""),
                }
                self._trace_lap(number, x, y)
            if utc is None:
                continue
            self.last_position_utc = utc
            if self.last_emit_utc is None or utc > self.last_emit_utc:
                self._emit(utc)
        self._flush_meta()

    def _apply_car_data(self, data):
        entries = (data or {}).get("Entries", [])
        if not entries:
            return
        # Samples are chronological, so the last one wins
        for number, car in (entries[-1].get("Cars") or {}).items():
            self.car_data[number] = car.get("Channels", {})

    def _record_track_status(self, utc):
        status = str((self.topics.get("TrackStatus") or {}).get("Status", ""))
        if self.track_statuses and self.track_statuses[-1]["status"] == status:
            return
        start = self._t(utc) if utc is not None else None
        if self.track_statuses:
            self.track_statuses[-1]["end_time"] = start
        self.track_statuses.append({"status": status, "start_time": start, "end_time": None})
        self._meta_dirty = True

    def _load_circuit(self):
        if self._circuit_requested or self.circuit_provider is None:
            return
        info = self.topics.get("SessionInfo") or {}
        key = ((info.get("Meeting") or {}).get("Circuit") or {}).get("Key")
        year = _as_int(str(info.get("StartDate") or info.get("Path") or "")[:4], None)
        if key is None or year is None:
            return
        self._circuit_requested = True
        try:
            self.circuit = self.circuit_provider(key, year)
        except Exception:
            self.circuit = None
        if self.circuit:
            self._meta_dirty = True

    def _trace_lap(self, number, x, y):
        """Use the first clean lap any car completes as the track outline."""
        if self.track is not None or x is None or y is None:
            return
        if self.circuit and self.circuit.get("track"):
            return
        line = self._timing_line(number)
        lap = _as_int(line.get("NumberOfLaps"), -1)
        # A trace only counts once it started at a lap change, not mid-lap
        traced_lap, points, complete = self._lap_traces.get(number, (lap, [], False))
        if lap != traced_lap:
            if (complete and len(points) >= MIN_TRACK_POINTS
                    and not line.get("InPit") and not line.get("PitOut")):
                self.track = points
                self._lap_traces.clear()
                self._meta_dirty = True
                return
            points, complete = [], True
        if x or y:
            points.append([float(x), float(y)])
        self._lap_traces[number] = (lap, points, complete)

    # Frame building -----------------------------------------------------

    def _t(self, utc):
        if self.origin_utc is None:
            self.origin_utc = utc
            # Race control message times are relative to the origin
            self._meta_dirty = True
        return round((utc - self.origin_utc).total_seconds(), 3)

    def _timing_line(self, number):
        return ((self.topics.get("TimingData") or {}).get("Lines") or {}).get(number) or {}

    def driver_code(self, number):
        info = (self.topics.get("DriverList") or {}).get(number) or {}
        return info.get("Tla") or str(number)

    def _driver_numbers(self):
        numbers = set((self.topics.get("DriverList") or {}).keys())
        numbers |= set(((self.topics.get("TimingData") or {}).get("Lines") or {}).keys())
        numbers |= set(self.positions.keys())
        return sorted((n for n in numbers if n.isdigit()), key=int)

    def _clock_at(self, utc):
        """Session time remaining, extrapolated like the official timing screen."""
        clock = self.topics.get("ExtrapolatedClock") or {}
        remaining = _parse_duration(clock.get("Remaining"))
        if remaining is None:
            return ""
        since = parse_utc(clock.get("Utc"))
        if clock.get("Extrapolating") and since is not None and utc is not None:
            remaining -= max((utc - since).total_seconds(), 0)
        return _format_duration(remaining)

    def _session_status(self):
        status = (self.topics.get("SessionStatus") or {}).get("Status")
        if status:
            return status
        # Recordings started mid-session only have the SessionData history
        series = as_list((self.topics.get("SessionData") or {}).get("StatusSeries"))
        for entry in reversed(series):
            if isinstance(entry, dict) and entry.get("SessionStatus"):
                return entry["SessionStatus"]
        return ""

    def build_frame(self, t, utc=None):
        drivers = {}
        app_lines = (self.topics.get("TimingAppData") or {}).get("Lines") or {}
        for number in self._driver_numbers():
            line = self._timing_line(number)
            stints = as_list((app_lines.get(number) or {}).get("Stints"))
            stint = stints[-1] if stints else {}
            if not isinstance(stint, dict):
                stint = {}
            pos = self.positions.get(number, {})
            channels = self.car_data.get(number, {})

            gap = line.get("GapToLeader")
            if gap is None:
                gap = line.get("TimeDiffToFastest")
            interval = line.get("IntervalToPositionAhead")
            if interval is None:
                interval = line.get("TimeDiffToPositionAhead")

            drivers[self.driver_code(number)] = {
                "number": number,
                "x": pos.get("x"),
                "y": pos.get("y"),
                "position": _as_int(line.get("Position"), 0),
                "lap": _as_int(line.get("NumberOfLaps"), 0),
                "tyre": float(get_tyre_compound_int(str(stint.get("Compound", "")))),
                "tyre_life": float(_as_int(stint.get("TotalLaps"), 0)),
                "speed": _as_float(channels.get(CHANNEL_SPEED), 0.0),
                "gear": _as_int(channels.get(CHANNEL_GEAR), 0),
                "drs": _as_int(channels.get(CHANNEL_DRS), 0),
                "throttle": _as_float(channels.get(CHANNEL_THROTTLE), 0.0),
                "brake": _as_float(channels.get(CHANNEL_BRAKE), 0.0),
                "rpm": _as_int(channels.get(CHANNEL_RPM), 0),
                "in_pit": bool(line.get("InPit")) or pos.get("status") == "OffTrack",
                "retired": bool(line.get("Retired") or line.get("Stopped")),
                "knocked_out": bool(line.get("KnockedOut")),
                "gap": _value(gap),
                "interval": _value(interval),
                "last_lap": _value(line.get("LastLapTime")),
                "best_lap": _value(line.get("BestLapTime")),
                "sectors": [_value(s) for s in as_list(line.get("Sectors"))
                            if isinstance(s, (dict, str))],
            }

        lap_count = self.topics.get("LapCount") or {}
        leader_lap = max((d["lap"] for d in drivers.values()), default=0)
        weather = self.topics.get("WeatherData") or {}
        frame = {
            "t": t,
            "lap": _as_int(lap_count.get("CurrentLap"), leader_lap),
            "drivers": drivers,
            "track_status": str((self.topics.get("TrackStatus") or {}).get("Status", "")),
            "session_status": self._session_status(),
            "clock": self._clock_at(utc),
        }
        if weather:
            rain = _as_float(weather.get("Rainfall"), 0.0)
            frame["weather"] = {
                "track_temp": _as_float(weather.get("TrackTemp")),
                "air_temp": _as_float(weather.get("AirTemp")),
                "humidity": _as_float(weather.get("Humidity")),
                "wind_speed": _as_float(weather.get("WindSpeed")),
                "wind_direction": _as_float(weather.get("WindDirection")),
                "rain_state": "RAINING" if rain and rain >= 0.5 else "DRY",
            }
        return frame

    def _emit(self, utc):
        self.last_emit_utc = utc
        t = self._t(utc)
        self.on_frame(t, self.build_frame(t, utc))

    # Metadata -----------------------------------------------------------

    def build_meta(self):
        info = self.topics.get("SessionInfo") or {}
        meeting = info.get("Meeting") or {}
        drivers = []
        for number, driver in sorted((self.topics.get("DriverList") or {}).items(),
                                     key=lambda item: _as_int(item[0])):
            if not isinstance(driver, dict) or not number.isdigit():
                continue
            colour = driver.get("TeamColour") or "FFFFFF"
            drivers.append({
                "code": driver.get("Tla") or number,
                "number": number,
                "name": driver.get("FullName", ""),
                "team": driver.get("TeamName", ""),
                "color": f"#{colour.lstrip('#')}",
            })

        app_lines = (self.topics.get("TimingAppData") or {}).get("Lines") or {}
        stints = {}
        for number, line in app_lines.items():
            # Same shape as replays: laps driven in the stint, tyre age at the
            # start, and the lap the stint started on
            driver_stints, start_lap = [], 1
            for s in as_list((line or {}).get("Stints")):
                if not isinstance(s, dict):
                    continue
                age_at_start = _as_int(s.get("StartLaps"), 0)
                laps = max(_as_int(s.get("TotalLaps"), 0) - age_at_start, 0)
                driver_stints.append({
                    "compound": s.get("Compound", ""),
                    "new": str(s.get("New", "")).lower() == "true",
                    "laps": laps,
                    "start_laps": age_at_start,
                    "start_lap": start_lap,
                })
                start_lap += laps
            stints[self.driver_code(number)] = driver_stints

        messages = []
        for message in as_list((self.topics.get("RaceControlMessages") or {}).get("Messages")):
            if not isinstance(message, dict):
                continue
            sent = parse_utc(message.get("Utc"))
            time = None
            if sent is not None and self.origin_utc is not None:
                time = round((sent - self.origin_utc).total_seconds(), 3)
            messages.append(_race_control_message(message, time))
        circuit = self.circuit or {}

        return {
            "session": {
                "name": info.get("Name", ""),
                "type": info.get("Type", ""),
                "meeting": meeting.get("Name", ""),
                "circuit": (meeting.get("Circuit") or {}).get("ShortName", ""),
                "circuit_key": (meeting.get("Circuit") or {}).get("Key"),
                "start": info.get("StartDate", ""),
            },
            "drivers": drivers,
            "total_laps": _as_int((self.topics.get("LapCount") or {}).get("TotalLaps"), 0),
            "race_control_messages": messages,
            "track_statuses": [dict(s) for s in self.track_statuses],
            "stints": stints,
            "track": circuit.get("track") or self.track,
            "rotation": circuit.get("rotation", 0.0),
            "corners": circuit.get("corners", []),
            "origin_utc": self.origin_utc.isoformat() if self.origin_utc else None,
        }

    def _flush_meta(self):
        if self._meta_dirty:
            self._meta_dirty = False
            self.on_meta(self.build_meta())
