"""
Convert a FastF1 live timing file into a recording the server can play.

FastF1's `python -m fastf1.livetiming save out.txt` writes one Python list per
line: [topic, data, utc]. The server records JSON Lines instead.

    python -m server.import_recording saved.txt data/recordings/2025-bahrain-fp3.jsonl
"""

import ast
import json
import sys


def convert(source, target):
    written = skipped = 0
    with open(source, encoding="utf-8") as src, open(target, "w", encoding="utf-8") as out:
        for line in src:
            line = line.strip()
            if not line:
                continue
            try:
                row = ast.literal_eval(line)
            except (ValueError, SyntaxError):
                skipped += 1
                continue
            if not isinstance(row, list) or len(row) < 2:
                skipped += 1
                continue
            utc = row[2] if len(row) > 2 else None
            out.write(json.dumps({"topic": row[0], "data": row[1], "utc": utc}) + "\n")
            written += 1
    return written, skipped


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    written, skipped = convert(sys.argv[1], sys.argv[2])
    print(f"{written} messages written, {skipped} lines skipped")
