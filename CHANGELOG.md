# Changelog

All notable changes to this project are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

## [1.5.0] - 2026-08-09
### Added
- **Order-receipt parsing** (Zomato-style confirmations): the parser now
  understands receipt wording — "Total paid - ₹281.13", "Grand Total",
  "Payment Summary", "Thanks for ordering" — preferring the receipt's final
  total over the first item price, and extracts the restaurant/shop from
  "order from X" / "meal from X" phrasing. Bank-alert parsing is unchanged
  (regression-checked against 2,167 real alerts).
- **Receipt sources + cross-source duplicate guard**: a tracked source can be
  marked "Receipt source" (Settings → Tracked sources). Transactions imported
  from such a source are auto-ignored (visible in the log, excluded from
  totals, re-taggable) when another source already recorded the same payment —
  same direction and amount within a day — so an order receipt doesn't
  double-count the card alert for the very same payment. Scan and live-check
  logs report these as "duplicate — auto-ignored".

## [1.4.0] - 2026-08-09
### Added
- **"Category habits" panel on the Overview** (replaces the month-by-month
  chart next to the donut): one row per spending category showing how many
  times it was used in the selected period, its average uses per month, and
  its quietest / busiest month by transaction count — e.g. Fuel: 9×, ~2.2/month,
  quietest Aug 26 (1×), busiest Jun 26 (3×). Rows are colour-matched to the
  donut, sortable, and double-click opens that category's transactions. For
  "All time" the averages start at the first transaction, and single-month
  ranges show "—" for quietest/busiest.
- **Analytics view in every transaction drill-in** (category, KPI-card and
  search dialogs): a 📊 Analytics button swaps the list for spending-rhythm
  insights — total / count / average, **how often** you spend there (average
  gap between purchase days), active days, extrapolated monthly pace, busiest
  weekday, biggest transaction and top merchant, plus a spending-over-time
  chart (day/week/month buckets picked from the range), a by-day-of-week chart
  and a top-merchants chart (new `TimeBars` widget in `charts.py`). The search
  box keeps filtering the analytics live; money-in lists analyse the incoming
  side. **Clicking a bar** on the timeline or weekday chart pops up a small
  frameless card next to the pointer with exactly that day/week/month's (or
  weekday's) transactions: one payment shows its full details, several show
  the bucket total plus a scrollable mini-list. ✕ or Esc dismisses it, and it
  can be dragged around.
- **"This month" period preset** on the Overview — filters from the 1st of the
  current month through today, next to the other quick ranges.

### Fixed
- **The UI now adapts to the screen resolution and window size.** The Overview
  toolbars (period presets, bank/card/filter scope) wrap onto extra rows instead
  of getting cut off at the right edge on smaller displays; the KPI cards wrap
  and the donut/month charts stack vertically when the window is narrow (via a
  new `FlowLayout` in `app.py`). The main window now sizes itself to the
  screen's available geometry instead of a fixed 1240×820 (minimum lowered from
  1080×700), long Settings help texts word-wrap, and pages fall back to a
  horizontal scrollbar rather than clipping content that still can't fit.

## [1.3.0] - 2026-07-22
### Added
- **Graph-based PDF export** — the statement export can render a PDF report
  with the dashboard's charts. (Released without changelog notes; recorded
  here retroactively.)

## [1.2.0] - 2026-07-14
### Added
- **Startup splash screen** — on launch the app now shows a proper loading card
  (the bitten-₹ logo, the app name, a status line and an indeterminate progress
  bar) while the database, config and migrations initialise, so it never looks
  frozen on a cold start. Rendered by `Splash` in `app.py`; reproducible via
  `tools/make_icon.py` + `tools/gen_screenshots.py`.

## [1.1.0] - 2026-07-14
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
- **The Money Goblin** — a mascot that announces new transactions and nags you
  (charmingly) to categorise them, in notifications and on the Review page
  (`goblin.py`).
- An **app icon** (a bitten ₹ coin — your salary, getting eaten) used for the
  window, tray, taskbar and packaged builds, plus a generator
  (`tools/make_icon.py`).
- **Log expenses by voice** — an Apple Shortcut + Siri recipe that emails
  yourself a bank-style alert the app then tracks (`docs/APPLE_SHORTCUT.md`).
- Documentation overhaul: rewritten README (with a value-proposition section:
  free, one Gmail, your data stays local, track it your way), a Google Cloud /
  Azure OAuth walkthrough, a hero icon, and app screenshots under
  `docs/screenshots/`.
- **Release CI** — GitHub Actions workflow builds one-folder PyInstaller apps
  for Windows, macOS, and Linux on tagged releases and publishes them as a
  GitHub Release, with a lightweight `py_compile` CI gate on every push/PR.

### Changed
- **Renamed the project to WhoAteMySalary** (window title, notifications /
  AppUserModelID, PyInstaller spec, docs, and the repo name).
- Sign-in methods are now labelled by test status: the **Gmail app password** is
  tested and working; **Google** and **Microsoft** OAuth2 are implemented but not
  yet verified end-to-end.

## [1.0.0]
### Added
- First public release of **WhoAteMySalary** (PyQt5 desktop app).
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
