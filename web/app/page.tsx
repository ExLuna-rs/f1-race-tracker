"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import Controls from "@/components/Controls";
import DriverPanel from "@/components/DriverPanel";
import Header from "@/components/Header";
import Home from "@/components/Home";
import Leaderboard from "@/components/Leaderboard";
import Nav, { type Route } from "@/components/Nav";
import SessionBanner from "@/components/SessionBanner";
import TokenWarning from "@/components/TokenWarning";
import RaceControl from "@/components/RaceControl";
import TrackMap from "@/components/TrackMap";
import TyreStrategy from "@/components/TyreStrategy";
import { sessionKind } from "@/lib/format";
import { useLibrary, useNextSession } from "@/lib/useLibrary";
import { useStatus } from "@/lib/useStatus";
import { useStream } from "@/lib/useStream";

type Tab = "telemetry" | "strategy" | "race-control";

const TABS: { id: Tab; label: string }[] = [
  { id: "telemetry", label: "Télémétrie" },
  { id: "strategy", label: "Stratégie pneus" },
  { id: "race-control", label: "Direction de course" },
];

// "/" follows live, "/?library" lists the library, "/?session=<id>" plays one
function parseRoute(): Route {
  const params = new URLSearchParams(window.location.search);
  const id = params.get("session");
  if (id) return { view: "session", id };
  if (params.has("library")) return { view: "library" };
  return { view: "live" };
}

function routeUrl(route: Route) {
  if (route.view === "session") return `/?session=${encodeURIComponent(route.id)}`;
  return route.view === "library" ? "/?library" : "/";
}

export default function Viewer() {
  const [route, setRoute] = useState<Route>({ view: "live" });
  const { connected, error, meta, frame, playback, motion, history, send } = useStream(
    route.view === "session" ? route.id : "live",
  );
  const status = useStatus();
  const library = useLibrary();
  const next = useNextSession();
  const [selected, setSelected] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("telemetry");
  const kind = sessionKind(meta.session);

  // Clicking the selected driver again clears the selection
  const toggle = (code: string | null) => setSelected((current) => (code === current ? null : code));
  // From the leaderboard or the map, show the driver's telemetry. Within a
  // tab (tyre strategy), only highlight the driver and stay on that tab.
  const selectAndShow = (code: string | null) => {
    toggle(code);
    if (code && code !== selected) setTab("telemetry");
  };
  const info = meta.drivers?.find((d) => d.code === selected);

  useEffect(() => {
    setRoute(parseRoute());
    const onPop = () => setRoute(parseRoute());
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  const navigate = (next: Route) => {
    window.history.pushState(null, "", routeUrl(next));
    setRoute(next);
  };
  const liveActive = !!status?.live_active;
  const nav = <Nav route={route} liveActive={liveActive} onNavigate={navigate} />;
  // Nothing on: the next session and the library instead of an empty map
  const idle = route.view === "live" && status != null && !liveActive;

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setSelected(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  if (idle || route.view === "library") {
    return (
      <div className="app">
        <header className="header">
          <div className="header-title">
            <h1>F1 Race Tracker</h1>
          </div>
          <div className="header-info">
            {nav}
            <Link href="/admin" className="admin-link">
              Admin
            </Link>
          </div>
        </header>
        <Home idle={idle} next={next} library={library} onOpen={(id) => navigate({ view: "session", id })} />
      </div>
    );
  }

  if (error) {
    return (
      <div className="app">
        <header className="header">
          <div className="header-title">
            <h1>F1 Race Tracker</h1>
          </div>
          <div className="header-info">{nav}</div>
        </header>
        <main className="home">
          <section className="panel home-live">
            <h2>{error}</h2>
            <p className="hint">Elle a peut-être été retirée de la bibliothèque.</p>
            <button onClick={() => navigate({ view: "library" })}>Voir la bibliothèque</button>
          </section>
        </main>
      </div>
    );
  }

  return (
    <div className="app">
      <Header meta={meta} frame={frame} playback={playback} connected={connected} kind={kind} nav={nav} />
      <SessionBanner status={route.view === "live" ? status : null} connected={connected} />
      <TokenWarning status={status} />
      <main className="main">
        <section className="panel map-panel">
          <TrackMap meta={meta} motion={motion} selected={selected} onSelect={selectAndShow} />
        </section>
        <section className="panel board-panel">
          <Leaderboard meta={meta} frame={frame} kind={kind} selected={selected} onSelect={selectAndShow} />
        </section>
        <section className="panel controls-panel">
          <Controls meta={meta} playback={playback} send={send} />
        </section>
        <section className="panel tabs-panel">
          <nav className="tabs">
            {TABS.map((item) => (
              <button
                key={item.id}
                className={tab === item.id ? "active" : ""}
                onClick={() => setTab(item.id)}
              >
                {item.label}
              </button>
            ))}
          </nav>
          <div className="tab-body">
            {tab === "telemetry" && (
              <DriverPanel
                code={selected}
                driver={selected ? frame?.drivers[selected] : undefined}
                info={info}
                samples={(selected && history.current.get(selected)) || []}
                now={frame?.t ?? 0}
              />
            )}
            {tab === "strategy" && (
              <TyreStrategy meta={meta} frame={frame} selected={selected} onSelect={toggle} />
            )}
            {tab === "race-control" && <RaceControl meta={meta} t={frame?.t ?? 0} />}
          </div>
        </section>
      </main>
    </div>
  );
}
