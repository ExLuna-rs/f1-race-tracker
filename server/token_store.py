"""
Stores the F1 TV subscription token used for the live feed.

The token comes from the formula1.com "login-session" cookie after signing in
with an F1 TV account. It can be pasted either as the raw token or as the
whole cookie value, which is URL-encoded JSON holding the token.
"""

import base64
import json
import os
import time
import urllib.parse


def extract_token(text):
    """Return the subscription token from a raw token or a login-session cookie."""
    text = (text or "").strip()
    if not text:
        raise ValueError("Empty token")
    if text.count(".") == 2 and not text.startswith(("{", "%7B")):
        return text
    try:
        data = json.loads(urllib.parse.unquote(text))
    except json.JSONDecodeError as e:
        raise ValueError("Not a token or a login-session cookie") from e
    token = (data.get("data") or {}).get("subscriptionToken")
    if not token:
        raise ValueError("No subscriptionToken in the cookie")
    return token


def token_claims(token):
    """Decode the JWT payload without checking the signature.

    F1 checks the signature itself; we only read the expiry for display.
    """
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload))
    except (IndexError, ValueError):
        return {}


class TokenStore:
    def __init__(self, path):
        self.path = path

    def get(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                token = f.read().strip()
        except FileNotFoundError:
            return None
        return token or None

    def set(self, text):
        """Store a token. Returns the status and whether the token changed."""
        token = extract_token(text)
        changed = token != self.get()
        if changed:
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as f:
                f.write(token)
            os.chmod(self.path, 0o600)
        return {**self.status(), "changed": changed}

    def clear(self):
        try:
            os.remove(self.path)
        except FileNotFoundError:
            pass

    def status(self):
        token = self.get()
        if not token:
            return {"present": False, "expires_at": None, "expired": None}
        exp = token_claims(token).get("exp")
        return {
            "present": True,
            "expires_at": exp,
            "expired": bool(exp and exp < time.time()),
        }
