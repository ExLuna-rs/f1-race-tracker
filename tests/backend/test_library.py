import json
from datetime import datetime, timezone

import pytest

from server.hub import Hub, timeline_from_recording
from server.library import Library
from server.schedule import next_session
from server.token_store import TokenStore
from tests.backend.fixtures import initial_messages, race_messages, utc
from tests.backend.test_app import server, write_recording  # noqa: F401  (fixture)


def make_hub(tmp_path):
    return Hub(str(tmp_path), TokenStore(str(tmp_path / "token")))


def with_key(messages, key, name="Race"):
    """The fixture feed, as the session with this SessionInfo key."""
    out = []
    for topic, data, ts in messages:
        if topic == "SessionInfo":
            data = {**data, "Key": key, "Name": name}
        out.append((topic, data, ts))
    return out


def test_library_saves_and_reopens_the_same_frames(tmp_path):
    path = tmp_path / "race.jsonl"
    write_recording(path, race_messages(laps=2))
    timeline = timeline_from_recording(str(path))
    library = Library(str(tmp_path / "library"))

    info = library.add("aus", "live", timeline)
    assert info["meeting"] == "Australian Grand Prix" and info["duration"] == timeline.duration
    reopened = Library(str(tmp_path / "library")).get("aus")
    assert reopened.mode == "recording" and reopened.finished
    assert len(reopened) == len(timeline)
    assert reopened.frame_at(50) == timeline.frame_at(50)
    assert reopened.meta == timeline.meta
    assert [e["id"] for e in library.list()] == ["aus"]


def test_library_keeps_only_a_few_sessions_in_memory(tmp_path):
    path = tmp_path / "race.jsonl"
    write_recording(path, race_messages(laps=1))
    timeline = timeline_from_recording(str(path))
    library = Library(str(tmp_path / "library"), keep_in_memory=2)
    for session_id in ("a", "b", "c"):
        library.add(session_id, "live", timeline)
        library.get(session_id)
    assert list(library._cache) == ["b", "c"]


def test_library_rejects_ids_outside_its_folder(tmp_path):
    library = Library(str(tmp_path / "library"))
    with pytest.raises(ValueError):
        library.get("../token")
    with pytest.raises(KeyError):
        library.get("missing")


def test_each_live_session_goes_into_the_library_when_the_next_starts(tmp_path):
    hub = make_hub(tmp_path)
    for message in with_key(race_messages(laps=3), "100", "Qualifying"):
        hub.on_live_message(*message)
    qualifying = hub.live_timeline
    assert hub.live.key == "100" and len(qualifying) > 0
    assert hub.library.list() == []

    for message in with_key(initial_messages(), "101"):
        hub.on_live_message(*message)
    assert hub.live.key == "101" and hub.live_timeline is not qualifying
    [entry] = hub.library.list()
    assert entry["id"] == "live-100" and entry["name"] == "Qualifying"
    assert entry["source"] == "live"


def test_session_end_saves_it_and_a_timing_only_session_is_skipped(tmp_path):
    hub = make_hub(tmp_path)
    for message in with_key(race_messages(laps=2), "100"):
        hub.on_live_message(*message)
    hub.on_live_message("SessionStatus", {"Status": "Finalised"}, utc(200))
    assert [e["id"] for e in hub.library.list()] == ["live-100"]

    # Connecting after a session ended only gets its final state, no cars
    for message in with_key(initial_messages(), "101"):
        hub.on_live_message(*message)
    hub.on_live_message("SessionStatus", {"Status": "Finalised"}, utc(500))
    hub.stop_live()
    hub._finish_live()
    assert [e["id"] for e in hub.library.list()] == ["live-100"]


def test_restart_mid_session_picks_up_the_recording(tmp_path):
    hub = make_hub(tmp_path)
    messages = with_key(race_messages(laps=2), "100")
    for message in messages[: len(messages) // 2]:
        hub.on_live_message(*message)
    before = hub.live_timeline.duration

    restarted = make_hub(tmp_path)
    restarted.on_live_message(*messages[1])  # SessionInfo comes with the subscription
    assert restarted.live_timeline.duration == pytest.approx(before)


def test_messages_before_session_info_are_kept_for_it(tmp_path):
    hub = make_hub(tmp_path)
    messages = with_key(race_messages(laps=1), "100")
    info = next(m for m in messages if m[0] == "SessionInfo")
    for message in [m for m in messages if m[0] != "SessionInfo"][:20]:
        hub.on_live_message(*message)
    assert hub.live is None
    hub.on_live_message(*info)
    assert len(hub.live_timeline) > 0


def test_websocket_follows_live_or_opens_a_library_session(server, tmp_path):  # noqa: F811
    app_module, client = server
    for message in with_key(race_messages(laps=2), "100"):
        app_module.hub.on_live_message(*message)

    with client.websocket_connect("/ws") as ws:
        meta = ws.receive_json()
        assert meta["state"]["mode"] == "live"

    with client.websocket_connect("/ws?session=nope") as ws:
        assert ws.receive_json()["type"] == "error"

    assert client.get("/api/status").json()["live_active"] is True
    assert client.get("/api/library").json() == []


def test_admin_can_delete_from_the_library(server, tmp_path):  # noqa: F811
    app_module, client = server
    path = tmp_path / "race.jsonl"
    write_recording(path, race_messages(laps=1))
    app_module.hub.library.add("aus", "live", timeline_from_recording(str(path)))
    headers = {"X-Admin-Password": "secret"}
    assert client.delete("/api/admin/library/aus").status_code == 401
    assert client.delete("/api/admin/library/aus", headers=headers).json() == []
    assert client.delete("/api/admin/library/aus", headers=headers).status_code == 404


def test_next_session_is_the_first_not_over_yet():
    weekends = {2026: [
        {"event_name": "Mexico City Grand Prix", "round_number": 19, "session_dates": {
            "Practice 1": "2026-10-23T12:30:00-06:00",
            "Qualifying": "2026-10-24T15:00:00-06:00",
            "Race": "2026-10-25T14:00:00-06:00",
        }},
    ]}
    pick = lambda now: next_session(lambda year: weekends.get(year, []), now)
    assert pick(datetime(2026, 10, 24, 20, 0, tzinfo=timezone.utc))["name"] == "Qualifying"
    # Still on an hour after the start
    assert pick(datetime(2026, 10, 24, 22, 0, tzinfo=timezone.utc))["name"] == "Qualifying"
    nxt = pick(datetime(2026, 10, 25, 1, 0, tzinfo=timezone.utc))
    assert nxt["name"] == "Race" and nxt["start"] == "2026-10-25T20:00:00+00:00"
    assert pick(datetime(2026, 12, 1, tzinfo=timezone.utc)) is None
