import importlib
import json

import pytest
from fastapi.testclient import TestClient

from server.hub import timeline_from_recording
from tests.backend.fixtures import race_messages


def write_recording(path, messages):
    with open(path, "w") as f:
        for topic, data, ts in messages:
            f.write(json.dumps({"topic": topic, "data": data, "utc": ts}) + "\n")


@pytest.fixture
def server(tmp_path, monkeypatch):
    monkeypatch.setenv("F1_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ADMIN_PASSWORD", "secret")
    monkeypatch.delenv("LIVE_AUTOSTART", raising=False)
    import server.app as app_module

    app_module = importlib.reload(app_module)
    return app_module, TestClient(app_module.app)


def test_recording_rebuilds_the_same_frames(tmp_path):
    path = tmp_path / "race.jsonl"
    write_recording(path, race_messages(laps=2))
    timeline = timeline_from_recording(str(path))
    assert timeline.mode == "recording"
    assert timeline.duration == pytest.approx(100.75)
    assert timeline.meta["track"] is not None
    _, frame = timeline.frame_at(10)
    assert set(json.loads(frame)["drivers"]) == {"VER", "HAM"}


def test_admin_requires_password(server):
    _, client = server
    assert client.get("/api/admin/token").status_code == 401
    ok = client.get("/api/admin/token", headers={"X-Admin-Password": "secret"})
    assert ok.status_code == 200 and ok.json()["present"] is False


def test_admin_disabled_without_password(tmp_path, monkeypatch):
    monkeypatch.setenv("F1_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ADMIN_PASSWORD", "")
    import server.app as app_module

    client = TestClient(importlib.reload(app_module).app)
    assert client.get("/api/admin/token").status_code == 403


def test_bad_token_is_rejected(server):
    _, client = server
    r = client.put("/api/admin/token", json={"token": "garbage"},
                   headers={"X-Admin-Password": "secret"})
    assert r.status_code == 400


def test_recording_name_cannot_escape_folder(server):
    _, client = server
    r = client.post("/api/admin/recording", json={"name": "../f1tv_token"},
                    headers={"X-Admin-Password": "secret"})
    assert r.status_code == 400


def test_websocket_streams_meta_then_frames(server, tmp_path):
    app_module, client = server
    path = tmp_path / "race.jsonl"
    write_recording(path, race_messages(laps=2))
    app_module.hub.library.add("aus", "live", timeline_from_recording(str(path)))

    with client.websocket_connect("/ws?session=aus") as ws:
        meta = ws.receive_json()
        assert meta["type"] == "meta"
        assert meta["meta"]["session"]["meeting"] == "Australian Grand Prix"
        assert meta["state"]["mode"] == "recording"

        frame = ws.receive_json()
        assert frame["type"] == "frame"
        assert frame["frame"]["t"] == 0.0

        ws.send_json({"type": "seek", "t": 50})
        for _ in range(10):
            frame = ws.receive_json()
            if frame["type"] == "frame" and frame["frame"]["t"] >= 50:
                break
        assert frame["frame"]["t"] >= 50


def test_new_token_reconnects_live_timing(server, monkeypatch):
    app_module, client = server
    calls = []
    monkeypatch.setattr(app_module.hub, "reconnect_live", lambda: calls.append(1))
    headers = {"X-Admin-Password": "secret"}
    token = "header.eyJleHAiOiAxfQ.signature"  # {"exp": 1}

    assert client.put("/api/admin/token", json={"token": token}, headers=headers).json()["changed"]
    assert not client.put("/api/admin/token", json={"token": token}, headers=headers).json()["changed"]
    assert calls == [1]


def test_status_shows_token_expiry_but_not_the_token(server):
    _, client = server
    token = "header.eyJleHAiOiAxfQ.signature"
    client.put("/api/admin/token", json={"token": token}, headers={"X-Admin-Password": "secret"})
    status = client.get("/api/status").json()
    assert status["token"] == {"present": True, "expires_at": 1, "expired": True}
    assert token not in json.dumps(status)
