import json

from server.live.feed import decode_z, deep_merge, encode_z
from server.live.state import LiveState, parse_utc
from tests.backend.fixtures import (
    SAMPLES_PER_LAP,
    car_data_message,
    initial_messages,
    position_message,
    race_messages,
    utc,
)


def run(messages):
    frames, metas = [], []
    state = LiveState(on_frame=lambda t, f: frames.append((t, f)), on_meta=metas.append)
    for topic, data, ts in messages:
        state.apply(topic, data, ts)
    return state, frames, metas


def test_decode_z_roundtrip():
    obj = {"Position": [{"Timestamp": "x", "Entries": {"1": {"X": 1}}}]}
    assert decode_z(encode_z(obj)) == obj


def test_deep_merge_updates_list_items_by_index():
    state = {"Stints": [{"Compound": "SOFT", "TotalLaps": 1}]}
    merged = deep_merge(state, {"Stints": {"0": {"TotalLaps": 4}, "1": {"Compound": "HARD"}}})
    assert merged["Stints"] == [{"Compound": "SOFT", "TotalLaps": 4}, {"Compound": "HARD"}]


def test_deep_merge_deletes_and_replaces_scalars():
    merged = deep_merge({"a": {"1": 1, "2": 2}, "b": 1}, {"a": {"_deleted": ["1"]}, "b": "x"})
    assert merged == {"a": {"2": 2}, "b": "x"}


def test_parse_utc_handles_seven_digit_fractions():
    parsed = parse_utc("2025-03-16T04:03:12.1234567Z")
    assert parsed.microsecond == 123456
    assert parsed.tzinfo is not None


def test_position_samples_emit_frames_with_replay_fields():
    messages = initial_messages() + [position_message(0, 4), car_data_message(0.75, 301)]
    messages.append(position_message(4, 4))
    _, frames, _ = run(messages)

    assert [t for t, _ in frames][:4] == [0.0, 0.25, 0.5, 0.75]
    last = frames[-1][1]
    ver = last["drivers"]["VER"]
    assert ver["x"] is not None and ver["position"] == 1
    assert ver["tyre"] == 1.0  # MEDIUM
    assert ver["speed"] == 301 and ver["gear"] == 7 and ver["drs"] == 12
    assert last["drivers"]["HAM"]["gap"] == "+1.2"
    assert last["drivers"]["HAM"]["interval"] == "+1.2"
    assert last["track_status"] == "1"
    json.dumps(last)


def test_partial_stint_update_is_merged():
    messages = initial_messages() + [
        ("TimingAppData", {"Lines": {"1": {"Stints": {"0": {"TotalLaps": 5}}}}}, utc(1)),
        position_message(0, 1),
    ]
    state, _, metas = run(messages)
    assert state.build_frame(0)["drivers"]["VER"]["tyre_life"] == 5.0
    assert metas[-1]["stints"]["VER"][0]["compound"] == "MEDIUM"


def test_frames_still_flow_without_position_data():
    messages = initial_messages() + [
        ("WeatherData", {"AirTemp": "20.5", "TrackTemp": "35", "Rainfall": "0"}, utc(1.0)),
        ("TimingData", {"Lines": {"1": {"NumberOfLaps": 1}}}, utc(1.5)),
        ("TimingData", {"Lines": {"1": {"NumberOfLaps": 1}}}, utc(2.2)),
    ]
    _, frames, _ = run(messages)
    assert [t for t, _ in frames] == [0.0, 1.0, 2.2]
    assert frames[-1][1]["weather"]["air_temp"] == 20.5
    assert frames[-1][1]["drivers"]["VER"]["x"] is None


def test_track_outline_comes_from_first_complete_lap():
    state, _, metas = run(race_messages(laps=2))
    assert state.track is not None
    assert len(state.track) == SAMPLES_PER_LAP
    assert metas[-1]["track"] == state.track


def test_meta_lists_drivers_and_session():
    _, _, metas = run(initial_messages())
    meta = metas[-1]
    assert meta["session"]["meeting"] == "Australian Grand Prix"
    assert meta["total_laps"] == 3
    assert meta["drivers"][0] == {
        "code": "VER", "number": "1", "name": "Max Verstappen",
        "team": "Red Bull Racing", "color": "#3671C6",
    }
    assert meta["track_statuses"][0]["status"] == "1"


def test_parse_utc_pads_short_fractions():
    assert parse_utc("2025-03-16T04:03:12.1Z").microsecond == 100000
