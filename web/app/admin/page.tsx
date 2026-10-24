"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import type { Status } from "@/lib/types";

const PASSWORD_KEY = "f1-admin-password";

interface Weekend {
  round_number: number;
  event_name: string;
  date: string;
  type: string;
}

interface TokenStatus {
  present: boolean;
  expires_at: number | null;
  expired: boolean | null;
}

function readPassword() {
  try {
    return localStorage.getItem(PASSWORD_KEY) ?? "";
  } catch {
    return "";
  }
}

export default function Admin() {
  const [password, setPassword] = useState("");
  const [status, setStatus] = useState<Status | null>(null);
  const [token, setToken] = useState<TokenStatus | null>(null);
  const [tokenInput, setTokenInput] = useState("");
  const [year, setYear] = useState(new Date().getFullYear());
  const [weekends, setWeekends] = useState<Weekend[] | null>(null);
  const [recordings, setRecordings] = useState<string[]>([]);
  const [message, setMessage] = useState<{ text: string; error: boolean } | null>(null);

  useEffect(() => setPassword(readPassword()), []);

  const call = useCallback(
    async (path: string, method = "GET", body?: unknown) => {
      const res = await fetch(path, {
        method,
        headers: {
          "X-Admin-Password": password,
          ...(body ? { "Content-Type": "application/json" } : {}),
        },
        body: body ? JSON.stringify(body) : undefined,
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail ?? `Erreur ${res.status}`);
      return data;
    },
    [password],
  );

  const run = async (action: () => Promise<unknown>, success: string) => {
    try {
      await action();
      setMessage({ text: success, error: false });
    } catch (e) {
      setMessage({ text: (e as Error).message, error: true });
    }
    refresh();
  };

  const refresh = useCallback(async () => {
    try {
      setStatus(await call("/api/status"));
      setRecordings(await call("/api/recordings"));
    } catch {
      setStatus(null);
    }
    try {
      setToken(await call("/api/admin/token"));
    } catch {
      setToken(null);
    }
  }, [call]);

  // Poll while something loads, otherwise every 5 s
  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, status?.loading ? 1500 : 5000);
    return () => clearInterval(timer);
  }, [refresh, status?.loading]);

  useEffect(() => {
    setWeekends(null);
    fetch(`/api/schedule/${year}`)
      .then((res) => (res.ok ? res.json() : []))
      .then(setWeekends)
      .catch(() => setWeekends([]));
  }, [year]);

  const savePassword = (value: string) => {
    setPassword(value);
    try {
      localStorage.setItem(PASSWORD_KEY, value);
    } catch {
      // Private mode: the password just won't be remembered
    }
  };

  const today = new Date().toISOString().slice(0, 10);
  const expires = token?.expires_at ? new Date(token.expires_at * 1000) : null;

  return (
    <div className="admin">
      <header className="admin-header">
        <h1>Administration</h1>
        <Link href="/">← Retour au suivi</Link>
      </header>

      {message && <div className={`notice${message.error ? " error" : ""}`}>{message.text}</div>}

      <section className="card">
        <h2>Mot de passe admin</h2>
        <input
          type="password"
          value={password}
          onChange={(e) => savePassword(e.target.value)}
          placeholder="ADMIN_PASSWORD du serveur"
          autoComplete="current-password"
        />
        <p className="hint">Gardé dans ce navigateur seulement. Les autres pages n&apos;en ont pas besoin.</p>
      </section>

      <section className="card">
        <h2>Session en cours</h2>
        {status ? (
          <dl className="facts">
            <dt>Mode</dt>
            <dd>{status.mode}</dd>
            <dt>Session</dt>
            <dd>{status.session ? `${status.session.meeting} · ${status.session.name}` : "–"}</dd>
            <dt>Direct</dt>
            <dd>
              {status.live_running ? (status.live_connected ? "connecté" : "connexion…") : "arrêté"}
              {status.live_error && <span className="error-text"> ({status.live_error})</span>}
            </dd>
            {status.loading && (
              <>
                <dt>Chargement</dt>
                <dd>{status.loading}… (plusieurs minutes la première fois)</dd>
              </>
            )}
            {status.error && (
              <>
                <dt>Erreur</dt>
                <dd className="error-text">{status.error}</dd>
              </>
            )}
          </dl>
        ) : (
          <p className="hint">Serveur injoignable.</p>
        )}
        <div className="row">
          <button onClick={() => run(() => call("/api/admin/live/start", "POST"), "Direct démarré")}>
            Démarrer le direct
          </button>
          <button onClick={() => run(() => call("/api/admin/live/stop", "POST"), "Direct arrêté")}>
            Arrêter le direct
          </button>
        </div>
      </section>

      <section className="card">
        <h2>Token F1 TV</h2>
        <p>
          {token == null
            ? "Entrez le mot de passe admin pour voir le token."
            : !token.present
              ? "Aucun token : le direct n'aura ni positions ni télémétrie."
              : token.expired
                ? `Expiré le ${expires?.toLocaleString("fr-FR")}.`
                : `Valide jusqu'au ${expires?.toLocaleString("fr-FR") ?? "?"}.`}
        </p>
        <textarea
          value={tokenInput}
          onChange={(e) => setTokenInput(e.target.value)}
          placeholder="Collez la valeur du cookie login-session de formula1.com, ou le token seul"
          rows={3}
        />
        <div className="row">
          <button
            disabled={!tokenInput.trim()}
            onClick={() =>
              run(async () => {
                await call("/api/admin/token", "PUT", { token: tokenInput });
                setTokenInput("");
              }, "Token enregistré. Redémarrez le direct pour l'utiliser.")
            }
          >
            Enregistrer
          </button>
          <button className="secondary" onClick={() => run(() => call("/api/admin/token", "DELETE"), "Token supprimé")}>
            Supprimer
          </button>
        </div>
        <p className="hint">
          Connectez-vous sur formula1.com avec le compte F1 TV, ouvrez les outils de développement, onglet
          Application → Cookies, et copiez la valeur de <code>login-session</code>. Le token dure environ une
          semaine.
        </p>
      </section>

      <section className="card">
        <h2>Revoir une course</h2>
        <div className="row">
          <label>
            Saison{" "}
            <select value={year} onChange={(e) => setYear(Number(e.target.value))}>
              {Array.from({ length: new Date().getFullYear() - 2017 }, (_, i) => new Date().getFullYear() - i).map(
                (y) => (
                  <option key={y}>{y}</option>
                ),
              )}
            </select>
          </label>
        </div>
        {weekends == null ? (
          <p className="hint">Chargement du calendrier…</p>
        ) : weekends.length === 0 ? (
          <p className="hint">Calendrier indisponible.</p>
        ) : (
          <ul className="weekends">
            {weekends.map((w) => (
              <li key={w.round_number} className={w.date > today ? "future" : ""}>
                <span className="round">{w.round_number}</span>
                <span className="event">{w.event_name}</span>
                <span className="date">{w.date}</span>
                <span className="actions">
                  {w.type.includes("sprint") && (
                    <button
                      className="secondary"
                      disabled={w.date > today}
                      onClick={() =>
                        run(
                          () => call("/api/admin/replay", "POST", { year, round: w.round_number, session_type: "S" }),
                          `Chargement du sprint ${w.event_name}`,
                        )
                      }
                    >
                      Sprint
                    </button>
                  )}
                  <button
                    disabled={w.date > today}
                    onClick={() =>
                      run(
                        () => call("/api/admin/replay", "POST", { year, round: w.round_number, session_type: "R" }),
                        `Chargement de la course ${w.event_name}`,
                      )
                    }
                  >
                    Course
                  </button>
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="card">
        <h2>Sessions enregistrées</h2>
        <p className="hint">Chaque session suivie en direct est enregistrée, qualifs et essais compris.</p>
        {recordings.length === 0 ? (
          <p className="hint">Aucun enregistrement.</p>
        ) : (
          <ul className="recordings">
            {recordings.map((name) => (
              <li key={name}>
                <code>{name}</code>
                <button
                  className="secondary"
                  onClick={() => run(() => call("/api/admin/recording", "POST", { name }), `Chargement de ${name}`)}
                >
                  Charger
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
