"""
Builds a timeline for a finished race or sprint from FastF1's archive.

This reuses the desktop app's telemetry pipeline (src/f1_data.py), so frames
are identical to the ones the Arcade replay draws. The archive is free and
includes car positions, no F1 TV token needed.
"""

from src.f1_data import (
    enable_cache,
    get_circuit_rotation,
    get_driver_colors,
    get_race_telemetry,
    load_session,
)

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


def build_replay_timeline(year, round_number, session_type="R", sample_hz=4):
    if session_type not in REPLAY_SESSION_TYPES:
        raise ValueError("Replays currently support races (R) and sprints (S)")

    enable_cache()
    session = load_session(year, round_number, session_type)
    if session is None:
        raise RuntimeError(f"Could not load {year} round {round_number} {session_type}")

    data = get_race_telemetry(session, session_type=session_type)
    timeline = Timeline("replay", min_interval_s=1 / sample_hz)

    for frame in data["frames"]:
        frame["track_status"] = _status_at(data["track_statuses"], frame["t"])
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
        },
        "drivers": _driver_info(session, colors),
        "total_laps": data["total_laps"],
        "race_control_messages": data["race_control_messages"],
        "track_statuses": data["track_statuses"],
        "stints": _stints(session),
        "track": _track_outline(session),
        "rotation": rotation,
        "max_tyre_life": data.get("max_tyre_life", {}),
    })
    return timeline
