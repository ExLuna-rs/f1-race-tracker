"""
Circuit outline, rotation and corner numbers for the live track map.

The live feed has no track outline, so without this the map stays empty until
a car completes a clean lap. FastF1 gets the same data from this API for
`Session.get_circuit_info()`, in the same coordinates as the Position feed.
"""

import json
import logging
import os

import requests

logger = logging.getLogger(__name__)

CIRCUIT_URL = "https://api.multiviewer.app/api/v1/circuits/{key}/{year}"


def _parse(data):
    xs, ys = data.get("x") or [], data.get("y") or []
    corners = []
    for corner in data.get("corners") or []:
        position = corner.get("trackPosition") or {}
        if "x" in position and "y" in position:
            corners.append({
                "number": corner.get("number"),
                "letter": corner.get("letter") or "",
                "x": float(position["x"]),
                "y": float(position["y"]),
                "angle": float(corner.get("angle") or 0),
            })
    return {
        "track": [[float(x), float(y)] for x, y in zip(xs, ys)] or None,
        "rotation": float(data.get("rotation") or 0),
        "corners": corners,
    }


class CircuitProvider:
    """Fetches circuit info once per circuit and year, cached on disk."""

    def __init__(self, cache_dir):
        self.cache_dir = cache_dir

    def __call__(self, key, year):
        path = os.path.join(self.cache_dir, f"{int(key)}_{int(year)}.json")
        try:
            with open(path, encoding="utf-8") as f:
                return _parse(json.load(f))
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        try:
            r = requests.get(CIRCUIT_URL.format(key=int(key), year=int(year)),
                             headers={"User-Agent": "f1-race-tracker"}, timeout=10)
            r.raise_for_status()
            data = r.json()
        except (requests.RequestException, ValueError) as e:
            logger.warning("Could not fetch circuit %s/%s: %s", key, year, e)
            return None
        os.makedirs(self.cache_dir, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        return _parse(data)
