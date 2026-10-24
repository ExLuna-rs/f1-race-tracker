"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import type { Status } from "@/lib/types";

// Warn this long before the F1 TV token expires
const WARN_BEFORE_S = 2 * 86400;
const CHECK_EVERY_MS = 5 * 60 * 1000;

function remaining(seconds: number) {
  const hours = Math.round(seconds / 3600);
  return hours >= 48 ? `${Math.round(hours / 24)} jours` : `${Math.max(hours, 1)} h`;
}

export default function TokenWarning() {
  const [status, setStatus] = useState<Status | null>(null);

  useEffect(() => {
    const load = () =>
      fetch("/api/status")
        .then((res) => (res.ok ? res.json() : null))
        .then(setStatus)
        .catch(() => setStatus(null));
    load();
    const timer = setInterval(load, CHECK_EVERY_MS);
    return () => clearInterval(timer);
  }, []);

  const token = status?.token;
  if (!token) return null;
  const left = token.expires_at ? token.expires_at - Date.now() / 1000 : null;

  let text: string | null = null;
  if (!token.present) {
    // Only matters while live timing runs: replays need no token
    if (status.live_running) text = "Aucun token F1 TV : pas de positions ni de télémétrie en direct.";
  } else if (token.expired || (left != null && left <= 0)) {
    text = "Le token F1 TV a expiré : positions et télémétrie en direct indisponibles.";
  } else if (left != null && left < WARN_BEFORE_S) {
    text = `Le token F1 TV expire dans ${remaining(left)}.`;
  }
  if (!text) return null;

  return (
    <div className="token-warning" role="status">
      {text} Ouvrez formula1.com avec l&apos;extension, ou collez un nouveau token dans <Link href="/admin">Admin</Link>.
    </div>
  );
}
