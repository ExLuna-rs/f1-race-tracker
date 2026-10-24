"use client";

export type Route = { view: "live" } | { view: "library" } | { view: "session"; id: string };

interface Props {
  route: Route;
  liveActive: boolean;
  onNavigate: (route: Route) => void;
}

export default function Nav({ route, liveActive, onNavigate }: Props) {
  return (
    <nav className="nav" aria-label="Choix de la séance">
      <button
        className={route.view === "live" ? "active" : ""}
        aria-current={route.view === "live" ? "page" : undefined}
        onClick={() => onNavigate({ view: "live" })}
      >
        <span className={`live-dot${liveActive ? " on" : ""}`} aria-hidden />
        Direct
      </button>
      <button
        className={route.view !== "live" ? "active" : ""}
        aria-current={route.view === "library" ? "page" : undefined}
        onClick={() => onNavigate({ view: "library" })}
      >
        Bibliothèque
      </button>
    </nav>
  );
}
