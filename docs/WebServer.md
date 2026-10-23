# Web server (backend)

`server/` is a FastAPI backend for the web version of F1 Race Replay. It serves
three kinds of sessions through one WebSocket stream:

- **Live**: F1's live timing feed during a session. Every message is also
  recorded to `data/recordings/*.jsonl`.
- **Recording**: a recorded live session played back through the same parser.
- **Replay**: a finished race or sprint built by the desktop app's pipeline in
  `src/f1_data.py` (FastF1 archive, no login needed).

Every browser has its own playback cursor, so one viewer can rewind or slow
down while the others keep watching live.

## Running it

```bash
pip install -r server/requirements.txt
ADMIN_PASSWORD=change-me uvicorn server.app:app --host 0.0.0.0 --port 8000
```

Or with Docker, from the repository root:

```bash
docker build -f server/Dockerfile -t f1-tracker-api .
docker run -d -p 8000:8000 -v f1-data:/data -e ADMIN_PASSWORD=change-me f1-tracker-api
```

| Variable | Default | Purpose |
|----------|---------|---------|
| `F1_DATA_DIR` | `data` (`/data` in Docker) | F1 TV token and live recordings |
| `ADMIN_PASSWORD` | unset | Enables `/api/admin/*`. Admin endpoints are off when unset |
| `LIVE_AUTOSTART` | unset | `1` connects to live timing on startup |
| `SAMPLE_HZ` | `4` | Frames per second kept and sent to browsers |

## F1 TV token

Since 2025 the live feed only sends car positions (`Position.z`) and car
telemetry (`CarData.z`) to F1 TV subscribers (Access, Pro or Premium). Timing,
tyres, race control, track status and weather work without a token.

The token is the `subscriptionToken` inside the formula1.com login cookie and
lasts about a week. To get it, either:

1. Log in on formula1.com, open the browser dev tools, and copy the value of
   the `login-session` cookie. Paste the whole value: the server extracts the
   token from it.
2. Or run FastF1's login on your own computer, which opens a browser page and
   prints the token:
   `python -c "from fastf1.internals.f1auth import get_auth_token; print(get_auth_token())"`

Then store it on the server:

```bash
curl -X PUT http://localhost:8000/api/admin/token \
  -H "X-Admin-Password: change-me" -H "Content-Type: application/json" \
  -d '{"token": "<token or cookie value>"}'
```

`GET /api/admin/token` shows whether a token is stored and when it expires.
Restart live timing (`stop` then `start`) after changing the token.

## HTTP API

| Method | Path | Notes |
|--------|------|-------|
| GET | `/api/health` | |
| GET | `/api/status` | Current mode, session, loading state and live errors |
| GET | `/api/meta` | Session, drivers, track outline, race control, stints |
| GET | `/api/schedule/{year}` | Race weekends from FastF1 |
| GET | `/api/recordings` | Recorded live sessions |
| POST | `/api/admin/live/start` / `stop` | Connect to or leave the live feed |
| POST | `/api/admin/replay` | `{"year": 2024, "round": 5, "session_type": "R"}` (`R` or `S`) |
| POST | `/api/admin/recording` | `{"name": "2025-03-16T04-00-00Z.jsonl"}` |
| GET/PUT/DELETE | `/api/admin/token` | F1 TV token |

Admin endpoints need the `X-Admin-Password` header. Switching the session
changes it for every viewer.

## WebSocket `/ws`

The server sends:

```json
{"type": "meta", "meta": {...}, "state": {...}}
{"type": "frame", "state": {...}, "frame": {...}}
```

`meta` is sent on connect and whenever it changes (new drivers, race control
messages, track outline). `frame` has the same shape as the desktop telemetry
stream (see `telemetry.md`) with extra live fields per driver: `gap`,
`interval`, `last_lap`, `best_lap`, `sectors`, `retired`, `rpm`.

`state` is the viewer's playback position:

```json
{"t": 812.5, "duration": 4210.0, "speed": 1, "paused": false, "live": true, "mode": "live"}
```

The browser controls its own playback with:

```json
{"type": "play"}            {"type": "pause"}
{"type": "seek", "t": 600}  {"type": "skip", "seconds": -10}
{"type": "speed", "value": 4}
{"type": "live"}            // jump back to the live edge
```

## Known limits

- The live track outline appears once the first car completes a clean lap.
  Replays use the fastest lap's outline straight away.
- Replays only support races and sprints for now. Qualifying and practice work
  live and from recordings.
- The live parser follows the feed format used by FastF1 and was tested with
  synthetic data. It still needs a check against a real session.
