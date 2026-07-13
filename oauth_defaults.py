# -*- coding: utf-8 -*-
"""Optional *shipped* Google OAuth client.

If you (the person building the releases) want your users to be able to
"Sign in with Google" with **zero setup**, put a Google OAuth *Desktop app*
client here — then every downloaded copy uses it and users never touch the
Google Cloud console.

Resolution order used by oauth.py (first non-empty wins):
    1. per-mailbox override         (Settings → the mailbox's own client)
    2. config.json  ->  "oauth": {"google_client_id", "google_client_secret"}
    3. environment  ->  MMT_GOOGLE_CLIENT_ID / MMT_GOOGLE_CLIENT_SECRET
    4. the constants in this file

SECURITY NOTE
-------------
For a *Desktop app* OAuth client Google does **not** treat the client secret as
confidential (see Google's "installed app" flow docs), so shipping it is
acceptable. Even so, committing a secret to a PUBLIC repo is best avoided.
The recommended way to "ship yours" is to inject it at build time via the
MMT_GOOGLE_CLIENT_ID / MMT_GOOGLE_CLIENT_SECRET environment variables — the
release workflow (.github/workflows/release.yml) reads them from repo secrets.

Leave both blank to require each user to paste their own client in Settings.
"""
import os

# Google (Gmail) — a "Desktop app" client has both an id and a secret.
GOOGLE_CLIENT_ID = os.environ.get("MMT_GOOGLE_CLIENT_ID", "").strip()
GOOGLE_CLIENT_SECRET = os.environ.get("MMT_GOOGLE_CLIENT_SECRET", "").strip()

# Microsoft (Outlook/Office365) — a public/native client needs only an id
# (PKCE, no secret). Leave the secret blank unless you registered a confidential
# client. These names are read by oauth.client_creds() as the bundled default.
MMT_MICROSOFT_CLIENT_ID = os.environ.get("MMT_MICROSOFT_CLIENT_ID", "").strip()
MMT_MICROSOFT_CLIENT_SECRET = os.environ.get("MMT_MICROSOFT_CLIENT_SECRET", "").strip()

# Back-compat aliases so oauth.client_creds() finds the Google default under the
# same MMT_* attribute-name convention it uses for Microsoft.
MMT_GOOGLE_CLIENT_ID = GOOGLE_CLIENT_ID
MMT_GOOGLE_CLIENT_SECRET = GOOGLE_CLIENT_SECRET
