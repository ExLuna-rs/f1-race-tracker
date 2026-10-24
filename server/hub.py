"""
Owns the session everyone is watching: live, a recorded feed, or a replay.
"""

import logging
import os
import re
import threading
from datetime import datetime, timezone

from server.circuit import CircuitProvider
from server.live.client import LiveClient, Recorder, read_recording
from server.live.state import LiveState
from server.timeline import Timeline

logger = logging.getLogger(__name__)

RECORDING_NAME = re.compile(r"^[\w.-]+\.jsonl$")


class Hub:
    def __init__(self, data_dir, token_store, sample_hz=4):
        self.data_dir = data_dir
        self.recordings_dir = os.path.join(data_dir, "recordings")
        os.makedirs(self.recordings_dir, exist_ok=True)
        self.token_store = token_store
        self.sample_hz = sample_hz
        self.circuits = CircuitProvider(os.path.join(data_dir, "circuits"))

        self.timeline = Timeline("replay")
        self.timeline.set_meta({})
        self.client = None
        self.loading = None
        self.error = None
        self._lock = threading.Lock()

    # Live ---------------------------------------------------------------

    def start_live(self):
        with self._lock:
            if self.client is not None:
                return
            timeline = Timeline("live", min_interval_s=1 / self.sample_hz)
            state = LiveState(on_frame=timeline.add_frame, on_meta=timeline.set_meta,
                              circuit_provider=self.circuits)
            name = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ") + ".jsonl"
            recorder = Recorder(os.path.join(self.recordings_dir, name))
            self.client = LiveClient(state.apply, self.token_store.get, recorder)
            self.timeline = timeline
            self.error = None
            self.client.start()
            logger.info("Live timing started, recording to %s", name)

    def reconnect_live(self):
        """Reconnect with the current token, e.g. after it was renewed."""
        with self._lock:
            if self.client is not None:
                self.client.reconnect()

    def stop_live(self):
        with self._lock:
            if self.client is None:
                return
            self.client.stop()
            self.client = None
            # Keep the session watchable, it just stops growing
            self.timeline.mode = "recording"
            self.timeline.finished = True

    # Recordings and replays --------------------------------------------

    def list_recordings(self):
        names = [n for n in os.listdir(self.recordings_dir) if RECORDING_NAME.match(n)]
        return sorted(names, reverse=True)

    def load_recording(self, name):
        if not RECORDING_NAME.match(name or ""):
            raise ValueError("Invalid recording name")
        path = os.path.join(self.recordings_dir, name)
        if not os.path.exists(path):
            raise FileNotFoundError(name)
        self._load_in_background(f"recording {name}", lambda: timeline_from_recording(path, self.sample_hz, self.circuits))

    def load_replay(self, year, round_number, session_type):
        from server.replay import build_replay_timeline

        self._load_in_background(
            f"{year} round {round_number} {session_type}",
            lambda: build_replay_timeline(year, round_number, session_type, self.sample_hz),
        )

    def _load_in_background(self, label, build):
        with self._lock:
            if self.loading:
                raise RuntimeError(f"Already loading {self.loading}")
            self.loading = label
            self.error = None

        def run():
            try:
                timeline = build()
                self.stop_live()
                with self._lock:
                    self.timeline = timeline
            except Exception as e:
                logger.exception("Failed to load %s", label)
                self.error = f"{label}: {e}"
            finally:
                self.loading = None

        threading.Thread(target=run, daemon=True).start()

    def status(self):
        return {
            "mode": self.timeline.mode,
            "session": (self.timeline.meta or {}).get("session"),
            "duration": self.timeline.duration,
            "frames": len(self.timeline),
            "live_running": self.client is not None,
            "live_connected": bool(self.client and self.client.connected),
            "live_error": self.client.last_error if self.client else None,
            "loading": self.loading,
            "error": self.error,
            # Expiry only, never the token itself, so the site can warn
            "token": self.token_store.status(),
        }


def timeline_from_recording(path, sample_hz=4, circuit_provider=None):
    """Rebuild a timeline by running a recorded feed through the live parser."""
    timeline = Timeline("recording", min_interval_s=1 / sample_hz)
    state = LiveState(on_frame=timeline.add_frame, on_meta=timeline.set_meta,
                      circuit_provider=circuit_provider)
    for topic, data, utc in read_recording(path):
        try:
            state.apply(topic, data, utc)
        except Exception:
            logger.exception("Skipping bad %s message in %s", topic, path)
    timeline.set_meta(state.build_meta())
    return timeline
