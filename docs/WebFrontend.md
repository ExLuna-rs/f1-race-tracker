# Web frontend

`web/` is the Next.js frontend for the web version. It talks to the FastAPI
backend in `server/` (see [WebServer.md](WebServer.md)): a WebSocket at `/ws`
for the session stream and `/api/*` for everything else.

Everything is drawn from the stream, so live sessions, recordings and replays
all use the same screen.

## Pages

| Path | What it does |
|------|--------------|
| `/` | The tracker: track map, timing tower, playback controls, telemetry, tyre strategy and race control |
| `/admin` | Start or stop live timing, store the F1 TV token, load a replay or a recording |

The admin password is sent as the `X-Admin-Password` header and kept in that
browser's local storage only. The tracker page needs no password.

## What the screen shows

- **Track map**: the circuit outline with corner numbers, every car as a dot in
  its team colour, cars in the pit lane dimmed, and the safety car when the
  replay places one. Clicking a car selects it. Positions are interpolated
  between frames, so cars move smoothly rather than jumping four times a second.
- **Timing tower**: position, driver, gap, lap time and tyre with its age.
  During a race the gap header switches between gap to the leader and interval
  to the car ahead. Replays have no timing gaps in the feed, so they are
  estimated from the distance between the cars.
- **Playback**: play, pause, skip, a speed from ×0.5 to ×64 and a scrubber
  marked with the yellow and red flag periods. Space toggles play, the arrow
  keys skip 5 seconds (30 with shift). During a live session the DIRECT button
  jumps back to the live edge; rewinding only moves your own cursor, so other
  viewers keep watching live.
- **Telemetry**: speed, gear, rpm, DRS, throttle and brake for the selected
  driver, with the last 90 seconds as a chart, plus sector times.
- **Tyre strategy**: a stint bar per driver, only up to the lap being watched.
- **Race control**: the messages announced up to that point, newest first.
- **Token warning**: a banner when the F1 TV token expires within two days,
  has expired, or is missing while live timing runs.

Qualifying and practice sessions show best lap times instead of last lap times
and drop the lap counter.

## Running it

The backend must be running first.

```bash
cd web
npm install
npm run dev     # http://localhost:3000, /api and /ws go to localhost:8000
```

`API_URL` changes where `/api` and `/ws` are forwarded. Next bakes rewrites in
at build time, so for a production build pass it as a build argument (the
Docker image does). `NEXT_PUBLIC_WS_URL` overrides the WebSocket URL in the
browser, which is only needed if the frontend and backend are on separate
hosts.

## Deploying

`docker-compose.yml` at the repository root builds both services and publishes
them on localhost only, for Caddy to pick up:

```bash
echo "ADMIN_PASSWORD=choose-something" > .env
docker compose up -d --build
```

| Variable | Purpose |
|----------|---------|
| `ADMIN_PASSWORD` | Required, enables `/api/admin/*` |
| `LIVE_AUTOSTART` | `1` connects to live timing when the backend starts |

`deploy/Caddyfile.example` is the matching route: `/api/*` and `/ws` to the
backend, everything else to the frontend. Caddy needs no TLS config here
because the Cloudflare Tunnel terminates it; the tunnel and any Access policy
are set up outside this repository.
