const api = globalThis.browser ?? globalThis.chrome;
const form = document.getElementById("form");
const serverUrl = document.getElementById("serverUrl");
const password = document.getElementById("password");
const result = document.getElementById("result");

async function showResult() {
  const { lastResult } = await api.storage.local.get("lastResult");
  if (!lastResult) return;
  let text = `${lastResult.message} (${new Date(lastResult.at).toLocaleString("fr-FR")})`;
  if (lastResult.expiresAt) {
    const date = new Date(lastResult.expiresAt * 1000).toLocaleString("fr-FR");
    text += lastResult.expired ? `. Ce token a expiré le ${date} : reconnectez-vous sur formula1.com.` : `. Valide jusqu'au ${date}.`;
  }
  result.textContent = text;
  result.className = lastResult.ok && !lastResult.expired ? "ok" : "error";
  result.hidden = false;
}

api.storage.local.get(["serverUrl", "password"]).then((saved) => {
  serverUrl.value = saved.serverUrl ?? "";
  password.value = saved.password ?? "";
});
showResult();

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const url = serverUrl.value.trim().replace(/\/+$/, "");
  // The extension may only call the hosts the user allowed
  const granted = await api.permissions.request({ origins: [`${new URL(url).origin}/*`] });
  if (!granted) {
    result.textContent = "Autorisation refusée pour cette adresse.";
    result.className = "error";
    result.hidden = false;
    return;
  }
  await api.storage.local.set({ serverUrl: url, password: password.value });
  await api.runtime.sendMessage("send-now");
  showResult();
});
