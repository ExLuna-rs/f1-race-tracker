"use client";

import { useEffect, useState } from "react";
import type { Status } from "@/lib/types";

// The first connection takes a moment: only call it lost after this
const CONNECT_GRACE_MS = 2500;

interface Props {
  status: Status | null;
  connected: boolean;
}

// What the map and leaderboard can't show: a lost connection or live timing
// in error. `status` is only passed while following live.
export default function SessionBanner({ status, connected }: Props) {
  const [graceOver, setGraceOver] = useState(false);
  useEffect(() => {
    const timer = setTimeout(() => setGraceOver(true), CONNECT_GRACE_MS);
    return () => clearTimeout(timer);
  }, []);

  if (!connected && graceOver) {
    return (
      <div className="banner banner-error" role="alert">
        <span className="spinner" aria-hidden /> Connexion au serveur perdue, reconnexion…
      </div>
    );
  }
  const error = status?.live_running && status.live_error;
  if (error) {
    return (
      <div className="banner banner-error" role="alert">
        Direct en erreur : {error}
      </div>
    );
  }
  return null;
}
