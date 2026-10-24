"""
Owns the live session and the library of sessions to watch again.

Live timing stays connected. Each session it carries (FP1, qualifying, the
race...) gets its own timeline and recording, and goes into the library once
it ends, so everything followed live can be watched again.
"""

import logging
import os
import re
import threading
import time

from server.circuit import CircuitProvider
from server.library import Library
from server.live.client import LiveClient, Recorder, read_recording
from server.live.feed import topic_name
from server.live.state import LiveState
from server.timeline import Timeline

logger = logging.getLogger(__name__)

RECORDING_NAME = re.compile(r"^[\w.-]+\.jsonl$")
# Session statuses after which the session is over and goes into the library
ENDED = ("Finalised", "Ends")
# A session counts as live while car positions keep coming
POSITIONS_FRESH_S = 120
# Shorter sessions (a connection made after the session ended) aren't kept
MIN_LIBRARY_DURATION_S = 120
# Messages kept while waiting for the session they belong to
MAX_PENDING = 2000


def _slug(text):
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")


class LiveSession:
    """One session followed live: its parser, timeline and recording."""

    def __init__(self, key, info, recordings_dir, sample_hz, circuits):
        self.key = key
        meeting = (info.get("Meeting") or {}).get("Name", "")
        name = f"{key}-{_slug(meeting)}-{_slug(info.get('Name', ''))}.jsonl"
        self.recording = os.path.join(recordings_dir, name)
        self.timeline = Timeline("live", min_interval_s=1 / sample_hz)
        self.state = LiveState(on_frame=self.timeline.add_frame, on_meta=self.timeline.set_meta,
                               circuit_provider=circuits)
        self.last_position = None
        self.had_positions = False
        self.archived_frames = 0

        # After a restart mid-session, pick up from what was already recorded
        if os.path.exists(self.recording):
            for topic, data, utc in read_recording(self.recording):
                self._apply(topic, data, utc)
            self.last_position = None
        self.recorder = Recorder(self.recording)

    def _apply(self, topic, data, utc):
        if topic_name(topic) == "Position":
            self.last_position = time.monotonic()
            self.had_positions = True
        try:
            self.state.apply(topic, data, utc)
        except Exception:
            logger.exception("Failed to process %s message", topic)

    def apply(self, topic, data, utc):
        self.recorder.write(topic, data, utc)
        self._apply(topic, data, utc)

    @property
    def status(self):
        return self.state._session_status()

    @property
    def active(self):
        fresh = self.last_position is not None and time.monotonic() - self.last_position < POSITIONS_FRESH_S
        return fresh or self.status == "Started"

    @property
    def library_id(self):
        return f"live-{self.key}"


class Hub:
    def __init__(self, data_dir, token_store, sample_hz=4):
        self.data_dir = data_dir
        self.recordings_dir = os.path.join(data_dir, "recordings")
        os.makedirs(self.recordings_dir, exist_ok=True)
        self.token_store = token_store
        self.sample_hz = sample_hz
        self.circuits = CircuitProvider(os.path.join(data_dir, "circuits"))
        self.library = Library(os.path.join(data_dir, "library"))

        self.live = None
        self._idle = Timeline("live")
        self._idle.set_meta({})
        self._pending = []
        self.client = None
        self.loading = None
        self.error = None
        self._lock = threading.RLock()

    # Live ---------------------------------------------------------------

    @property
    def live_timeline(self):
        """What viewers following live watch: the current session, or nothing yet."""
        live = self.live
        return live.timeline if live else self._idle

    def start_live(self):
        with self._lock:
            if self.client is not None:
                return
            self.client = LiveClient(self.on_live_message, self.token_store.get)
            self.client.start()
            logger.info("Live timing started")

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
            self._finish_live()

    def on_live_message(self, topic, data, utc):
        name = topic_name(topic)
        with self._lock:
            if name == "SessionInfo" and isinstance(data, dict):
                key = str(data.get("Key") or "")
                if key and (self.live is None or key != self.live.key):
                    self._finish_live()
                    self.live = LiveSession(key, data, self.recordings_dir, self.sample_hz, self.circuits)
                    logger.info("Following live session %s (%s)", key, self.live.recording)
                    pending, self._pending = self._pending, []
                    for message in pending:
                        self.live.apply(*message)
            if self.live is None:
                if len(self._pending) < MAX_PENDING:
                    self._pending.append((topic, data, utc))
                return
            self.live.apply(topic, data, utc)
            if name == "SessionStatus" and self.live.status in ENDED:
                self._archive(self.live)

    def _finish_live(self):
        live, self.live = self.live, None
        if live is None:
            return
        live.recorder.close()
        live.timeline.finished = True
        self._archive(live)

    def _archive(self, live):
        """Put a live session in the library, once it has anything worth watching."""
        timeline = live.timeline
        frames = len(timeline)
        if frames == live.archived_frames or timeline.duration < MIN_LIBRARY_DURATION_S:
            return
        if not live.had_positions:
            # Timing only, no car on the map: nothing to watch again
            return
        try:
            self.library.add(live.library_id, "live", timeline)
            live.archived_frames = frames
            logger.info("Live session %s saved to the library", live.key)
        except Exception:
            logger.exception("Could not save live session %s to the library", live.key)

    # Library ------------------------------------------------------------

    def list_recordings(self):
        names = [n for n in os.listdir(self.recordings_dir) if RECORDING_NAME.match(n)]
        return sorted(names, reverse=True)

    def import_recording(self, name):
        """Add a recording made elsewhere (or before the library existed) to the library."""
        if not RECORDING_NAME.match(name or ""):
            raise ValueError("Invalid recording name")
        path = os.path.join(self.recordings_dir, name)
        if not os.path.exists(path):
            raise FileNotFoundError(name)
        session_id = "rec-" + name[: -len(".jsonl")]
        self._build_in_background(
            f"l'enregistrement {name}",
            lambda: self.library.add(
                session_id, "live", timeline_from_recording(path, self.sample_hz, self.circuits)
            ),
        )

    def add_replay(self, year, round_number, session_type):
        """Build a race or sprint from FastF1's archive into the library."""
        from server.replay import build_replay_timeline_in_subprocess

        session_id = f"{int(year)}-r{int(round_number):02d}-{session_type.lower()}"
        self._build_in_background(
            f"{year} manche {round_number} {session_type}",
            lambda: self.library.add(
                session_id, "archive",
                build_replay_timeline_in_subprocess(
                    year, round_number, session_type, self.sample_hz, token=self.token_store.get()
                ),
            ),
        )

    def _build_in_background(self, label, build):
        with self._lock:
            if self.loading:
                raise RuntimeError(f"Already loading {self.loading}")
            self.loading = label
            self.error = None

        def run():
            try:
                build()
            except Exception as e:
                logger.exception("Failed to build %s", label)
                self.error = f"{label}: {e}"
            finally:
                self.loading = None

        threading.Thread(target=run, daemon=True).start()

    def status(self):
        timeline = self.live_timeline
        live = self.live
        return {
            "mode": timeline.mode,
            "session": (timeline.meta or {}).get("session"),
            "duration": timeline.duration,
            "frames": len(timeline),
            "live_running": self.client is not None,
            "live_connected": bool(self.client and self.client.connected),
            "live_error": self.client.last_error if self.client else None,
            # A session is on and worth showing, not just the last one's leftovers
            "live_active": bool(live and live.active),
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
