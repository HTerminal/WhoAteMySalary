# Contributing to WhoAteMySalary

Thanks for taking the time to contribute! WhoAteMySalary is a small, native
**PyQt5 desktop app** that reads bank/transaction-alert emails over Gmail IMAP,
detects and categorises transactions, sends Windows desktop notifications, and
helps you analyse your spending. Everything runs and stays **on your own
machine** — the app only makes read-only IMAP connections to Gmail and never
uploads anything anywhere.

The project is intentionally **close to the standard library plus PyQt5**. That
constraint is a feature: it keeps the app easy to build, audit, and package.
Please keep it that way (see [Coding style](#coding-style)).

> Replace `OWNER/REPO` throughout with the real GitHub path once the repo is
> published. The suggested repository name is **`who-ate-my-salary`**.

---

## Table of contents

- [Getting set up](#getting-set-up)
- [Running the app](#running-the-app)
- [Project layout](#project-layout)
- [Common contributions](#common-contributions)
  - [Add support for a new bank](#add-support-for-a-new-bank)
  - [Add a spending / income category](#add-a-spending--income-category)
  - [Regenerate the README screenshots](#regenerate-the-readme-screenshots)
- [Coding style](#coding-style)
- [Never commit personal data](#never-commit-personal-data)
- [Commits & the changelog](#commits--the-changelog)
- [Pull requests](#pull-requests)
- [Cutting a release](#cutting-a-release)

---

## Getting set up

You need **Python 3.12** and **git**. PyQt5 currently has no wheels for Python
3.13+/3.15-alpha, so 3.12 is the supported line — please develop and test on it.

```bash
# 1. Clone
git clone https://github.com/OWNER/REPO.git
cd REPO

# 2. (Recommended) create a virtual environment
py -3.12 -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux

# 3. Install dependencies
pip install -r requirements.txt

# 4. Create your local config from the template
copy config.example.json config.json      # Windows
# cp config.example.json config.json       # macOS / Linux
```

`requirements.txt` is deliberately tiny: `PyQt5` on every platform, plus
notification helpers (`windows-toasts`, `winotify`, `pywin32` on Windows;
`plyer` elsewhere) that all fail gracefully if missing.

`config.json`, `tokens.json`, and the `*.db` files are **git-ignored** — they
hold your personal data and must never be committed. See
[Never commit personal data](#never-commit-personal-data).

---

## Running the app

```bash
py -3.12 app.py
```

On Windows you can also use the bundled launchers:

- `run_pyqt.bat` — run with a console window (handy while developing).
- `start_pyqt_hidden.vbs` — start silently to the system tray.

The app has six pages: **Overview**, **Review**, **Transactions**, **Scan
mailbox**, **Parser**, and **Settings**.

### Signing in

There are three supported sign-in methods; you only need one:

1. **Sign in with Google (OAuth2)** — browser-based, no password stored. Tokens
   land in the git-ignored `tokens.json`. Needs a free Google Cloud OAuth
   **Desktop app** client (see the README). Gmail's `https://mail.google.com/`
   is a *restricted* scope: an unverified client only works for accounts you add
   as **Test users** (up to 100), which is plenty for personal/family use.
2. **Sign in with Microsoft / Outlook (OAuth2)** — same browser flow for
   Outlook/Hotmail/Office365 (`outlook.office365.com`, scope
   `IMAP.AccessAsUser.All`). Needs a free Azure **public client** — register an
   app with redirect `http://localhost` under "Mobile and desktop applications"
   (client ID only, no secret). See the README.
3. **App password** — a 16-character **Gmail** app password (Google Account →
   Security → 2-Step Verification → App passwords). Microsoft has disabled app
   passwords for most accounts, so use OAuth for Outlook.

For manual testing, the **Parser** page lets you paste an email and see exactly
what the engine extracts — no live mailbox required.

---

## Project layout

Each module is small and single-purpose. Start with `app.py` to see how the UI
wires the rest together.

| Module | What it does |
| --- | --- |
| `app.py` | The whole PyQt5 UI: main window, sidebar navigation, and all six pages (Overview, Review, Transactions, Scan, Parser, Settings). The entry point (`py -3.12 app.py`). |
| `engine.py` | The data layer — pure DB/analysis operations with **no Qt**. Builds the dashboard model, filters transactions, tags & "learns" merchant→category, manages custom categories, and the one-time credit-card-bill reclassification. |
| `workers.py` | Background `QThread` workers: `PollerWorker` (auto-checks mailboxes on an interval, auto-retries, never dies), `ScanWorker` (scans a date range), and `OAuthWorker` (runs the interactive Google sign-in off the UI thread). They only touch DB/IMAP and report back via Qt signals. |
| `mailreader.py` | The IMAP + parsing core. Logs in (XOAUTH2 or app password), fetches mail, and turns a message into a transaction: amount, direction (IN/OUT), merchant, card, bank. Home of `MERCHANT_PATTERNS`, the IN/OUT keyword lists, and the source-matching rules. |
| `oauth.py` | Pure-stdlib **Google and Microsoft** "installed app" OAuth2 flow (loopback redirect + PKCE, XOAUTH2 for IMAP). Provider table in `PROVIDERS` (endpoints, scope, IMAP host). Stores/refreshes tokens in `tokens.json`. |
| `oauth_defaults.py` | Optional place for a maintainer to ship default Google/Microsoft OAuth clients. Left blank by default; usually populated at build time from `MMT_GOOGLE_CLIENT_ID` / `MMT_GOOGLE_CLIENT_SECRET` / `MMT_MICROSOFT_CLIENT_ID`. |
| `db.py` | SQLite storage (`data.db`) for detected transactions, per-account UID cursor, scanned-UID bookkeeping, and merchant memory. WAL + autocommit for safe concurrency. |
| `cache.py` | A separate hidden email cache (`cache.db`) storing fetched sender/subject/body so later scans read from disk instead of re-downloading from Gmail. Purely a speed layer; never shown in the UI. |
| `categorize.py` | The category list (`EXPENSE_CATEGORIES`, `INCOME_CATEGORIES`) and `guess_category()` — the keyword rules that auto-guess a category from merchant + subject. Also the credit-card-bill detection. |
| `charts.py` | Custom `QPainter` chart widgets — the animated donut, month bars, income bars, and count-up KPI cards. |
| `theme.py` | The dark Qt stylesheet, colour palette (`PAL`), and number/colour formatting helpers. |
| `config.py` | Loads/saves `config.json` (accounts, tracked sources, preferences) atomically, with default backfill for missing keys. |
| `notify.py` | Windows desktop notifications: `windows-toasts` (WinRT) → `winotify` → `plyer` → console. Registers an AppUserModelID so toasts are attributed to the app and persist in the Action Center. |

Supporting files: `config.example.json` (shipped template), `requirements.txt`,
`CHANGELOG.md`, `LICENSE` (GPLv3), the Windows launchers, and
`tools/gen_screenshots.py` (see below).

---

## Common contributions

### Add support for a new bank

Most banks send transaction alerts in the same broad shape, so the engine often
works with **zero code** — you just tell it which emails to watch:

1. **Add a tracked source.** In **Settings**, add a source with a
   `from_contains` (e.g. the bank's alert address) and/or a `subject_contains`,
   and choose a match mode (`from`, `subject`, `both`, `either`). This is the
   preferred, no-code path and mirrors the `sources` array in `config.json`.
2. **If the merchant/amount is parsed wrongly**, the fix usually belongs in
   `mailreader.py`:
   - Add a regex to `MERCHANT_PATTERNS` to pull the payee out of that bank's
     narration format. Patterns are tried in order and the first non-boilerplate
     capture wins; keep them anchored (e.g. `\bat\s+…`, `\bfor\s+…\s+on\s+\d`) so
     they don't grab dates, times, or limit figures.
   - If the bank uses an unusual debit/credit verb, extend `OUT_KW` / `IN_KW`.
   - If it names the amount without a currency symbol, `_VERB_NOCUR_RE` already
     handles the common "Debited with 1800.00" style — check whether it matches
     before adding a new rule.
   - Add the bank's short name to the `BANKS` map so rows are tagged with it.
3. **Test it on the Parser page.** Paste a real (redacted) alert into the
   Parser's tester and confirm the extracted amount, direction, merchant, card,
   and matched source are correct. `parse_debug()` even reports *which* rule
   fired, which makes tuning fast.

End users can also add their own parsing rules without editing code, via
`config.json`'s `custom` block (`merchant_patterns`, `out_keywords`,
`in_keywords`) — see `mailreader.apply_custom()`. Prefer built-in patterns for
banks that many users will have; use the custom block for one-off local formats.

### Add a spending / income category

Categories live in `categorize.py`:

1. Add the display name to `EXPENSE_CATEGORIES` (money **out**) or
   `INCOME_CATEGORIES` (money **in**). Keep it India-friendly and consistent
   with the existing naming.
2. If you want it auto-guessed, add a keyword branch in `guess_category()` — the
   uppercase keyword checks run against `merchant + subject`. Order matters:
   more specific rules go before broad catch-alls.
3. Credit-card **bill payments** are special: they are neither income nor spend
   and live in their own bucket so purchases aren't double-counted. Don't route
   a bill-payment merchant into a spending category — extend `is_cc_bill_payment()`
   instead if detection needs improving.

Users can also add their own categories at runtime (stored in
`config['custom_categories']`); those don't need a code change.

### Regenerate the README screenshots

The screenshots in `docs/screenshots/` are produced from **fabricated demo
data** — never from real accounts. To regenerate them:

```bash
py -3.12 tools/gen_screenshots.py
```

The tool runs the real UI off-screen, seeds a **throwaway temp database** with
made-up transactions and a `you@example.com` demo mailbox, and writes the PNGs.
It redirects `config.json`, `data.db`, `cache.db`, and `tokens.json` to a temp
folder for the run, so **your real data is never touched**. Reference the images
from Markdown with relative paths, e.g. `docs/screenshots/overview.png` (the
hero image).

---

## Coding style

- **Match the existing style.** It's terse, well-commented, and pragmatic:
  short helper functions, module-level docstrings explaining *why*, and inline
  comments where a regex or a subtle invariant needs it.
- **No new heavy dependencies.** The app is intentionally standard library +
  PyQt5 (plus the optional, gracefully-degrading notification backends). If you
  think you need another package, open an issue first and explain why — the bar
  is high.
- **Keep Qt out of the core.** `engine.py`, `mailreader.py`, `db.py`,
  `cache.py`, `categorize.py`, and `oauth.py` have no PyQt imports. Preserve
  that separation so the parsing/data logic stays testable and reusable.
- **Fail soft on I/O.** Network, cache, and notification code wrap failures so a
  transient error never crashes the poller or the UI. Follow the same pattern.
- **Read-only IMAP.** The app opens mailboxes `readonly=True` and never modifies
  or deletes mail. Don't change that.

---

## Never commit personal data

This is the most important rule in the project. The following are **git-ignored**
and must never be committed:

- `config.json` — your mailboxes, filters, and any pasted OAuth client
- `tokens.json` — your Google refresh/access tokens
- `data.db`, `cache.db` (and their `-wal` / `-shm` siblings) — your transactions
  and cached email bodies
- `transactions_export.csv`, `*.bak`

Before every commit, **double-check**:

```bash
git status
git diff --cached --name-only
```

If you see any of the files above staged, unstage them
(`git restore --staged <file>`) and stop. Never put a real email address,
password, app password, token, or client secret in code, tests, commit messages,
config examples, or screenshots. Use obvious fakes like `you@example.com`.

---

## Commits & the changelog

- Write clear, imperative commit subjects: `Add UPI VPA merchant pattern`, not
  `fixed stuff`. Keep the subject under ~72 chars; add a body explaining the
  *why* when it isn't obvious.
- Group related changes into a single logical commit; avoid mixing an unrelated
  refactor into a feature commit.
- **Update `CHANGELOG.md`.** The project follows
  [Keep a Changelog](https://keepachangelog.com/). Put user-visible changes
  under the `## [Unreleased]` heading, in an `### Added` / `### Changed` /
  `### Fixed` / `### Removed` subsection — for example:

  ```markdown
  ## [Unreleased]
  ### Added
  - Merchant pattern for XYZ Bank UPI alerts.
  ```

  Internal-only refactors that users won't notice don't need an entry.

---

## Pull requests

1. **Branch** off the default branch: `git checkout -b feat/xyz-bank-parser`.
2. Make your change, keeping it focused and matching the existing style.
3. **Test manually.** Run `py -3.12 app.py`, exercise the affected page, and use
   the **Parser** page to verify any parsing change against a redacted sample.
4. Update `CHANGELOG.md` under `[Unreleased]` if the change is user-visible.
5. Run `git status` and confirm **no personal data files** are staged.
6. Open a PR against `OWNER/REPO`. Describe *what* changed and *why*, list how
   you tested it, and attach a screenshot for UI changes (use demo data only).
7. Be responsive to review. Small, well-scoped PRs merge fastest.

By contributing you agree that your contributions are licensed under the
project's **GPLv3** license (see `LICENSE`).

---

## Cutting a release

Releases are cut by a maintainer:

1. Move the `[Unreleased]` items in `CHANGELOG.md` under a new
   `## [X.Y.Z]` heading (Keep a Changelog format) and leave a fresh empty
   `[Unreleased]` section on top.
2. Commit that, then tag it:

   ```bash
   git tag vX.Y.Z
   git push origin main --tags
   ```

3. Pushing the tag triggers the release workflow, which builds the
   Windows / macOS / Linux artifacts and attaches them to the GitHub Release.
   The workflow injects the bundled Google OAuth client at build time by reading
   `MMT_GOOGLE_CLIENT_ID` / `MMT_GOOGLE_CLIENT_SECRET` from the repo's GitHub
   **secrets**, so no client ID or secret is ever committed to the repository.

That's it — thanks again for contributing!
