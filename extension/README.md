# Extension: token F1 TV automatique

The live feed only sends car positions and telemetry with an F1 TV token, and
that token expires after about a week. This browser extension sends it to the
tracker on its own: whenever the formula1.com `login-session` cookie changes
(you log in, or the site renews it), it calls `PUT /api/admin/token`, and the
server reconnects live timing with the new token.

Your formula1.com password never leaves the browser; only the cookie is sent,
and only to the tracker address you enter.

## Install

**Chrome, Edge, Brave**

1. Open `chrome://extensions` and turn on developer mode.
2. Click *Load unpacked* and pick this `extension/` folder.
3. The options page opens: enter the tracker address (for example
   `https://f1.example.com`) and the admin password, then allow access to that
   address when the browser asks.

**Firefox**

Open `about:debugging#/runtime/this-firefox`, click *Load Temporary Add-on* and
pick `manifest.json`. Firefox removes unsigned add-ons on restart; to keep it,
sign it as an unlisted add-on on addons.mozilla.org (free, no store listing).

## Use

Stay logged in on formula1.com with the F1 TV account in that browser. The
extension sends the token when the cookie changes and checks again every six
hours. Its options page shows the last result and when the token expires; the
toolbar icon shows a red `!` when the last attempt failed.

When the token is about to expire, the tracker shows a banner. Visiting
formula1.com is usually enough to renew it; if the site logged you out, log in
again and the extension does the rest.

## Cloudflare Access

If the tracker sits behind Cloudflare Access, the extension's request must get
through it too. Either stay signed in to Access in the same browser, or let
`/api/admin/token` bypass Access: that endpoint is still protected by the admin
password.
