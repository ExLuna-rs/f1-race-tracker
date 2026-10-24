import base64
import json
import time

import pytest

from server.timeline import Timeline
from server.token_store import TokenStore, extract_token
from server.viewer import Viewer


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def make_timeline(mode, seconds):
    timeline = Timeline(mode, min_interval_s=0.25)
    for i in range(int(seconds * 4) + 1):
        timeline.add_frame(i * 0.25, {"t": i * 0.25})
    return timeline


def test_timeline_drops_frames_closer_than_interval():
    timeline = Timeline("live", min_interval_s=0.25)
    assert timeline.add_frame(0.0, {})
    assert not timeline.add_frame(0.1, {})
    assert timeline.add_frame(0.3, {})
    assert timeline.frame_at(0.2)[0] == 0.0
    assert timeline.frame_at(99)[0] == 0.3


def test_live_viewer_follows_head():
    timeline = make_timeline("live", 10)
    viewer = Viewer(timeline, FakeClock())
    assert viewer.position() == 10
    timeline.add_frame(11, {})
    assert viewer.position() == 11


def test_live_viewer_can_rewind_then_catch_up():
    clock = FakeClock()
    timeline = make_timeline("live", 60)
    viewer = Viewer(timeline, clock)

    viewer.handle({"type": "skip", "seconds": -10})
    assert viewer.position() == 50 and not viewer.state()["live"]

    viewer.handle({"type": "speed", "value": 3})
    assert viewer.speed == 2 or viewer.speed == 4

    viewer.handle({"type": "live"})
    assert viewer.position() == 60 and viewer.state()["live"]


def test_paused_viewer_stays_put_while_live_grows():
    clock = FakeClock()
    timeline = make_timeline("live", 30)
    viewer = Viewer(timeline, clock)
    viewer.handle({"type": "pause"})
    clock.now += 5
    timeline.add_frame(35, {})
    assert viewer.position() == 30

    viewer.handle({"type": "play"})
    clock.now += 2
    assert viewer.position() == 32


def test_replaying_into_live_edge_rejoins_live():
    clock = FakeClock()
    timeline = make_timeline("live", 30)
    viewer = Viewer(timeline, clock)
    viewer.handle({"type": "seek", "t": 20})
    viewer.handle({"type": "speed", "value": 8})
    clock.now += 2
    assert viewer.position() == 30
    assert viewer.state()["live"]


def test_replay_viewer_starts_at_zero_and_clamps_seek():
    clock = FakeClock()
    viewer = Viewer(make_timeline("replay", 100), clock)
    assert viewer.position() == 0
    viewer.handle({"type": "seek", "t": 500})
    assert viewer.position() == 100
    viewer.handle({"type": "live"})
    assert not viewer.state()["live"]


def _jwt(claims):
    body = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return f"header.{body}.signature"


def test_extract_token_from_login_session_cookie():
    token = _jwt({"exp": 1})
    cookie = "%7B%22data%22%3A%7B%22subscriptionToken%22%3A%22" + token + "%22%7D%7D"
    assert extract_token(cookie) == token
    assert extract_token(f"  {token}\n") == token
    with pytest.raises(ValueError):
        extract_token("nope")


def test_token_store_reports_expiry(tmp_path):
    store = TokenStore(str(tmp_path / "token"))
    assert store.status()["present"] is False
    status = store.set(_jwt({"exp": int(time.time()) + 3600}))
    assert status["present"] and status["expired"] is False
    store.set(_jwt({"exp": 1}))
    assert store.status()["expired"] is True
    store.clear()
    assert store.get() is None


def test_token_store_reports_whether_the_token_changed(tmp_path):
    store = TokenStore(str(tmp_path / "token"))
    token = _jwt({"exp": int(time.time()) + 3600})
    assert store.set(token)["changed"] is True
    assert store.set(token)["changed"] is False
    assert store.set(_jwt({"exp": 2}))["changed"] is True
