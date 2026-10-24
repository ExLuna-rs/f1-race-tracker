"""
Builds a timeline for a finished race or sprint from FastF1's archive.

This reuses the desktop app's telemetry pipeline (src/f1_data.py), so frames
are identical to the ones the Arcade replay draws. Since FastF1 3.9 the
archive needs the F1 TV token too, so the stored one is handed to FastF1.
"""

import bisect

from server.timeline import Timeline

REPLAY_SESSION_TYPES = ("R", "S")


def _hex(rgb):
    return "#{:02X}{:02X}{:02X}".format(*(int(c) for c in rgb[:3]))


def _status_at(track_statuses, t):
    status = ""
    for entry in track_statuses:
        if entry["start_time"] is not None and entry["start_time"] <= t:
            status = str(entry["status"])
        else:
            break
    return status


def _corners(session):
    try:
        corners = session.get_circuit_info().corners
        return [
            {"number": int(c["Number"]), "letter": str(c.get("Letter") or ""),
             "x": float(c["X"]), "y": float(c["Y"]), "angle": float(c.get("Angle") or 0)}
            for _, c in corners.iterrows()
        ]
    except Exception:
        return []


def _track_outline(session):
    try:
        pos = session.laps.pick_fastest().get_pos_data()
        return [[float(x), float(y)] for x, y in zip(pos["X"], pos["Y"])]
    except Exception:
        return None


def _stints(session):
    stints = {}
    try:
        for code, laps in session.laps.groupby("Driver"):
            driver_stints = []
            for _, stint_laps in laps.groupby("Stint"):
                first = stint_laps.iloc[0]
                driver_stints.append({
                    "compound": str(first.get("Compound", "")),
                    "new": bool(first.get("FreshTyre", False)),
                    "laps": int(len(stint_laps)),
                    "start_laps": int(first.get("TyreLife", 1) or 1) - 1,
                    "start_lap": int(first.get("LapNumber", 0) or 0),
                })
            stints[str(code)] = driver_stints
    except Exception:
        pass
    return stints


def _driver_info(session, colors):
    drivers = []
    for number in session.drivers:
        info = session.get_driver(number)
        code = info["Abbreviation"]
        drivers.append({
            "code": code,
            "number": str(number),
            "name": str(info.get("FullName", "")),
            "team": str(info.get("TeamName", "")),
            "color": _hex(colors.get(code, (255, 255, 255))),
        })
    return drivers


def _start(session):
    try:
        return session.date.isoformat()
    except Exception:
        return ""


def _lap_times(session):
    """(driver code, lap number) -> lap time in seconds."""
    times = {}
    try:
        for _, lap in session.laps.iterrows():
            seconds = lap["LapTime"].total_seconds()
            # NaT gives NaN
            if seconds == seconds and lap["LapNumber"] == lap["LapNumber"]:
                times[(str(lap["Driver"]), int(lap["LapNumber"]))] = seconds
    except Exception:
        pass
    return times


def _lap_time_text(seconds):
    minutes, rest = divmod(seconds, 60)
    return f"{int(minutes)}:{rest:06.3f}"


def _behind_text(seconds, laps):
    # Same shapes as the live feed, which the site already formats
    return f"+{laps} LAP" if laps >= 1 else f"+{max(seconds, 0):.3f}"


class _RaceTiming:
    """Adds the gap, interval and lap times that the desktop pipeline leaves out.

    Its "dist" restarts at every lap and each car measures laps a little
    differently, so race distance is laps done plus the share of the current
    lap, times one lap length. A car's gap is how long ago the front of the
    race was where that car is now, like the timing screens work it out.
    """

    def __init__(self, frames, lap_times):
        self.lap_times = lap_times
        lap_lengths = {}
        for frame in frames:
            for code, d in frame["drivers"].items():
                key = (code, d.get("lap", 0))
                lap_lengths[key] = max(lap_lengths.get(key, 0.0), d.get("dist") or 0.0)
        full = sorted(v for v in lap_lengths.values() if v > 1000)
        self.lap_length = full[len(full) // 2] if full else 5000.0

        # When the front of the race first reached each distance
        self.front_dist = []
        self.front_time = []
        self.last_lap = {}
        self.laps = {}
        self.best = {}
        # code -> (distance, time and front distance when the car was last seen moving)
        self.moving = {}

    def _front_time_at(self, dist, t):
        idx = bisect.bisect_left(self.front_dist, dist)
        if idx == 0:
            return self.front_time[0]
        if idx == len(self.front_dist):
            return t
        d0, d1 = self.front_dist[idx - 1], self.front_dist[idx]
        t0, t1 = self.front_time[idx - 1], self.front_time[idx]
        return t0 + (t1 - t0) * (dist - d0) / (d1 - d0)

    def annotate(self, frame):
        t = frame["t"]
        cars = []
        for code, d in frame["drivers"].items():
            lap = d.get("lap", 0)
            dist = (max(lap, 1) - 1 + (d.get("rel_dist") or 0.0)) * self.lap_length
            previous = self.last_lap.get(code)
            if previous is not None and lap > previous:
                seconds = self.lap_times.get((code, previous))
                if seconds:
                    self.laps[code] = seconds
                    self.best[code] = min(seconds, self.best.get(code, seconds))
            self.last_lap[code] = lap
            if code in self.laps:
                d["last_lap"] = _lap_time_text(self.laps[code])
                d["best_lap"] = _lap_time_text(self.best[code])
            cars.append((d.get("position") or 99, dist, d, code))

        front = max(dist for _, dist, _, _ in cars)
        if not self.front_dist or front > self.front_dist[-1]:
            self.front_dist.append(front)
            self.front_time.append(t)

        cars.sort(key=lambda car: car[0])
        ahead = None
        for _, dist, d, code in cars:
            # Telemetry of a car that stopped stays where it stopped. Out once
            # the front has done a lap meanwhile, which a red flag never does.
            seen = self.moving.get(code)
            if seen is None or dist - seen[0] > 5:
                self.moving[code] = seen = (dist, t, front)
            if front - seen[2] > self.lap_length:
                d["retired"] = True
                d["gap"] = d["interval"] = ""
                continue
            gap = t - self._front_time_at(dist, t)
            if ahead is None:
                d["gap"] = d["interval"] = ""
            else:
                d["gap"] = _behind_text(gap, int((front - dist) // self.lap_length))
                d["interval"] = _behind_text(gap - ahead[1], int((ahead[0] - dist) // self.lap_length))
            ahead = (dist, gap)


def _use_token(token):
    """Give FastF1 the F1 TV token instead of letting it try to sign in.

    It is stored in FastF1's token file, which the worker processes of
    get_race_telemetry read as well.
    """
    from fastf1.internals.f1account import SubscriptionToken, token_manager

    token_manager.store(SubscriptionToken.from_jwt(token))


def build_replay_timeline(year, round_number, session_type="R", sample_hz=4, token=None):
    # Imported here so the API starts without loading FastF1 and matplotlib's
    # pyplot, which also kept the desktop GUI modules from picking QtAgg in tests
    from src.f1_data import (
        enable_cache,
        get_circuit_rotation,
        get_driver_colors,
        get_race_telemetry,
        load_session,
    )

    if session_type not in REPLAY_SESSION_TYPES:
        raise ValueError("Replays currently support races (R) and sprints (S)")

    if token:
        _use_token(token)
    enable_cache()
    session = load_session(year, round_number, session_type)
    if session is None:
        raise RuntimeError(f"Could not load {year} round {round_number} {session_type}")

    data = get_race_telemetry(session, session_type=session_type)
    timeline = Timeline("replay", min_interval_s=1 / sample_hz)

    timing = _RaceTiming(data["frames"], _lap_times(session))
    for frame in data["frames"]:
        frame["track_status"] = _status_at(data["track_statuses"], frame["t"])
        timing.annotate(frame)
        timeline.add_frame(frame["t"], frame)

    try:
        rotation = float(get_circuit_rotation(session))
    except Exception:
        rotation = 0.0

    colors = data.get("driver_colors") or get_driver_colors(session)
    timeline.set_meta({
        "session": {
            "name": session.name,
            "type": session_type,
            "meeting": str(session.event.get("EventName", "")),
            "circuit": str(session.event.get("Location", "")),
            "year": year,
            "round": round_number,
            "start": _start(session),
        },
        "drivers": _driver_info(session, colors),
        "total_laps": data["total_laps"],
        "race_control_messages": data["race_control_messages"],
        "track_statuses": data["track_statuses"],
        "stints": _stints(session),
        "track": _track_outline(session),
        "rotation": rotation,
        "corners": _corners(session),
        "max_tyre_life": data.get("max_tyre_life", {}),
    })
    return timeline


def _replay_parts(year, round_number, session_type, sample_hz, token):
    timeline = build_replay_timeline(year, round_number, session_type, sample_hz, token)
    return timeline._times, timeline._frames, timeline.meta


def build_replay_timeline_in_subprocess(year, round_number, session_type="R", sample_hz=4, token=None):
    """Run build_replay_timeline in a short-lived process.

    The desktop pipeline builds every 25 FPS frame of the race as Python dicts,
    a few GB at peak. Python keeps that memory after freeing it, so building in
    the API process would leave it at that size until restarted. Only the 4 Hz
    frame JSON and the meta come back, and the child gives everything else back
    to the system when it exits. Spawned, not forked, so the child does not
    start as a copy of the API and its threads.
    """
    import multiprocessing
    from concurrent.futures import ProcessPoolExecutor

    context = multiprocessing.get_context("spawn")
    with ProcessPoolExecutor(max_workers=1, mp_context=context) as pool:
        times, frames, meta = pool.submit(
            _replay_parts, year, round_number, session_type, sample_hz, token
        ).result()
    return Timeline.from_parts("replay", 1 / sample_hz, times, frames, meta)
