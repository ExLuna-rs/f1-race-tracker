"""
The next session on the calendar, for the page shown while nothing is live.
"""

from datetime import datetime, timedelta, timezone

# A session still counts as next until this long after its start
SESSION_LENGTH = timedelta(hours=2)


def next_session(weekends_by_year, now=None):
    """First session of this year's calendar, or next year's, not over yet.

    `weekends_by_year(year)` returns the weekends as src.f1_data's
    get_race_weekends_by_year does, with each session's local start time.
    """
    now = now or datetime.now(timezone.utc)
    for year in (now.year, now.year + 1):
        try:
            weekends = weekends_by_year(year)
        except Exception:
            continue
        upcoming = []
        for weekend in weekends:
            for name, start in (weekend.get("session_dates") or {}).items():
                try:
                    begins = datetime.fromisoformat(start)
                except (TypeError, ValueError):
                    continue
                if begins.tzinfo is None:
                    begins = begins.replace(tzinfo=timezone.utc)
                if begins + SESSION_LENGTH > now:
                    upcoming.append((begins, name, weekend))
        if upcoming:
            begins, name, weekend = min(upcoming, key=lambda item: item[0])
            return {
                "meeting": weekend.get("event_name", ""),
                "round": int(weekend.get("round_number") or 0),
                "name": name,
                "start": begins.astimezone(timezone.utc).isoformat(),
            }
    return None
