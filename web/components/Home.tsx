"use client";

import { useEffect, useState } from "react";
import Library from "@/components/Library";
import { sessionLabel } from "@/lib/format";
import type { LibraryEntry, NextSession } from "@/lib/types";

interface Props {
  // Shown when nothing is live, not when the library was asked for
  idle: boolean;
  next: NextSession | null;
  library: LibraryEntry[] | null;
  onOpen: (id: string) => void;
}

function countdown(ms: number) {
  if (ms <= 0) return "d'un instant à l'autre";
  const minutes = Math.floor(ms / 60000);
  const days = Math.floor(minutes / 1440);
  const hours = Math.floor((minutes % 1440) / 60);
  const mins = minutes % 60;
  if (days > 0) return `dans ${days} j ${hours} h`;
  if (hours > 0) return `dans ${hours} h ${String(mins).padStart(2, "0")}`;
  return `dans ${Math.max(mins, 1)} min`;
}

function NextUp({ next }: { next: NextSession }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 30 * 1000);
    return () => clearInterval(timer);
  }, []);
  const start = new Date(next.start);
  const when = start.toLocaleString("fr-FR", {
    weekday: "long",
    day: "numeric",
    month: "long",
    hour: "2-digit",
    minute: "2-digit",
  });

  return (
    <div className="next-session">
      <span className="next-label">Prochaine séance</span>
      <strong>
        {sessionLabel(next.name)} · {next.meeting}
      </strong>
      <span>
        {when}, {countdown(start.getTime() - now)}
      </span>
    </div>
  );
}

export default function Home({ idle, next, library, onOpen }: Props) {
  return (
    <main className="home">
      {idle && (
        <section className="panel home-live">
          <h2>Pas de séance en direct</h2>
          {next ? <NextUp next={next} /> : <p className="hint">Calendrier indisponible.</p>}
          <p className="hint">La page passe en direct toute seule dès que la séance commence.</p>
        </section>
      )}
      <section className="panel home-library">
        <h2>Bibliothèque</h2>
        <Library entries={library} onOpen={onOpen} />
      </section>
    </main>
  );
}
