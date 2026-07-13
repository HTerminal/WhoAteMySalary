# -*- coding: utf-8 -*-
"""A separate, hidden email cache (cache.db). Stores the sender/subject/body of
every email we've fetched so later scans read from disk instead of re-downloading
from Gmail. Never shown in the UI — it's purely a speed layer."""
import sqlite3, os, threading, time

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE_PATH = os.path.join(HERE, "cache.db")
_local = threading.local()


_SCHEMA = """
    CREATE TABLE IF NOT EXISTS email_cache(
        account TEXT, uid INTEGER,
        from_addr TEXT, subject TEXT, body TEXT, email_date TEXT,
        cached_at REAL,
        PRIMARY KEY(account, uid)
    );"""


def conn():
    if not hasattr(_local, "c"):
        c = sqlite3.connect(CACHE_PATH, timeout=30, isolation_level=None)  # autocommit
        c.row_factory = sqlite3.Row
        try:
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("PRAGMA busy_timeout=30000")
            c.execute("PRAGMA synchronous=NORMAL")
        except Exception:
            pass
        c.executescript(_SCHEMA)   # ensure schema for every connection/thread
        _local.c = c
    return _local.c


def init():
    conn()


def get(account, uid):
    r = conn().execute(
        "SELECT from_addr, subject, body, email_date FROM email_cache WHERE account=? AND uid=?",
        (account, int(uid))).fetchone()
    return dict(r) if r else None


def put(account, uid, from_addr, subject, body, email_date):
    c = conn()
    c.execute("""INSERT OR REPLACE INTO email_cache
        (account, uid, from_addr, subject, body, email_date, cached_at)
        VALUES(?,?,?,?,?,?,?)""",
        (account, int(uid), from_addr, subject, body, email_date, time.time()))
    c.commit()


def count():
    return conn().execute("SELECT COUNT(*) n FROM email_cache").fetchone()["n"]


def clear():
    c = conn()
    c.execute("DELETE FROM email_cache")
    c.commit()
