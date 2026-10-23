"""
A growing list of frames shared by every viewer.

Frames are serialised to JSON once when added, so sending one frame to many
viewers costs nothing extra and a three hour session stays small in memory.
"""

import bisect
import json
import threading


class Timeline:
    def __init__(self, mode, min_interval_s=0.25):
        self.mode = mode  # "live", "replay" or "recording"
        self.min_interval_s = min_interval_s
        self.meta = {}
        self.meta_version = 0
        self.finished = mode != "live"
        self._times = []
        self._frames = []
        self._lock = threading.Lock()

    def add_frame(self, t, frame):
        """Store a frame, dropping it if it is too close to the previous one."""
        with self._lock:
            if self._times and t - self._times[-1] < self.min_interval_s:
                return False
            self._times.append(t)
            self._frames.append(json.dumps(frame, separators=(",", ":")))
            return True

    def set_meta(self, meta):
        with self._lock:
            self.meta = meta
            self.meta_version += 1

    @property
    def duration(self):
        with self._lock:
            return self._times[-1] if self._times else 0.0

    def __len__(self):
        return len(self._times)

    def frame_at(self, t):
        """Return (frame_time, frame_json) for the latest frame at or before t."""
        with self._lock:
            if not self._times:
                return None, None
            idx = bisect.bisect_right(self._times, t) - 1
            idx = max(idx, 0)
            return self._times[idx], self._frames[idx]
