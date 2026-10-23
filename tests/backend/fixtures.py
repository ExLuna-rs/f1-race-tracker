"""Synthetic live timing messages shaped like the real feed."""

import math
from datetime import datetime, timedelta, timezone

from server.live.feed import encode_z

START = datetime(2025, 3, 16, 4, 0, 0, tzinfo=timezone.utc)
SAMPLES_PER_LAP = 200
SAMPLE_DT = 0.25


def utc(seconds):
    return (START + timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z")


def circle(i, phase=0.0):
    angle = 2 * math.pi * (i / SAMPLES_PER_LAP) + phase
    return round(5000 * math.cos(angle)), round(5000 * math.sin(angle))


def initial_messages():
    return [
        ("DriverList", {
            "1": {"Tla": "VER", "TeamColour": "3671C6", "FullName": "Max Verstappen",
                  "TeamName": "Red Bull Racing", "RacingNumber": "1"},
            "44": {"Tla": "HAM", "TeamColour": "E80020", "FullName": "Lewis Hamilton",
                   "TeamName": "Ferrari", "RacingNumber": "44"},
        }, utc(0)),
        ("SessionInfo", {"Name": "Race", "Type": "Race",
                         "Meeting": {"Name": "Australian Grand Prix",
                                     "Circuit": {"Key": 10, "ShortName": "Melbourne"}}}, utc(0)),
        ("LapCount", {"CurrentLap": 1, "TotalLaps": 3}, utc(0)),
        ("TrackStatus", {"Status": "1", "Message": "AllClear"}, utc(0)),
        ("TimingData", {"Lines": {
            "1": {"Position": "1", "NumberOfLaps": 0, "GapToLeader": "",
                  "IntervalToPositionAhead": {"Value": ""}, "InPit": False},
            "44": {"Position": "2", "NumberOfLaps": 0, "GapToLeader": "+1.2",
                   "IntervalToPositionAhead": {"Value": "+1.2"}, "InPit": False},
        }}, utc(0)),
        ("TimingAppData", {"Lines": {
            "1": {"Stints": [{"Compound": "MEDIUM", "New": "true", "TotalLaps": 0}]},
            "44": {"Stints": [{"Compound": "HARD", "New": "false", "TotalLaps": 3}]},
        }}, utc(0)),
    ]


def position_message(sample_start, count):
    samples = []
    for i in range(sample_start, sample_start + count):
        ver_x, ver_y = circle(i)
        ham_x, ham_y = circle(i, phase=-0.1)
        samples.append({
            "Timestamp": utc(i * SAMPLE_DT),
            "Entries": {
                "1": {"Status": "OnTrack", "X": ver_x, "Y": ver_y, "Z": 0},
                "44": {"Status": "OnTrack", "X": ham_x, "Y": ham_y, "Z": 0},
            },
        })
    return ("Position.z", encode_z({"Position": samples}), samples[-1]["Timestamp"])


def car_data_message(seconds, speed):
    return ("CarData.z", encode_z({"Entries": [{
        "Utc": utc(seconds),
        "Cars": {"1": {"Channels": {"0": 11000, "2": speed, "3": 7, "4": 100, "5": 0, "45": 12}}},
    }]}), utc(seconds))


def lap_update(seconds, laps):
    return ("TimingData", {"Lines": {"1": {"NumberOfLaps": laps}, "44": {"NumberOfLaps": laps}}},
            utc(seconds))


def race_messages(laps=2):
    """Two cars driving `laps` laps of a circle, with positions every 0.25s."""
    messages = initial_messages()
    batch = 4
    for lap in range(laps):
        messages.append(lap_update(lap * SAMPLES_PER_LAP * SAMPLE_DT, lap + 1))
        for start in range(lap * SAMPLES_PER_LAP, (lap + 1) * SAMPLES_PER_LAP, batch):
            messages.append(position_message(start, batch))
    messages.append(lap_update(laps * SAMPLES_PER_LAP * SAMPLE_DT, laps + 1))
    messages.append(position_message(laps * SAMPLES_PER_LAP, batch))
    return messages
