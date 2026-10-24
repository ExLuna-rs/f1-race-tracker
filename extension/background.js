// Sends the formula1.com login-session cookie to the tracker whenever it
// changes. The cookie holds the F1 TV subscription token the live feed needs;
// the server extracts the token from it, so it is sent as is.

const COOKIE_NAME = "login-session";
const COOKIE_URL = "https://www.formula1.com/";
// Catch a renewal even if the browser missed the change event
const CHECK_EVERY_MINUTES = 6 * 60;

const api = globalThis.browser ?? globalThis.chrome;

async function settings() {
  const { serverUrl = "", password = "" } = await api.storage.local.get(["serverUrl", "password"]);
  return { serverUrl: serverUrl.replace(/\/+$/, ""), password };
}

async function record(result) {
  await api.storage.local.set({ lastResult: { ...result, at: Date.now() } });
  api.action.setBadgeText({ text: result.ok ? "" : "!" });
  api.action.setBadgeBackgroundColor({ color: "#e10600" });
}

async function send(force = false) {
  const { serverUrl, password } = await settings();
  if (!serverUrl || !password) {
    await record({ ok: false, message: "Serveur ou mot de passe non configuré" });
    return;
  }
  const cookie = await api.cookies.get({ url: COOKIE_URL, name: COOKIE_NAME });
  if (!cookie) {
    await record({ ok: false, message: "Pas connecté sur formula1.com" });
    return;
  }
  const { lastSent } = await api.storage.local.get("lastSent");
  if (!force && lastSent === cookie.value) return;

  try {
    const res = await fetch(`${serverUrl}/api/admin/token`, {
      method: "PUT",
      headers: { "Content-Type": "application/json", "X-Admin-Password": password },
      body: JSON.stringify({ token: cookie.value }),
      credentials: "include",
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      await record({ ok: false, message: data.detail ?? `Erreur ${res.status}` });
      return;
    }
    await api.storage.local.set({ lastSent: cookie.value });
    await record({ ok: true, message: "Token envoyé", expiresAt: data.expires_at, expired: data.expired });
  } catch (e) {
    await record({ ok: false, message: `Serveur injoignable : ${e.message}` });
  }
}

api.cookies.onChanged.addListener(({ cookie, removed }) => {
  if (!removed && cookie.name === COOKIE_NAME && cookie.domain.endsWith("formula1.com")) send();
});

api.alarms.create("check", { periodInMinutes: CHECK_EVERY_MINUTES });
api.alarms.onAlarm.addListener(() => send());
api.runtime.onStartup.addListener(() => send());
api.runtime.onInstalled.addListener(() => api.runtime.openOptionsPage());
api.action.onClicked.addListener(() => api.runtime.openOptionsPage());

api.runtime.onMessage.addListener((message, _sender, reply) => {
  if (message === "send-now") {
    send(true).then(() => reply(true));
    return true;
  }
});
