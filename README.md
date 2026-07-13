# Mail Money Tracker — PyQt5 Edition

A native **PyQt5 (Qt)** desktop app — the same tool as the tkinter version, but
built on Qt for **smooth, GPU-composited rendering (no jitter)** and native
widgets. Reads your Gmail accounts over IMAP, detects bank/transaction alerts,
notifies you, and lets you categorise + analyse your spending.

Self-contained: its own copy of the core logic and its own data files. It does
**not** touch the web app (`../mail_tracker`) or the tkinter app
(`../mail_tracker_gui`).

## Why Qt (fixes the tkinter pain points)

- **Sorting** — every table uses Qt's native click-to-sort headers (numbers sort
  as numbers, dates chronologically).
- **Date picker** — the From/To fields are native `QDateEdit`s with a real
  drop-down **calendar**.
- **Merchant expand** — the Top-merchants list is a native tree; click ▸ to
  expand a merchant into its transactions.
- **No jitter** — Qt paints on the native compositor; animations use
  `QPropertyAnimation` and are genuinely smooth. They can still be toggled in
  **Settings → Smooth animations**.

## Run it

Requires **Python 3.12** (PyQt5 has no wheels for the 3.15 alpha). Your machine
has 3.12 installed, so:

- Double-click **`run_pyqt.bat`** (installs PyQt5 the first time if needed), or
- **`start_pyqt_hidden.vbs`** for no console, or
- `py -3.12 app.py`

## Screens

| Screen | What it does |
|--------|--------------|
| **Overview** | KPIs, an interactive donut (hover + click a slice to drill in), month bars, incoming-by-source, an **expandable merchant tree**, and highlighted >₹1,000 transactions. Native calendar date-range. |
| **Review** | New transactions arrive here live — pick a category and Save/Skip. |
| **Transactions** | Sortable, searchable table; double-click to tag; export CSV. |
| **Scan mailbox** | Fetch a date range with a live progress bar + log. Fetch-once, or Force. |
| **Parser** | The 4-step logic, a paste-an-email tester, and custom rules. |
| **Settings** | Mailboxes, tracked sources, auto-check interval, notifications, animations, cache. |

## Files

- `app.py` — window, sidebar, pages, dialogs, tray notifications.
- `charts.py` — QPainter chart widgets (donut, bars, KPI cards) + numeric table item.
- `workers.py` — `QThread` poller + range scanner (report via Qt signals).
- `engine.py` — data layer (dashboard aggregation, tagging, recovery).
- `theme.py` — Qt stylesheet, palette, number/colour helpers.
- `db.py`, `cache.py`, `config.py`, `mailreader.py`, `categorize.py` — shared core.
- `data.db`, `cache.db`, `config.json` — this app's own data (seeded from the web app).
