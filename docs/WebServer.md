# Web server (backend)

`server/` is a FastAPI backend for the web version of F1 Race Replay. Viewers
follow the live session by default, or pick one from the library:

- **Live**: F1's live timing feed stays connected (`LIVE_AUTOSTART=1`). Each
  session it carries (practice, qualifying, race) gets its own timeline and
  raw recording in `data/recordings/<key>-<meeting>-<session>.jsonl`. After a
  restart mid-session the recording is read back, so nothing is lost.
- **Library** (`data/library/`): every live session goes in once it ends, plus
  the races and sprints an admin adds from FastF1's archive, built by the
  desktop app's pipeline in `src/f1_data.py`. Each is stored once as gzipped
  frame JSON; the last two opened stay in memory.

Every browser has its own playback cursor and picks its own session, so one
viewer can rewatch a race while the others keep watching live.

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
| `LIVE_AUTOSTART` | `1` in docker-compose | `1` connects to live timing on startup |
| `SAMPLE_HZ` | `4` | Frames per second kept and sent to browsers |

## F1 TV token

Since 2025 the live feed only sends car positions (`Position.z`) and car
telemetry (`CarData.z`) to F1 TV subscribers (Access, Pro or Premium). Timing,
tyres, race control, track status and weather work without a token.

The token is the `subscriptionToken` inside the formula1.com login cookie and
lasts about a week.

The easiest way to keep it fresh is the browser extension in
[`extension/`](../extension/README.md): it sends the cookie to the server every
time it changes. Otherwise, get it by hand, either:

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

`GET /api/admin/token` shows whether a token is stored and when it expires;
`/api/status` includes the same (never the token itself) so the site can warn
before it expires. When a different token is stored while live timing runs,
the server reconnects with it straight away.

## HTTP API

| Method | Path | Notes |
|--------|------|-------|
| GET | `/api/health` | |
| GET | `/api/status` | Live session, whether it is on (`live_active`), admin build state, live errors |
| GET | `/api/library` | Sessions to watch again, newest first |
| GET | `/api/next` | Next session on the calendar, for the page shown while nothing is live |
| GET | `/api/meta` | Session, drivers, track outline, race control, stints |
| GET | `/api/schedule/{year}` | Race weekends from FastF1 |
| GET | `/api/recordings` | Recorded live sessions |
| POST | `/api/admin/live/start` / `stop` | Connect to or leave the live feed |
| POST | `/api/admin/replay` | Add `{"year": 2024, "round": 5, "session_type": "R"}` (`R` or `S`) to the library |
| POST | `/api/admin/recording` | Add a raw recording `{"name": "2025-03-16T04-00-00Z.jsonl"}` to the library |
| DELETE | `/api/admin/library/{id}` | Remove a session from the library |
| GET/PUT/DELETE | `/api/admin/token` | F1 TV token |

Admin endpoints need the `X-Admin-Password` header. Switching the session
changes it for every viewer.

## WebSocket `/ws`

`/ws` follows the live session, switching by itself when the next one starts.
`/ws?session=<id>` plays a library session; an unknown id gets
`{"type": "error", "message": ...}` and the socket closes with code 4404.

The server sends:

```json
{"type": "meta", "meta": {...}, "state": {...}}
{"type": "frame", "state": {...}, "frame": {...}, "between": [{...}]}
```

`between` holds the frames skipped since the previous message (at 4x a message
covers four of them), so the map can draw every one of them.

`meta` is sent on connect and whenever it changes (new drivers, race control
messages, track outline). `frame` has the same shape as the desktop telemetry
stream (see `telemetry.md`) with extra fields per driver: `gap`, `interval`,
`last_lap`, `best_lap`, `retired`, and live only `sectors`, `rpm`. Replays
work out their gaps from race distance, since the archive has none.

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

## Importing a FastF1 live timing file

FastF1 can record the feed itself (`python -m fastf1.livetiming save out.txt`).
Those files use a different line format, so convert them before loading:

```bash
python -m server.import_recording out.txt data/recordings/2025-bahrain-fp3.jsonl
```

## Circuit outline

The live feed sends no track outline, so the server fetches the circuit from
`api.multiviewer.app` — the same source FastF1 uses for
`Session.get_circuit_info()`, in the same coordinates as `Position.z`. The
result is cached in `$F1_DATA_DIR/circuits`. If the fetch fails the map falls
back to the first clean lap any car completes.

## Known limits

- Archive replays only support races and sprints. Qualifying and practice get
  into the library by being followed live.
- The live parser was checked against the 2021 Bahrain FP3 feed from FastF1's
  test data. A live session with an F1 TV token has still not been tried.
