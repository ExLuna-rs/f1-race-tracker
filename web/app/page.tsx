"use client";

import { useState } from "react";
import Controls from "@/components/Controls";
import DriverPanel from "@/components/DriverPanel";
import Header from "@/components/Header";
import Leaderboard from "@/components/Leaderboard";
import RaceControl from "@/components/RaceControl";
import TrackMap from "@/components/TrackMap";
import TyreStrategy from "@/components/TyreStrategy";
import { sessionKind } from "@/lib/format";
import { useStream } from "@/lib/useStream";

type Tab = "telemetry" | "strategy" | "race-control";

const TABS: { id: Tab; label: string }[] = [
  { id: "telemetry", label: "Télémétrie" },
  { id: "strategy", label: "Stratégie pneus" },
  { id: "race-control", label: "Direction de course" },
];

export default function Viewer() {
  const { connected, meta, frame, playback, motion, history, send } = useStream();
  const [selected, setSelected] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("telemetry");
  const kind = sessionKind(meta.session);

  const select = (code: string) => {
    setSelected(code);
    setTab("telemetry");
  };
  const info = meta.drivers?.find((d) => d.code === selected);

  return (
    <div className="app">
      <Header meta={meta} frame={frame} playback={playback} connected={connected} kind={kind} />
      <main className="main">
        <section className="panel map-panel">
          <TrackMap meta={meta} motion={motion} selected={selected} onSelect={select} />
        </section>
        <section className="panel board-panel">
          <Leaderboard meta={meta} frame={frame} kind={kind} selected={selected} onSelect={select} />
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
              <TyreStrategy meta={meta} frame={frame} selected={selected} onSelect={select} />
            )}
            {tab === "race-control" && <RaceControl meta={meta} t={frame?.t ?? 0} />}
          </div>
        </section>
      </main>
    </div>
  );
}
