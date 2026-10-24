"use client";

import { formatTime, sessionLabel } from "@/lib/format";
import type { LibraryEntry } from "@/lib/types";

interface Props {
  entries: LibraryEntry[] | null;
  onOpen: (id: string) => void;
}

function day(start: string) {
  const date = new Date(start);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString("fr-FR", { weekday: "short", day: "numeric", month: "short" });
}

// Sessions of the same weekend together, newest weekend first
function byWeekend(entries: LibraryEntry[]) {
  const groups: { key: string; meeting: string; year: number | null; sessions: LibraryEntry[] }[] = [];
  for (const entry of entries) {
    const key = `${entry.year} ${entry.meeting}`;
    let group = groups.find((g) => g.key === key);
    if (!group) groups.push((group = { key, meeting: entry.meeting, year: entry.year, sessions: [] }));
    group.sessions.push(entry);
  }
  return groups;
}

export default function Library({ entries, onOpen }: Props) {
  if (entries == null) return <p className="empty">Chargement de la bibliothèque…</p>;
  if (entries.length === 0) {
    return <p className="empty">Rien pour l&apos;instant. Chaque séance suivie en direct viendra s&apos;ajouter ici.</p>;
  }

  return (
    <div className="library">
      {byWeekend(entries).map((group) => (
        <section key={group.key} className="library-weekend">
          <h3>
            {group.meeting || "Séance"} <span className="library-year">{group.year}</span>
          </h3>
          <ul>
            {group.sessions.map((entry) => (
              <li key={entry.id}>
                <button className="library-session" onClick={() => onOpen(entry.id)}>
                  <span className="library-name">{sessionLabel(entry.name) || entry.id}</span>
                  <span className="library-day">{day(entry.start)}</span>
                  <span className="library-duration mono">{formatTime(entry.duration)}</span>
                  {entry.source === "archive" && <span className="library-badge">Archives</span>}
                </button>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}
