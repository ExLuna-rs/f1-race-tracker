"""
Sessions anyone can watch again: every session followed live, plus the races
and sprints an admin adds from FastF1's archive.

Each one is stored once as a gzipped file of frame JSON, so opening it again
skips the expensive build. Only the last few opened stay in memory.
"""

import gzip
import json
import os
import re
import threading
from collections import OrderedDict
from datetime import datetime, timezone

from server.timeline import Timeline

SESSION_ID = re.compile(r"^[\w.-]{1,80}$")


def save_timeline(timeline, path):
    """Write the frames and meta of a timeline, replacing any previous file."""
    tmp = path + ".tmp"
    times, frames = timeline.parts()
    with gzip.open(tmp, "wt", encoding="utf-8") as f:
        f.write(json.dumps({"meta": timeline.meta, "min_interval_s": timeline.min_interval_s}) + "\n")
        for t, frame in zip(times, frames):
            f.write(f"{t}\t{frame}\n")
    os.replace(tmp, path)


def load_timeline(path):
    with gzip.open(path, "rt", encoding="utf-8") as f:
        header = json.loads(f.readline())
        times, frames = [], []
        for line in f:
            t, frame = line.rstrip("\n").split("\t", 1)
            times.append(float(t))
            frames.append(frame)
    return Timeline.from_parts("recording", header["min_interval_s"], times, frames, header["meta"])


def summary(session_id, source, timeline):
    """What the library lists for a session, taken from its meta."""
    session = (timeline.meta or {}).get("session") or {}
    return {
        "id": session_id,
        # "live" for sessions recorded live, "archive" for FastF1 replays
        "source": source,
        "year": session.get("year") or _year(session.get("start")),
        "meeting": session.get("meeting", ""),
        "name": session.get("name", ""),
        "type": session.get("type", ""),
        "start": session.get("start", ""),
        "duration": timeline.duration,
        "added": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def _year(start):
    try:
        return int(str(start)[:4])
    except ValueError:
        return None


class Library:
    def __init__(self, folder, keep_in_memory=2):
        self.folder = folder
        os.makedirs(folder, exist_ok=True)
        self.keep_in_memory = keep_in_memory
        self._cache = OrderedDict()
        self._lock = threading.Lock()
        # One lock per session being opened, so two viewers don't load it twice
        self._loading = {}

    def _path(self, session_id, suffix):
        if not SESSION_ID.match(session_id or ""):
            raise ValueError("Invalid session id")
        return os.path.join(self.folder, session_id + suffix)

    def list(self):
        entries = []
        for name in os.listdir(self.folder):
            if not name.endswith(".info.json"):
                continue
            try:
                with open(os.path.join(self.folder, name), encoding="utf-8") as f:
                    entries.append(json.load(f))
            except (OSError, ValueError):
                continue
        return sorted(entries, key=lambda e: (str(e.get("start") or ""), e["id"]), reverse=True)

    def add(self, session_id, source, timeline):
        info = summary(session_id, source, timeline)
        save_timeline(timeline, self._path(session_id, ".frames.gz"))
        info_path = self._path(session_id, ".info.json")
        with open(info_path + ".tmp", "w", encoding="utf-8") as f:
            json.dump(info, f)
        os.replace(info_path + ".tmp", info_path)
        with self._lock:
            self._cache.pop(session_id, None)
        return info

    def get(self, session_id):
        """The session's timeline, loaded from disk unless opened recently."""
        path = self._path(session_id, ".frames.gz")
        with self._lock:
            if session_id in self._cache:
                self._cache.move_to_end(session_id)
                return self._cache[session_id]
            loading = self._loading.setdefault(session_id, threading.Lock())
        with loading:
            with self._lock:
                if session_id in self._cache:
                    return self._cache[session_id]
            if not os.path.exists(path):
                raise KeyError(session_id)
            timeline = load_timeline(path)
            with self._lock:
                self._cache[session_id] = timeline
                while len(self._cache) > self.keep_in_memory:
                    self._cache.popitem(last=False)
                self._loading.pop(session_id, None)
            return timeline

    def delete(self, session_id):
        removed = False
        for suffix in (".frames.gz", ".info.json"):
            path = self._path(session_id, suffix)
            if os.path.exists(path):
                os.remove(path)
                removed = True
        with self._lock:
            self._cache.pop(session_id, None)
        return removed
