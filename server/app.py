"""
FastAPI server for the web version of F1 Race Replay.

Run with:  uvicorn server.app:app --host 0.0.0.0 --port 8000

Environment:
  F1_DATA_DIR      where the token and live recordings are stored (default ./data)
  ADMIN_PASSWORD   enables the /api/admin endpoints (disabled when unset)
  LIVE_AUTOSTART   "1" to connect to live timing on startup
  SAMPLE_HZ        frames per second kept in timelines (default 4)
"""

import asyncio
import hmac
import json
import os

from fastapi import Depends, FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from server.hub import Hub
from server.replay import REPLAY_SESSION_TYPES
from server.token_store import TokenStore
from server.viewer import Viewer

DATA_DIR = os.environ.get("F1_DATA_DIR", "data")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
SAMPLE_HZ = float(os.environ.get("SAMPLE_HZ", "4"))
SEND_INTERVAL_S = 1 / SAMPLE_HZ

token_store = TokenStore(os.path.join(DATA_DIR, "f1tv_token"))
hub = Hub(DATA_DIR, token_store, sample_hz=SAMPLE_HZ)

app = FastAPI(title="F1 Race Tracker")


@app.on_event("startup")
def autostart_live():
    if os.environ.get("LIVE_AUTOSTART") == "1":
        hub.start_live()


def require_admin(x_admin_password: str = Header(default="")):
    if not ADMIN_PASSWORD:
        raise HTTPException(403, "Set ADMIN_PASSWORD to enable admin endpoints")
    if not hmac.compare_digest(x_admin_password, ADMIN_PASSWORD):
        raise HTTPException(401, "Wrong admin password")


# Public ------------------------------------------------------------------

@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/status")
def status():
    return hub.status()


@app.get("/api/meta")
def meta():
    return hub.timeline.meta


@app.get("/api/schedule/{year}")
def schedule(year: int):
    from src.f1_data import get_race_weekends_by_year

    return get_race_weekends_by_year(year)


@app.get("/api/recordings")
def recordings():
    return hub.list_recordings()


# Admin -------------------------------------------------------------------

class TokenBody(BaseModel):
    token: str


class ReplayBody(BaseModel):
    year: int
    round: int
    session_type: str = "R"


class RecordingBody(BaseModel):
    name: str


@app.get("/api/admin/token", dependencies=[Depends(require_admin)])
def token_status():
    return token_store.status()


@app.put("/api/admin/token", dependencies=[Depends(require_admin)])
def set_token(body: TokenBody):
    try:
        return token_store.set(body.token)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.delete("/api/admin/token", dependencies=[Depends(require_admin)])
def clear_token():
    token_store.clear()
    return token_store.status()


@app.post("/api/admin/live/start", dependencies=[Depends(require_admin)])
def live_start():
    hub.start_live()
    return hub.status()


@app.post("/api/admin/live/stop", dependencies=[Depends(require_admin)])
def live_stop():
    hub.stop_live()
    return hub.status()


@app.post("/api/admin/replay", dependencies=[Depends(require_admin)])
def load_replay(body: ReplayBody):
    if body.session_type not in REPLAY_SESSION_TYPES:
        raise HTTPException(400, f"session_type must be one of {REPLAY_SESSION_TYPES}")
    try:
        hub.load_replay(body.year, body.round, body.session_type)
    except RuntimeError as e:
        raise HTTPException(409, str(e))
    return hub.status()


@app.post("/api/admin/recording", dependencies=[Depends(require_admin)])
def load_recording(body: RecordingBody):
    try:
        hub.load_recording(body.name)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except FileNotFoundError:
        raise HTTPException(404, "Recording not found")
    except RuntimeError as e:
        raise HTTPException(409, str(e))
    return hub.status()


# Viewer stream -----------------------------------------------------------

@app.websocket("/ws")
async def stream(ws: WebSocket):
    """Send frames at the viewer's own playback position.

    Server -> browser:
      {"type": "meta", "meta": {...}, "state": {...}}  on connect and on changes
      {"type": "frame", "state": {...}, "frame": {...}}
    Browser -> server:
      {"type": "play" | "pause" | "live"}
      {"type": "seek", "t": seconds} / {"type": "skip", "seconds": -10}
      {"type": "speed", "value": 4}
    """
    await ws.accept()
    viewer = Viewer(hub.timeline)
    sent_meta = None
    sent_frame_t = None
    sent_state = None

    async def receive_controls():
        while True:
            try:
                message = json.loads(await ws.receive_text())
            except (json.JSONDecodeError, TypeError):
                continue
            if isinstance(message, dict):
                viewer.handle(message)

    receiver = asyncio.create_task(receive_controls())
    try:
        while not receiver.done():
            if viewer.timeline is not hub.timeline:
                viewer.reset(hub.timeline)
                sent_meta = sent_frame_t = None

            timeline = viewer.timeline
            t = viewer.position()
            state = viewer.state()

            meta_key = (id(timeline), timeline.meta_version)
            if meta_key != sent_meta:
                await ws.send_text(json.dumps({"type": "meta", "meta": timeline.meta, "state": state}))
                sent_meta = meta_key

            frame_t, frame_json = timeline.frame_at(t)
            if frame_json is not None and (frame_t != sent_frame_t or state != sent_state):
                await ws.send_text(
                    '{"type":"frame","state":' + json.dumps(state) + ',"frame":' + frame_json + "}"
                )
                sent_frame_t, sent_state = frame_t, state

            await asyncio.sleep(SEND_INTERVAL_S)
    except WebSocketDisconnect:
        pass
    finally:
        receiver.cancel()
