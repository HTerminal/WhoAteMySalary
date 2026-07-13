# Mail Money Tracker

**Turn your bank's transaction-alert emails into a private, local spending dashboard — no bank logins, no cloud, no spreadsheets.**

[![License: GPLv3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB.svg?logo=python&logoColor=white)](https://www.python.org/downloads/release/python-3120/)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg)](#download--install)
[![Download](https://img.shields.io/badge/Download-Releases-brightgreen.svg)](https://github.com/OWNER/REPO/releases)

Mail Money Tracker is a native **PyQt5** desktop app. It connects to your Gmail over
**read-only IMAP**, finds the "you spent ₹…" / "you received ₹…" alert emails your banks
already send you, parses out the amount, direction and merchant, pops a Windows desktop
notification, and lets you categorise and analyse where your money goes. Everything stays
on your machine.

> Replace `OWNER/REPO` in the links above with your actual GitHub repository
> (suggested name: **`mail-money-tracker`**).

![Overview dashboard](docs/screenshots/overview.png)

---

## Features

- **Reads the emails you already get.** No screen-scraping, no bank credentials, no
  third-party aggregator. Just the transaction alerts your bank emails you.
- **Two safe sign-in methods** — [Sign in with Google (OAuth2)](#sign-in-with-google-recommended)
  (browser-based, no password ever stored) or a [Gmail app password](#use-a-gmail-app-password).
- **Smart parser** that pulls the amount + currency out of messy alert text while
  deliberately ignoring "available balance" and "credit limit" figures, detects the
  direction (money in vs money out), and extracts the merchant, card (e.g. `XX1009`) and bank.
- **Multi-currency aware** — understands ₹/INR, `$`/USD, `£`, `€`, and more, and flags
  foreign-currency transactions.
- **Automatic categorisation** with a broad, India-friendly category set (Groceries, Food
  delivery, Fuel, Subscriptions, EMIs, and dozens more), plus **merchant memory** so a
  payee keeps the category you last chose.
- **Credit-card bills done right.** A credit-card *bill payment* is neither income nor
  spend (the individual card purchases are already counted), so it gets its own bucket and
  is never double-counted.
- **Interactive dashboard** — KPI cards, an interactive donut you can click to drill in,
  month-by-month bars, incoming-by-source, an expandable merchant tree, and highlighted
  large transactions.
- **Review queue** — every newly detected transaction appears for a quick verify /
  categorise / skip, with a desktop notification.
- **Desktop notifications** on Windows (Action Center, with sound) via `windows-toasts`,
  degrading gracefully to `winotify` → `plyer` → console. A **Send test notification**
  button lets you confirm alerts work.
- **Parser page** with a paste-an-email tester that explains exactly what it extracted and
  why, plus custom keyword/merchant rules you can add yourself.
- **Fully local & private** — read-only IMAP only; your config, tokens and databases never
  leave your computer.

---

## Screenshots

**Review queue** — verify and categorise each new transaction as it arrives:

![Review queue](docs/screenshots/review.png)

**Transactions** — a sortable, searchable table you can tag and export to CSV:

![Transactions table](docs/screenshots/transactions.png)

**Settings** — mailboxes, tracked sources, notifications, and Google sign-in setup:

![Settings](docs/screenshots/settings.png)

There is also a **Parser** page (`docs/screenshots/parser.png`) where you can paste any
alert email and watch the 4-step pipeline explain its decision.

> The screenshots use fabricated demo data (`you@example.com`) — no real accounts.

---

## Download & Install

Grab the latest build for your OS from the
[**Releases**](https://github.com/OWNER/REPO/releases) page.

### Windows
Download the `.exe` (or installer), then run it. Windows SmartScreen may warn about an
unrecognised publisher on first launch — click **More info → Run anyway**.

### macOS
Download the `.dmg`, open it, and drag the app to **Applications**. Because the build is
not notarised, the first launch is blocked by Gatekeeper — **right-click (or Control-click)
the app → Open**, then confirm. You only need to do this once.

### Linux
Download the `AppImage`, make it executable, and run it:

```bash
chmod +x MailMoneyTracker-*.AppImage
./MailMoneyTracker-*.AppImage
```

### Run from source

Requires **Python 3.12** (PyQt5 has no wheels for the 3.15 alpha).

```bash
# clone your repo
git clone https://github.com/OWNER/REPO.git
cd REPO/mail_tracker_pyqt

# install dependencies
py -3.12 -m pip install -r requirements.txt

# run
py -3.12 app.py
```

On Windows you can also just double-click **`run_pyqt.bat`** (it installs PyQt5 on first
run), or **`start_pyqt_hidden.vbs`** to launch with no console window.

---

## Configuration

On first run the app creates a local `config.json` with sensible defaults; a shipped
[`config.example.json`](config.example.json) is included as a reference template. You can
add mailboxes and tune settings entirely from the **Settings** page — you don't need to
hand-edit JSON.

Each Gmail mailbox needs **one** of the two sign-in methods below.

### Sign in with Google (recommended)

The browser-based OAuth2 flow: you grant access in your browser and the app stores only a
refresh token in `tokens.json` — **your password is never entered or stored.**

If your copy of the app already ships with a Google client (see
[Ship your own Google client](#ship-your-own-google-client)), just open **Settings**, click
**Sign in with Google (OAuth2)** on the mailbox, and complete the browser prompt.

If it doesn't, you'll need a free Google Cloud OAuth **Desktop app** client (about 3
minutes):

1. Go to the [Google Cloud Console](https://console.cloud.google.com/) and **create a
   project** (or pick an existing one).
2. **Enable the Gmail API** for that project (APIs & Services → Library → Gmail API → Enable).
3. **Configure the OAuth consent screen**: User type **External**; fill in the app name and
   your email. Under **Test users**, add the Google account(s) you'll sign in with.
4. **Create credentials**: APIs & Services → Credentials → **Create Credentials → OAuth
   client ID** → Application type **Desktop app**. Copy the **Client ID** and **Client
   secret**.
5. In the app, open **Settings → Google sign-in setup (advanced)** and paste the Client ID
   and secret, then save. Now click **Sign in with Google (OAuth2)** on your mailbox.

> **Restricted-scope caveat.** Mail Money Tracker uses Gmail's `https://mail.google.com/`
> scope, which Google classifies as a **restricted scope**. An **unverified** app only
> works for accounts you added as **Test users** (up to 100), which is perfectly fine for
> personal / family / small use. Distributing to the general public would require going
> through Google's app verification (and possibly a CASA security assessment).

### Use a Gmail app password

If you'd rather not set up OAuth, use a 16-character Gmail **app password**:

1. Enable **2-Step Verification** on your Google account.
2. Go to **Google Account → Security → 2-Step Verification → App passwords** and generate
   a password (choose "Mail" / "Other").
3. In the app, open **Settings**, set the mailbox's method to **App password**, and paste
   the 16-character password.

App passwords are stored in your local `config.json` (git-ignored). OAuth is recommended
because nothing reusable is stored in plaintext.

### Tracked sources / filters

By default the app can track any email that looks like a transaction (the global
**catch-all** toggle, `track_all_amount_emails`). For precision, define **sources** in
Settings — each source matches on the sender (`from_contains`) and/or the subject
(`subject_contains`), with a match mode (`both` / `from` / `subject` / `either`). You can
also list **ignore senders** to always skip. The bundled defaults include Canara Bank,
PNB and CRED as examples.

---

## How it works

For every candidate email, the parser runs a 4-step pipeline (visible and testable on the
**Parser** page):

1. **Match** — check the sender and subject against your tracked sources (and ignore list)
   to decide whether the email should be considered at all.
2. **Extract the amount** — pull the amount and currency, preferring the figure tied to the
   transaction phrase or a debit/credit verb, and **skipping** "available balance" / "credit
   limit" numbers so they can't masquerade as the transaction.
3. **Detect direction** — classify the email as money **IN** (credited/received/refund…) or
   **OUT** (debited/spent/withdrawn…) from its keywords.
4. **Identify merchant & categorise** — extract the merchant (UPI VPA, "at/to/for …",
   narration fields, etc.), the card identifier and the bank, then auto-guess a category
   (with merchant memory overriding the guess once you've tagged a payee).

Emails are fetched read-only and cached locally, so re-scans and re-tagging don't hit Gmail
again. A background poller checks for new mail on an interval and can even split a forwarded
"email within an email" that carries its own transaction.

---

## Privacy & Security

- **Everything is local.** The app only makes **read-only** IMAP connections to Gmail
  (`imap.gmail.com`, `readonly=True`). It never sends your data anywhere.
- **Your secrets never leave the machine.** `config.json` (settings + any app password),
  `tokens.json` (OAuth refresh/access tokens), `data.db` (your transactions) and `cache.db`
  (email cache) all stay on disk and are **git-ignored** — they are never committed or
  uploaded.
- **No password storage with OAuth.** The Google flow uses PKCE and a loopback redirect;
  only a refresh token is stored, and `tokens.json` is written with restrictive permissions
  where the OS allows.
- **Read-only by design.** The app cannot send, delete or modify your email.

---

## Ship your own Google client

If you're the maintainer cutting releases and want your users to "Sign in with Google" with
**zero setup**, bundle a Google **Desktop app** OAuth client. The client is resolved in this
order (first non-empty wins), per `oauth.py`:

1. A per-mailbox override (set in Settings on the mailbox itself).
2. `config.json` → `"oauth": { "google_client_id", "google_client_secret" }`.
3. Environment variables `MMT_GOOGLE_CLIENT_ID` / `MMT_GOOGLE_CLIENT_SECRET`.
4. The constants in [`oauth_defaults.py`](oauth_defaults.py).

The **recommended** approach is to inject the client at **build time** via the `MMT_*`
environment variables — store them as GitHub repo secrets and have the release workflow read
them, so no secret is committed to the repository. (For a Desktop-app client Google does not
treat the secret as confidential, but keeping it out of a public repo is still best practice.)
Leave both blank to require each user to paste their own client in Settings.

---

## Building releases

Packaged builds are produced by the project's CI (GitHub Actions release workflow) and
published to the [Releases](https://github.com/OWNER/REPO/releases) page. If you're setting
up your own fork's build pipeline — including how the `MMT_*` OAuth secrets are wired in —
see [CONTRIBUTING.md](CONTRIBUTING.md).

---

## Project layout

| Path | What it is |
|------|------------|
| `app.py` | Entry point — window, sidebar, pages (Overview, Review, Transactions, Scan mailbox, Parser, Settings), dialogs, tray notifications. |
| `oauth.py` | Pure-stdlib Google OAuth2 "installed app" loopback flow with PKCE; XOAUTH2 for IMAP. |
| `oauth_defaults.py` | Optional bundled Google client (reads the `MMT_*` env vars). |
| `mailreader.py` | IMAP login (XOAUTH2 or app password), fetching, and the transaction parser. |
| `categorize.py` | Category list, auto-categorisation, and credit-card-bill detection. |
| `notify.py` | Desktop notifications (`windows-toasts` → `winotify` → `plyer` → console). |
| `config.py` / `config.example.json` | Config loading and the shipped template. |
| `requirements.txt` | Python dependencies (with per-platform markers). |
| `run_pyqt.bat` / `start_pyqt_hidden.vbs` | Windows launchers. |
| `docs/screenshots/` | Screenshots used in this README. |

Local data files — `config.json`, `tokens.json`, `data.db`, `cache.db` — are created at
runtime and git-ignored.

---

## License

Mail Money Tracker is released under the **GNU General Public License v3.0** — see
[LICENSE](LICENSE). It bundles PyQt5, which is itself GPL-licensed.

---

## Contributing

Contributions are welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) for how to set up
a dev environment, run the app from source, and build releases.

---

## Disclaimer

Mail Money Tracker is an independent project and is **not affiliated with, endorsed by, or
sponsored by Google or any bank**. It reads transaction-alert emails on a best-effort basis;
parsing may be imperfect, so always verify against your official bank statements. This
software does **not** provide financial advice.
