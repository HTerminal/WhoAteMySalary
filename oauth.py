# -*- coding: utf-8 -*-
"""OAuth 2.0 sign-in for IMAP (XOAUTH2) — pure standard library.

Supports two providers:
  * "google"    — Gmail          (imap.gmail.com)
  * "microsoft" — Outlook/Office (outlook.office365.com)

Both use the same "installed application" flow: a loopback redirect + PKCE, so a
user grants access from their browser and never enters a password into the app.
Google uses a Desktop-app client (with secret); Microsoft uses a public/native
client (PKCE only, no secret needed). The resulting access token is used for IMAP
via the XOAUTH2 SASL mechanism.

Nothing here is Qt- or app-specific; it only needs `config` for the client
credentials. Tokens (refresh + short-lived access) are stored in `tokens.json`
next to this file, which is git-ignored — they never leave the machine.

No third-party packages required.
"""
import base64, hashlib, http.server, json, os, secrets, threading, time
import urllib.parse, urllib.request, webbrowser

import config
try:
    import oauth_defaults
except Exception:                       # pragma: no cover - defaults are optional
    oauth_defaults = None

HERE = os.path.dirname(os.path.abspath(__file__))
TOKENS_PATH = os.path.join(HERE, "tokens.json")

# Per-provider endpoints, IMAP host and scope. "common" tenant lets Microsoft
# accept both personal (outlook.com/hotmail) and work/school accounts.
PROVIDERS = {
    "google": {
        "label": "Google",
        "auth_uri": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "scope": "https://mail.google.com/",
        "imap_host": "imap.gmail.com",
        "extra_auth": {"access_type": "offline", "prompt": "consent"},
        "needs_secret": True,           # Google "Desktop app" client has a secret
        "send_scope_on_token": False,
    },
    "microsoft": {
        "label": "Microsoft",
        "auth_uri": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
        "token_uri": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
        # offline_access -> refresh token; IMAP.AccessAsUser.All -> IMAP via XOAUTH2
        "scope": "https://outlook.office.com/IMAP.AccessAsUser.All offline_access",
        "imap_host": "outlook.office365.com",
        "extra_auth": {"prompt": "select_account"},
        "needs_secret": False,          # public/native client — PKCE, no secret
        "send_scope_on_token": True,
    },
}
DEFAULT_PROVIDER = "google"

_lock = threading.RLock()


def provider_of(account):
    """The OAuth provider for a mailbox ('google' | 'microsoft')."""
    p = (account or {}).get("provider") or DEFAULT_PROVIDER
    return p if p in PROVIDERS else DEFAULT_PROVIDER


def imap_host(provider):
    return PROVIDERS.get(provider, PROVIDERS[DEFAULT_PROVIDER])["imap_host"]


def provider_label(provider):
    return PROVIDERS.get(provider, PROVIDERS[DEFAULT_PROVIDER])["label"]


# --------------------------------------------------------------------------- creds
def _cfg_keys(provider):
    return (f"{provider}_client_id", f"{provider}_client_secret",
            f"MMT_{provider.upper()}_CLIENT_ID", f"MMT_{provider.upper()}_CLIENT_SECRET")


def client_creds(account=None, cfg=None, provider=None):
    """Resolve (client_id, client_secret, source) for a mailbox/provider.

    Order: the mailbox's own override -> config['oauth'] -> the bundled default
    (env / oauth_defaults). `source` is a short human string for the UI."""
    provider = provider or provider_of(account)
    id_key, sec_key, env_id, env_sec = _cfg_keys(provider)
    if account:
        cid = (account.get("oauth_client_id") or "").strip()
        csec = (account.get("oauth_client_secret") or "").strip()
        if cid:
            return cid, csec, "this mailbox"
    cfg = cfg or config.load()
    o = cfg.get("oauth", {}) or {}
    cid = (o.get(id_key) or "").strip()
    csec = (o.get(sec_key) or "").strip()
    if cid:
        return cid, csec, "Settings"
    if oauth_defaults:
        cid = (getattr(oauth_defaults, env_id, "") or "").strip()
        csec = (getattr(oauth_defaults, env_sec, "") or "").strip()
        if cid:
            return cid, csec, "bundled default"
    return "", "", "none"


def have_client(account=None, cfg=None, provider=None):
    return bool(client_creds(account, cfg, provider)[0])


# --------------------------------------------------------------------------- token store
def _load_tokens():
    with _lock:
        if not os.path.exists(TOKENS_PATH):
            return {}
        try:
            with open(TOKENS_PATH, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}


def _save_tokens(data):
    with _lock:
        tmp = TOKENS_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, TOKENS_PATH)
        try:
            os.chmod(TOKENS_PATH, 0o600)     # best-effort: keep tokens private
        except Exception:
            pass


def has_token(email):
    return bool((_load_tokens().get(email or "") or {}).get("refresh_token"))


def status(email):
    return "Connected" if has_token(email) else "Not signed in"


def forget(email):
    with _lock:
        data = _load_tokens()
        if email in data:
            del data[email]
            _save_tokens(data)


# --------------------------------------------------------------------------- HTTP helpers
def _post_form(url, fields):
    body = urllib.parse.urlencode(fields).encode()
    req = urllib.request.Request(url, data=body, method="POST",
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode())
        except Exception:
            return {"error": f"http_{e.code}", "error_description": str(e)}


class _CatchHandler(http.server.BaseHTTPRequestHandler):
    """One-shot handler that captures the ?code=... redirect."""
    result = {}

    def do_GET(self):
        q = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(q)
        _CatchHandler.result = {k: v[0] for k, v in params.items()}
        ok = "code" in _CatchHandler.result
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        msg = ("Signed in successfully. You can close this tab and return to "
               "WhoAteMySalary.") if ok else \
              "Sign-in failed or was cancelled. You can close this tab."
        self.wfile.write((
            "<!doctype html><meta charset='utf-8'>"
            "<title>WhoAteMySalary</title>"
            "<div style='font-family:Segoe UI,Arial,sans-serif;max-width:520px;"
            "margin:80px auto;text-align:center'>"
            "<div style='font-size:44px'>%s</div>"
            "<h2 style='color:#0f172a'>%s</h2></div>"
            % ("&#10003;" if ok else "&#10007;", msg)).encode())

    def log_message(self, *a):
        pass                                # keep the console quiet


def _pkce():
    verifier = base64.urlsafe_b64encode(os.urandom(40)).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


# --------------------------------------------------------------------------- the flow
def authorize(email, provider="google", client_id="", client_secret="",
              timeout=180, open_browser=True):
    """Run the interactive sign-in for `email` on `provider`. Blocks until the
    user finishes in the browser (or `timeout` seconds pass). On success the
    refresh token is stored. Returns (ok: bool, message: str).

    Safe to run in a background thread — it does no Qt work."""
    P = PROVIDERS.get(provider)
    if not P:
        return False, f"Unknown provider: {provider}"
    if not client_id:
        return False, (f"No {P['label']} OAuth client configured. Add a Client ID in "
                       f"Settings, or build with a bundled default.")
    verifier, challenge = _pkce()
    state = secrets.token_urlsafe(16)

    # loopback server on an ephemeral port. Bind on 127.0.0.1, but advertise the
    # redirect as http://localhost:<port>/ . Microsoft ignores the port (and allows
    # the http scheme) ONLY for the *localhost* host, and treats "localhost" and
    # "127.0.0.1" as DIFFERENT registered redirect URIs. The public-client redirect
    # users register is http://localhost, so the host here must be localhost or the
    # sign-in fails with AADSTS50011 (reply-URL mismatch). Google's loopback flow
    # accepts localhost equally, so this is correct for both providers.
    httpd = http.server.HTTPServer(("127.0.0.1", 0), _CatchHandler)
    httpd.timeout = timeout
    port = httpd.server_address[1]
    redirect_uri = f"http://localhost:{port}/"
    _CatchHandler.result = {}

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": P["scope"],
        "login_hint": email or "",
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    params.update(P.get("extra_auth", {}))
    url = P["auth_uri"] + "?" + urllib.parse.urlencode(params)

    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass

    def _serve():
        try:
            httpd.handle_request()          # blocks until one request or timeout
        except Exception:
            pass

    th = threading.Thread(target=_serve, daemon=True)
    th.start()
    th.join(timeout + 5)
    try:
        httpd.server_close()
    except Exception:
        pass

    res = _CatchHandler.result
    if not res:
        return False, ("Timed out waiting for the browser sign-in. If your "
                       "browser didn't open, copy this URL into it:\n" + url)
    if res.get("state") != state:
        return False, "Sign-in aborted: state mismatch (possible CSRF). Try again."
    if "error" in res:
        return False, f"{P['label']} returned: " + res.get("error", "unknown error")
    code = res.get("code")
    if not code:
        return False, "No authorization code was returned. Try again."

    fields = {
        "code": code,
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
        "code_verifier": verifier,
    }
    if client_secret:
        fields["client_secret"] = client_secret
    if P.get("send_scope_on_token"):
        fields["scope"] = P["scope"]
    tok = _post_form(P["token_uri"], fields)
    if "error" in tok or "access_token" not in tok:
        return False, ("Token exchange failed: "
                       + tok.get("error_description", tok.get("error", "unknown")))
    refresh = tok.get("refresh_token")
    if not refresh:
        return False, (f"{P['label']} did not return a refresh token. Remove this "
                       f"app's access in your account settings and try again.")
    with _lock:
        data = _load_tokens()
        data[email] = {
            "provider": provider,
            "refresh_token": refresh,
            "access_token": tok.get("access_token", ""),
            "expiry": time.time() + int(tok.get("expires_in", 3600)) - 60,
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": tok.get("scope", P["scope"]),
        }
        _save_tokens(data)
    return True, f"Signed in with {P['label']}."


def _refresh(email, rec):
    provider = rec.get("provider", DEFAULT_PROVIDER)
    P = PROVIDERS.get(provider, PROVIDERS[DEFAULT_PROVIDER])
    fields = {
        "client_id": rec.get("client_id", ""),
        "grant_type": "refresh_token",
        "refresh_token": rec["refresh_token"],
    }
    if rec.get("client_secret"):
        fields["client_secret"] = rec["client_secret"]
    if P.get("send_scope_on_token"):
        fields["scope"] = P["scope"]
    tok = _post_form(P["token_uri"], fields)
    if "access_token" not in tok:
        raise RuntimeError("token refresh failed: "
                           + tok.get("error_description", tok.get("error", "unknown")))
    rec["access_token"] = tok["access_token"]
    rec["expiry"] = time.time() + int(tok.get("expires_in", 3600)) - 60
    # Microsoft may rotate the refresh token — keep the newest one.
    if tok.get("refresh_token"):
        rec["refresh_token"] = tok["refresh_token"]
    with _lock:
        data = _load_tokens()
        data[email] = rec
        _save_tokens(data)
    return rec["access_token"]


def access_token(email):
    """Return a currently-valid access token for `email`, refreshing if needed.
    Raises RuntimeError if the mailbox has never been signed in."""
    rec = _load_tokens().get(email or "")
    if not rec or not rec.get("refresh_token"):
        raise RuntimeError(f"{email} is not signed in. Open Settings and use "
                           f"'Sign in with Google' or 'Sign in with Microsoft'.")
    if rec.get("access_token") and time.time() < float(rec.get("expiry", 0)):
        return rec["access_token"]
    return _refresh(email, rec)


def xoauth2_bytes(email, token):
    """The raw SASL XOAUTH2 string for imaplib's authenticate() (it base64-encodes)."""
    return f"user={email}\x01auth=Bearer {token}\x01\x01".encode()
