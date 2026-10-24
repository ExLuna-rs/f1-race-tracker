"use client";

import { useEffect, useState } from "react";
import type { Status } from "./types";

// Poll often while a session loads so its progress shows up quickly
const LOADING_EVERY_MS = 3000;
const IDLE_EVERY_MS = 30 * 1000;

export function useStatus(): Status | null {
  const [status, setStatus] = useState<Status | null>(null);
  const loading = !!status?.loading;

  useEffect(() => {
    let cancelled = false;
    const load = () =>
      fetch("/api/status")
        .then((res) => (res.ok ? res.json() : null))
        .then((next) => !cancelled && setStatus(next))
        .catch(() => !cancelled && setStatus(null));
    load();
    const timer = setInterval(load, loading ? LOADING_EVERY_MS : IDLE_EVERY_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [loading]);

  return status;
}
