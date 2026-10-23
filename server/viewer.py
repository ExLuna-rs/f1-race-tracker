"""
Playback position of one connected browser.

Each viewer has its own cursor over the shared timeline, so a friend can
rewind an overtake while everyone else keeps watching live.
"""

import time

SPEEDS = (0.5, 1, 2, 4, 8, 16, 32, 64)
# How close to the newest frame still counts as watching live
LIVE_EDGE_S = 2.0


class Viewer:
    def __init__(self, timeline, clock=time.monotonic):
        self.clock = clock
        self.timeline = timeline
        self.speed = 1.0
        self.paused = False
        self.follow_live = timeline.mode == "live"
        self._t = timeline.duration if self.follow_live else 0.0
        self._last_tick = clock()

    def reset(self, timeline):
        self.__init__(timeline, self.clock)

    def position(self):
        """Advance the cursor to now and return the session time to show."""
        now = self.clock()
        elapsed = now - self._last_tick
        self._last_tick = now
        head = self.timeline.duration

        if self.follow_live:
            self._t = head
        elif not self.paused:
            self._t = min(self._t + elapsed * self.speed, head)
            # Catching up with the live edge switches back to following it
            if self.timeline.mode == "live" and head - self._t < LIVE_EDGE_S:
                self.follow_live = True
                self._t = head
        return self._t

    def handle(self, message):
        """Apply a control message from the browser."""
        kind = message.get("type")
        self.position()
        if kind == "pause":
            self.paused = True
            self.follow_live = False
        elif kind == "play":
            self.paused = False
        elif kind == "seek":
            t = float(message.get("t", 0))
            self._t = min(max(t, 0.0), self.timeline.duration)
            self.follow_live = False
        elif kind == "skip":
            t = self._t + float(message.get("seconds", 0))
            self._t = min(max(t, 0.0), self.timeline.duration)
            self.follow_live = False
        elif kind == "speed":
            value = float(message.get("value", 1))
            self.speed = min(SPEEDS, key=lambda s: abs(s - value))
        elif kind == "live":
            if self.timeline.mode == "live":
                self.follow_live = True
                self.paused = False
                self.speed = 1.0

    def state(self):
        return {
            "t": round(self._t, 3),
            "duration": round(self.timeline.duration, 3),
            "speed": self.speed,
            "paused": self.paused,
            "live": self.follow_live,
            "mode": self.timeline.mode,
        }
