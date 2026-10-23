"""
Connects to F1's live timing SignalR feed and records every message.

Car positions and car telemetry are only sent to F1 TV subscribers, so the
client sends the subscription token stored through the admin endpoint. Without
a token the feed still gives timing, tyres, race control and weather.
"""

import json
import logging
import threading
import time
from datetime import datetime, timezone

import requests
from signalrcore.hub_connection_builder import HubConnectionBuilder
from signalrcore.messages.completion_message import CompletionMessage

logger = logging.getLogger(__name__)

CONNECTION_URL = "wss://livetiming.formula1.com/signalrcore"
NEGOTIATE_URL = "https://livetiming.formula1.com/signalrcore/negotiate"

TOPICS = [
    "Heartbeat", "DriverList", "ExtrapolatedClock", "RaceControlMessages",
    "SessionInfo", "SessionStatus", "TimingAppData", "TimingStats",
    "TrackStatus", "WeatherData", "Position.z", "CarData.z", "SessionData",
    "TimingData", "TopThree", "LapCount",
]

# Reconnect when the feed goes quiet for this long
SILENCE_TIMEOUT_S = 60


def _now_utc():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class Recorder:
    """Appends feed messages to a JSON Lines file so sessions can be replayed."""

    def __init__(self, path):
        self.path = path
        self._lock = threading.Lock()
        self._file = open(path, "a", encoding="utf-8")

    def write(self, topic, data, utc):
        line = json.dumps({"topic": topic, "data": data, "utc": utc})
        with self._lock:
            self._file.write(line + "\n")
            self._file.flush()

    def close(self):
        with self._lock:
            self._file.close()


def read_recording(path):
    """Yield (topic, data, utc) tuples from a recording made by Recorder."""
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            yield row["topic"], row["data"], row.get("utc")


class LiveClient:
    """Runs the SignalR connection in a background thread and reconnects."""

    def __init__(self, on_message, token_provider=None, recorder=None):
        self.on_message = on_message
        self.token_provider = token_provider or (lambda: None)
        self.recorder = recorder
        self.connected = False
        self.last_error = None
        self._connection = None
        self._stop = threading.Event()
        self._thread = None
        self._t_last_message = time.time()

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._disconnect()
        if self.recorder:
            self.recorder.close()

    def _handle(self, topic, data, utc):
        self._t_last_message = time.time()
        if self.recorder:
            self.recorder.write(topic, data, utc)
        try:
            self.on_message(topic, data, utc)
        except Exception:
            logger.exception("Failed to process %s message", topic)

    def _on_feed(self, args):
        # Feed messages arrive as [topic, data, timestamp]
        if isinstance(args, list) and len(args) >= 2:
            utc = args[2] if len(args) > 2 else _now_utc()
            self._handle(args[0], args[1], utc)

    def _on_subscribed(self, msg):
        if isinstance(msg, CompletionMessage) and isinstance(msg.result, dict):
            utc = _now_utc()
            for topic, data in msg.result.items():
                self._handle(topic, data, utc)

    def _connect(self):
        headers = {}
        # The load balancer needs its stickiness cookie before the websocket
        r = requests.options(NEGOTIATE_URL, timeout=15)
        if "AWSALBCORS" in r.cookies:
            headers["Cookie"] = f"AWSALBCORS={r.cookies['AWSALBCORS']}"

        token = self.token_provider()
        options = {"verify_ssl": True, "headers": headers}
        if token:
            options["access_token_factory"] = lambda: token
        else:
            logger.warning("No F1 TV token set: positions and car data will be missing")

        connection = HubConnectionBuilder().with_url(CONNECTION_URL, options=options).build()
        opened = threading.Event()
        connection.on_open(opened.set)
        connection.on_close(lambda: setattr(self, "connected", False))
        connection.on("feed", self._on_feed)
        connection.start()
        if not opened.wait(20):
            connection.stop()
            raise ConnectionError("Timed out connecting to live timing")

        self._connection = connection
        self.connected = True
        self._t_last_message = time.time()
        connection.send("Subscribe", [TOPICS], on_invocation=self._on_subscribed)

    def _disconnect(self):
        if self._connection is not None:
            try:
                self._connection.stop()
            except Exception:
                pass
        self._connection = None
        self.connected = False

    def _run(self):
        backoff = 5
        while not self._stop.is_set():
            try:
                self._connect()
                self.last_error = None
                backoff = 5
                while not self._stop.is_set() and self.connected:
                    if time.time() - self._t_last_message > SILENCE_TIMEOUT_S:
                        logger.warning("Live timing went quiet, reconnecting")
                        break
                    self._stop.wait(1)
            except Exception as e:
                self.last_error = str(e)
                logger.warning("Live timing connection failed: %s", e)
            self._disconnect()
            self._stop.wait(backoff)
            backoff = min(backoff * 2, 60)
