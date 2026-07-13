# -*- coding: utf-8 -*-
"""Load / save config.json (accounts, tracked sources, settings)."""
import json, os, threading

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "config.json")
_lock = threading.RLock()   # reentrant: load() may call save() while holding it

DEFAULT = {
    "poll_interval_seconds": 60,           # auto-check for new transactions every minute
    "backfill_days": 3,
    "track_all_amount_emails": True,
    "notifications": True,
    "web_port": 5000,
    "accounts": [],
    "sources": [
        {"name": "Canara Bank", "from_contains": "canarabank", "subject_contains": "", "match": "from", "primary": "from"},
        {"name": "PNB",         "from_contains": "pnb",         "subject_contains": "", "match": "from", "primary": "from"},
        {"name": "CRED",        "from_contains": "cred.club",   "subject_contains": "", "match": "from", "primary": "from"},
    ],
    "ignore_senders": ["noreply@google.com", "no-reply@accounts.google.com"],
}


def load():
    with _lock:
        if not os.path.exists(CONFIG_PATH):
            save(DEFAULT)
            return json.loads(json.dumps(DEFAULT))
        with open(CONFIG_PATH, encoding="utf-8") as f:
            cfg = json.load(f)
    # backfill any missing keys
    for k, v in DEFAULT.items():
        cfg.setdefault(k, v)
    return cfg


def save(cfg):
    with _lock:
        tmp = CONFIG_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
        os.replace(tmp, CONFIG_PATH)
