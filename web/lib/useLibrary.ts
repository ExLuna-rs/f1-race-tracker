"use client";

import { useEffect, useState } from "react";
import type { LibraryEntry, NextSession } from "./types";

// Sessions join the library when they end, so a slow refresh is enough
const REFRESH_EVERY_MS = 60 * 1000;

export function useLibrary(): LibraryEntry[] | null {
  const [entries, setEntries] = useState<LibraryEntry[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = () =>
      fetch("/api/library")
        .then((res) => (res.ok ? res.json() : []))
        .then((next) => !cancelled && setEntries(next))
        .catch(() => !cancelled && setEntries((current) => current ?? []));
    load();
    const timer = setInterval(load, REFRESH_EVERY_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);

  return entries;
}

export function useNextSession(): NextSession | null {
  const [next, setNext] = useState<NextSession | null>(null);

  useEffect(() => {
    fetch("/api/next")
      .then((res) => (res.ok ? res.json() : null))
      .then(setNext)
      .catch(() => setNext(null));
  }, []);

  return next;
}
