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

    @classmethod
    def from_parts(cls, mode, min_interval_s, times, frames, meta):
        """Rebuild a timeline from the frame times, frame JSON and meta of another one."""
        timeline = cls(mode, min_interval_s)
        timeline._times, timeline._frames = times, frames
        timeline.set_meta(meta)
        return timeline

    def parts(self):
        """Copies of the frame times and frame JSON, for saving."""
        with self._lock:
            return list(self._times), list(self._frames)

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

    def frames_between(self, t0, t1, limit=64):
        """JSON of the frames after t0 and before t1, the most recent `limit` of them."""
        with self._lock:
            start = bisect.bisect_right(self._times, t0)
            end = bisect.bisect_left(self._times, t1)
            return self._frames[max(start, end - limit):end]

    def frame_at(self, t):
        """Return (frame_time, frame_json) for the latest frame at or before t."""
        with self._lock:
            if not self._times:
                return None, None
            idx = bisect.bisect_right(self._times, t) - 1
            idx = max(idx, 0)
            return self._times[idx], self._frames[idx]
