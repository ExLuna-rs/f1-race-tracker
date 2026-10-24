"""
Helpers for the raw F1 live timing feed.

The feed sends a full snapshot of every topic when we subscribe, then partial
updates that must be deep-merged into that snapshot. Lists are often updated
with dicts keyed by index (e.g. {"Stints": {"1": {...}}}), and topics ending
in ".z" are base64 encoded, raw-deflated JSON.
"""

import base64
import json
import zlib


def decode_z(payload):
    """Decode a compressed ".z" topic payload into a Python object."""
    if not isinstance(payload, str):
        return payload
    raw = zlib.decompress(base64.b64decode(payload), -zlib.MAX_WBITS)
    return json.loads(raw)


def encode_z(obj):
    """Inverse of decode_z, used by tests and fixtures."""
    compressor = zlib.compressobj(wbits=-zlib.MAX_WBITS)
    raw = compressor.compress(json.dumps(obj).encode()) + compressor.flush()
    return base64.b64encode(raw).decode()


def deep_merge(target, update):
    """Merge a partial feed update into the current topic state, in place.

    Returns the merged value, which callers must store back because a scalar
    or a type change replaces the target entirely.
    """
    if isinstance(update, dict):
        if isinstance(target, list):
            for key, value in update.items():
                try:
                    idx = int(key)
                except (TypeError, ValueError):
                    continue
                if idx < len(target):
                    target[idx] = deep_merge(target[idx], value)
                else:
                    # Pad when the feed skips indices, which happens rarely
                    target.extend([None] * (idx - len(target)))
                    target.append(deep_merge(None, value))
            return target
        if not isinstance(target, dict):
            target = {}
        for key, value in update.items():
            if key == "_deleted":
                for deleted in value or []:
                    target.pop(str(deleted), None)
                continue
            target[key] = deep_merge(target.get(key), value)
        return target
    if isinstance(update, list):
        return [deep_merge(None, value) for value in update]
    return update


def topic_name(topic):
    """Strip the ".z" suffix so compressed topics share a name with their data."""
    return topic[:-2] if topic.endswith(".z") else topic


def as_list(value):
    """Return a feed list, also when it only ever arrived as index-keyed updates.

    Without the subscribe snapshot (for example a recording started mid
    session) lists such as Stints or Sectors are built from {"0": ...} updates
    and end up as dicts.
    """
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        items = []
        for key, item in value.items():
            try:
                items.append((int(key), item))
            except (TypeError, ValueError):
                continue
        return [item for _, item in sorted(items, key=lambda pair: pair[0])]
    return []
