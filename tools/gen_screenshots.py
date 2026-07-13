# -*- coding: utf-8 -*-
"""Regenerate the README screenshots from *fabricated demo data*.

Runs the real PyQt UI headless (offscreen), seeds a throwaway temp database with
made-up transactions and a demo mailbox, and saves PNGs to docs/screenshots/.
No real account, email, password or transaction is ever touched or shown.

    py -3.12 tools/gen_screenshots.py

Safe to run anytime; it never writes to your real data.db / config.json /
tokens.json (all are redirected to a temp folder for the run)."""
import os, sys, json, tempfile
from datetime import datetime, timedelta

# NOTE: we deliberately use the REAL platform (not QT_QPA_PLATFORM=offscreen) so
# text renders with the system font engine, then keep the window off-screen with
# WA_DontShowOnScreen — it paints into its backing store but never appears.
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

# ---- redirect ALL data to a throwaway temp folder (protects real files) ----
tmp = tempfile.mkdtemp(prefix="mmt_shots_")
import config, db, cache, oauth
config.CONFIG_PATH = os.path.join(tmp, "config.json")
db.DB_PATH = os.path.join(tmp, "data.db")
cache.CACHE_PATH = os.path.join(tmp, "cache.db")
oauth.TOKENS_PATH = os.path.join(tmp, "tokens.json")

# a demo mailbox (one Google, one app-password) + a fake token so Settings shows
# a "connected" state — all obviously not-real placeholders.
DEMO_CFG = {
    "poll_interval_seconds": 60, "backfill_days": 3, "notifications": True,
    "animations": True, "track_all_amount_emails": False,
    "accounts": [
        {"label": "Personal", "email": "you@example.com", "auth": "oauth", "folder": "INBOX"},
        {"label": "Cards", "email": "you.cards@example.com", "auth": "app_password",
         "app_password": "xxxxxxxxxxxxxxxx", "folder": "INBOX"},
    ],
    "sources": [
        {"name": "Bank alerts", "from_contains": "alerts@examplebank.com",
         "subject_contains": "Transaction Alert", "match": "both", "primary": "from"},
        {"name": "Card alerts", "from_contains": "cards@examplebank.com",
         "subject_contains": "", "match": "from", "primary": "from"},
    ],
    "ignore_senders": ["noreply@google.com"],
    "custom_categories": ["Car Repairs", "Gym"],
    "oauth": {"google_client_id": "", "google_client_secret": ""},
}
with open(config.CONFIG_PATH, "w", encoding="utf-8") as f:
    json.dump(DEMO_CFG, f)
with open(oauth.TOKENS_PATH, "w", encoding="utf-8") as f:              # fake "connected"
    json.dump({"you@example.com": {"provider": "google", "refresh_token": "DEMO",
                                   "access_token": "DEMO", "expiry": 9e9,
                                   "client_id": "demo"}}, f)

db.init(); cache.init()

# ---- fabricate a realistic-looking spread of transactions ----
BASE = datetime(2026, 7, 12, 19, 30)      # fixed so runs are deterministic
def edate(days_ago, hh=13, mm=20):
    d = (BASE - timedelta(days=days_ago)).replace(hour=hh, minute=mm)
    return d.strftime("%a, %d %b %Y %H:%M:%S +0530")

# (days_ago, merchant, amount, direction, category, bank, status)
DEMO = [
    (0,  "Blue Bottle Coffee",   380,  "OUT", "Food & dining",   "ExampleBank", "pending"),
    (0,  "Blinkit",              1703, "OUT", "Groceries",       "ExampleBank", "pending"),
    (1,  "Zomato",               524,  "OUT", "Food delivery",   "ExampleBank", "pending"),
    (1,  "Apollo Pharmacy",      642,  "OUT", "Pharmacy",        "ExampleBank", "pending"),
    (2,  "Uber",                 289,  "OUT", "Taxi",            "ExampleBank", "tagged"),
    (2,  "Netflix",              649,  "OUT", "Entertainment",   "Cards",       "tagged"),
    (3,  "Whole Foods Market",   3120, "OUT", "Groceries",       "ExampleBank", "tagged"),
    (4,  "Shell Fuel Station",   2400, "OUT", "Fuel",            "Cards",       "tagged"),
    (5,  "Amazon",               1899, "OUT", "Shopping",        "Cards",       "tagged"),
    (6,  "Swiggy",               438,  "OUT", "Food delivery",   "ExampleBank", "tagged"),
    (7,  "Jio Recharge",         799,  "OUT", "Internet & mobile","ExampleBank","tagged"),
    (8,  "BESCOM Electricity",   1560, "OUT", "Utilities",       "ExampleBank", "tagged"),
    (9,  "Acme Corp Payroll",    185000,"IN", "Salary",          "ExampleBank", "tagged"),
    (10, "Starbucks",            510,  "OUT", "Food & dining",   "Cards",       "tagged"),
    (12, "IKEA",                 8650, "OUT", "Furniture",       "Cards",       "tagged"),
    (13, "Ola Cabs",             332,  "OUT", "Taxi",            "ExampleBank", "tagged"),
    (15, "Amazon",               2450, "OUT", "Shopping",        "Cards",       "tagged"),
    (16, "BigBasket",            2210, "OUT", "Groceries",       "ExampleBank", "tagged"),
    (18, "PVR Cinemas",          960,  "OUT", "Entertainment",   "Cards",       "tagged"),
    (20, "Refund - Amazon",      1899, "IN",  "Refund",          "Cards",       "tagged"),
    (22, "CRED Visa bill",       24500,"OUT", "Credit Card bill payment", "CRED","tagged"),
    (24, "Spotify",              119,  "OUT", "Entertainment",   "Cards",       "tagged"),
    (26, "Dominos",              720,  "OUT", "Food delivery",   "ExampleBank", "tagged"),
    (30, "Whole Foods Market",   2780, "OUT", "Groceries",       "ExampleBank", "tagged"),
    (34, "Shell Fuel Station",   2100, "OUT", "Fuel",            "Cards",       "tagged"),
    (39, "Acme Corp Payroll",    185000,"IN", "Salary",          "ExampleBank", "tagged"),
    (44, "Uber",                 415,  "OUT", "Taxi",            "ExampleBank", "tagged"),
    (49, "Apollo Pharmacy",      1230, "OUT", "Pharmacy",        "ExampleBank", "tagged"),
    (55, "Amazon",               3299, "OUT", "Shopping",        "Cards",       "tagged"),
    (61, "BESCOM Electricity",   1490, "OUT", "Utilities",       "ExampleBank", "tagged"),
]
for i, (dago, merch, amt, dirn, cat, bank, status) in enumerate(DEMO):
    t = {"account": bank if bank != "CRED" else "Cards", "uid": 10000 + i, "seq": 0,
         "amount": float(amt), "direction": dirn, "merchant": merch, "bank": bank,
         "subject": f"Transaction Alert: {merch}", "from_addr": "alerts@examplebank.com",
         "email_date": edate(dago), "guessed_category": cat, "source": "Bank alerts"}
    rid = db.add_txn(t, status=("pending" if status == "pending" else "tagged"))
    if rid and status == "tagged":
        db.tag(rid, cat, "", "tagged")

# ---- render ----
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt, QEventLoop, QTimer
import theme as T
import charts
import app as A

charts.ANIM = False                       # capture charts at their final frame
qapp = QApplication(sys.argv)
qapp.setStyle("Fusion")
qapp.setStyleSheet(T.QSS.replace("__CARET__", A._make_caret()))

win = A.MainWindow()
win.poller.stop()                         # never hit the network
win.setAttribute(Qt.WA_DontShowOnScreen, True)   # render, but never appear on screen
win.resize(1440, 900)
# widen the default view so the dashboard shows the whole demo span
win.rng_from = (BASE - timedelta(days=70)).strftime("%Y-%m-%d")
win.rng_to = BASE.strftime("%Y-%m-%d")
win.show()                                # required for widgets to size + paint

OUT = os.path.join(ROOT, "docs", "screenshots")
os.makedirs(OUT, exist_ok=True)

def settle(ms=350):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec_()

def snap(page, name):
    win.show_page(page)
    settle()
    win.repaint()
    settle(120)
    path = os.path.join(OUT, name)
    win.grab().save(path)
    print("saved", os.path.relpath(path, ROOT))

settle(400)                               # let the first page lay out
win.set_status("live")                    # show a tidy "Live" pill (poller is stopped)

snap("Overview", "overview.png")
snap("Inbox", "review.png")
snap("Transactions", "transactions.png")
snap("Parser", "parser.png")
snap("Settings", "settings.png")

win.poller.wait(1500)
print("done ->", OUT)
