# -*- coding: utf-8 -*-
"""SQLite storage for detected transactions + per-account cursor."""
import sqlite3, os, threading, time, re
from email.utils import parsedate_to_datetime

HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(HERE, "data.db")
_local = threading.local()


def conn():
    if not hasattr(_local, "c"):
        # isolation_level=None => autocommit: each statement commits immediately, so
        # no connection ever holds a write lock between calls (prevents "database is
        # locked" from a lingering transaction). WAL + busy_timeout for concurrency.
        c = sqlite3.connect(DB_PATH, timeout=30, isolation_level=None)
        c.row_factory = sqlite3.Row
        try:
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("PRAGMA busy_timeout=30000")
            c.execute("PRAGMA synchronous=NORMAL")
        except Exception:
            pass
        _local.c = c
    return _local.c


def init():
    c = conn()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS txns(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        account TEXT, uid INTEGER, bank TEXT,
        amount REAL, direction TEXT,
        merchant TEXT, subject TEXT, from_addr TEXT,
        email_date TEXT, tdate TEXT, month TEXT, received_at REAL,
        guessed_category TEXT, category TEXT, note TEXT,
        source TEXT, card TEXT,
        status TEXT DEFAULT 'pending'          -- pending | tagged | ignored
    );
    CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);
    CREATE TABLE IF NOT EXISTS scanned(account TEXT, uid INTEGER, PRIMARY KEY(account, uid));
    -- remembers the category a user chose for a given merchant/payee
    CREATE TABLE IF NOT EXISTS merchant_memory(
        mkey TEXT PRIMARY KEY, category TEXT, updated_at REAL);
    """)
    # migrate older DBs that lack the date columns
    cols = {r["name"] for r in c.execute("PRAGMA table_info(txns)")}
    for col in ("tdate", "month", "source", "card"):
        if col not in cols:
            c.execute(f"ALTER TABLE txns ADD COLUMN {col} TEXT")
    if "seq" not in cols:
        c.execute("ALTER TABLE txns ADD COLUMN seq INTEGER DEFAULT 0")
    # unique per (account, uid, seq) so ONE email can hold multiple transactions
    # (e.g. a forwarded / nested alert). Replaces the old (account, uid) index.
    c.execute("DROP INDEX IF EXISTS ux_txn")
    c.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_txn_seq ON txns(account, uid, seq)")
    c.commit()


def parse_dates(email_date):
    try:
        dt = parsedate_to_datetime(email_date)
        return dt.strftime("%Y-%m-%d"), dt.strftime("%Y-%m")
    except Exception:
        return "", ""


def get_meta(k, default=None):
    r = conn().execute("SELECT v FROM meta WHERE k=?", (k,)).fetchone()
    return r["v"] if r else default


def set_meta(k, v):
    c = conn()
    c.execute("INSERT INTO meta(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
              (k, str(v)))
    c.commit()


def add_txn(t, status="pending", seq=None):
    """Insert a detected txn. Returns row id, or None if duplicate.
    seq distinguishes multiple transactions parsed from the same email."""
    tdate, month = parse_dates(t.get("email_date", ""))
    if seq is None:
        seq = t.get("seq", 0)
    c = conn()
    try:
        cur = c.execute("""INSERT INTO txns
            (account,uid,seq,bank,amount,direction,merchant,subject,from_addr,
             email_date,tdate,month,received_at,guessed_category,category,note,
             source,card,status)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (t["account"], t["uid"], int(seq), t.get("bank",""), t["amount"], t["direction"],
             t.get("merchant",""), t.get("subject",""), t.get("from_addr",""),
             t.get("email_date",""), tdate, month, time.time(),
             t.get("guessed_category",""), t.get("guessed_category",""), "",
             t.get("source",""), t.get("card",""), status))
        c.commit()
        return cur.lastrowid
    except sqlite3.IntegrityError:
        try:
            c.rollback()          # never leave the failed INSERT's transaction open
        except Exception:
            pass
        return None


def pending():
    return conn().execute(
        "SELECT * FROM txns WHERE status='pending' ORDER BY received_at DESC").fetchall()


def recent(limit=100):
    return conn().execute(
        "SELECT * FROM txns ORDER BY tdate DESC, received_at DESC LIMIT ?", (limit,)).fetchall()


def rows_filtered(start=None, end=None):
    """Rows with tdate between start..end (ISO 'YYYY-MM-DD'); non-ignored only."""
    q = "SELECT * FROM txns WHERE status!='ignored'"
    args = []
    if start:
        q += " AND tdate>=? AND tdate!=''"; args.append(start)
    if end:
        q += " AND tdate<=? AND tdate!=''"; args.append(end)
    q += " ORDER BY tdate DESC, amount DESC"
    return conn().execute(q, args).fetchall()


def get(id):
    return conn().execute("SELECT * FROM txns WHERE id=?", (id,)).fetchone()


# --- "fetched once" bookkeeping: remember every email UID we've already read ---
def scanned_uids(account):
    return {r["uid"] for r in
            conn().execute("SELECT uid FROM scanned WHERE account=?", (account,))}


def mark_scanned(account, uid):
    c = conn()
    c.execute("INSERT OR IGNORE INTO scanned(account, uid) VALUES(?,?)", (account, int(uid)))
    c.commit()


def total_txns():
    return conn().execute("SELECT COUNT(*) n FROM txns").fetchone()["n"]


def tag(id, category, note, status="tagged"):
    c = conn()
    c.execute("UPDATE txns SET category=?, note=?, status=? WHERE id=?",
              (category, note, status, id))
    c.commit()


def set_category_many(ids, category):
    """Bulk-categorise many txns (keeps their notes). Returns count updated."""
    ids = [int(i) for i in ids if str(i).strip().isdigit()]
    if not ids:
        return 0
    c = conn()
    c.executemany("UPDATE txns SET category=?, status='tagged' WHERE id=?",
                  [(category, i) for i in ids])
    c.commit()
    return len(ids)


# --------- merchant "memory": remember a payee's category, apply it everywhere ---------
def merch_key(m):
    """Normalise a merchant/payee name so the same person maps to one key."""
    m = re.sub(r'\s*\[[^\]]*\]\s*$', '', (m or "").upper())   # drop "[GBP 0.31]" flag
    return re.sub(r'\s+', ' ', m).strip() or "(UNKNOWN)"


def remember_merchant(mkey, category):
    if not mkey or mkey == "(UNKNOWN)" or not category:
        return
    c = conn()
    c.execute("""INSERT INTO merchant_memory(mkey, category, updated_at) VALUES(?,?,?)
                 ON CONFLICT(mkey) DO UPDATE SET category=excluded.category,
                 updated_at=excluded.updated_at""", (mkey, category, time.time()))
    c.commit()


def recall_merchant(mkey):
    if not mkey or mkey == "(UNKNOWN)":
        return None
    r = conn().execute("SELECT category FROM merchant_memory WHERE mkey=?", (mkey,)).fetchone()
    return r["category"] if r else None


def forget_merchant(mkey):
    c = conn()
    c.execute("DELETE FROM merchant_memory WHERE mkey=?", (mkey,))
    c.commit()


def ids_for_merchant(mkey):
    """All txn ids whose normalised merchant == mkey (across the whole DB)."""
    return [r["id"] for r in conn().execute("SELECT id, merchant FROM txns")
            if merch_key(r["merchant"]) == mkey]


def totals_by_category(status="tagged"):
    return conn().execute("""SELECT category, direction, COUNT(*) n, SUM(amount) total
        FROM txns WHERE status=? GROUP BY category, direction ORDER BY total DESC""",
        (status,)).fetchall()


def counts():
    r = conn().execute("""SELECT
        SUM(status='pending') pend,
        SUM(status='tagged')  tagged,
        SUM(direction='OUT' AND status='tagged') out_n,
        COALESCE(SUM(CASE WHEN direction='OUT' AND status!='ignored' THEN amount END),0) out_sum,
        COALESCE(SUM(CASE WHEN direction='IN'  AND status!='ignored' THEN amount END),0) in_sum
        FROM txns""").fetchone()
    return r
