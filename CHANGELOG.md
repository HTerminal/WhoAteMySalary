# Changelog

All notable changes to this project are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

## [1.1.0]
### Added
- **Sign in with Google (OAuth2)** — a browser-based login that stores no
  password. Implemented as a pure-stdlib Google "installed app" loopback flow
  with PKCE; tokens are cached locally in `tokens.json` (git-ignored) and used
  for IMAP via XOAUTH2.
- **Sign in with Microsoft / Outlook (OAuth2)** — the same browser-based flow
  for Outlook.com / Hotmail / Office 365 mailboxes, using a public (native)
  Azure client (PKCE, no secret), the `IMAP.AccessAsUser.All` scope, and
  `outlook.office365.com` for IMAP. App-password sign-in stays Gmail-only.
- **Bundled OAuth client option** — maintainers can ship a default Google
  "Desktop app" client and/or a Microsoft public client by setting
  `MMT_GOOGLE_CLIENT_ID` / `MMT_GOOGLE_CLIENT_SECRET` and
  `MMT_MICROSOFT_CLIENT_ID` at build time (the release workflow reads these
  from repo secrets) or by editing `oauth_defaults.py`. Users without a bundled
  client can paste their own in Settings → "Google / Microsoft sign-in setup
  (advanced)".
- Documentation overhaul: rewritten README with setup and Google Cloud OAuth
  walkthrough, plus app screenshots under `docs/screenshots/`.
- **Release CI** — GitHub Actions workflow builds one-folder PyInstaller apps
  for Windows, macOS, and Linux on tagged releases and publishes them as a
  GitHub Release, with a lightweight `py_compile` CI gate on every push/PR.

### Changed
- Corrected the sign-in description: the app supports **Google (OAuth2)** and a
  **Gmail app password** (the earlier "Microsoft (OAuth2)" wording was
  inaccurate and has been removed).

## [1.0.0]
### Added
- First public release of **Mail Money Tracker** (PyQt5 desktop app).
- Reads bank/transaction-alert emails over IMAP and turns them into transactions.
- Dashboard: KPIs (money out / credit-card bills / money in / net / count), an
  interactive donut, month-by-month bars, incoming-by-source, an expandable
  merchant tree, and highlighted large transactions.
- Global search + clickable KPI cards → searchable, sortable transaction lists.
- Review queue: every new transaction appears for you to verify, with a
  pre-filled category and a desktop notification.
- Merchant memory: remembers the category you chose for a payee.
- Credit-card bill payments tracked in their own bucket (not double-counted).
- Native calendar date-range with today highlighted; date + time on every row.
- Sign in with a **Gmail app password** (Google OAuth2 sign-in arrives in 1.1.0).
- Parser page with a live tester and custom rules.
- Robust background checker (auto-retry, never dies).
