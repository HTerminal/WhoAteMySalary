# -*- coding: utf-8 -*-
"""Data layer for the PyQt app — pure DB / parsing operations, no Qt.
Reuses the proven core modules (db, cache, config, mailreader, categorize)."""
import calendar, re
from collections import defaultdict

import config, db, cache, mailreader
import theme as T
from categorize import (guess_category, ALL_CATEGORIES,
                        EXPENSE_CATEGORIES, INCOME_CATEGORIES,
                        CC_BILL_CATEGORY, CC_BILL_CATEGORIES, is_cc_bill_payment)


def init():
    db.init()
    cache.init()
    cfg = config.load()
    mailreader.apply_custom(cfg)
    try:
        db.conn().execute("PRAGMA journal_mode=WAL")
    except Exception:
        pass
    # one-time: reclassify existing credit-card bill payments out of income/spend
    if db.get_meta("cc_reclassified_v1") != "1":
        try:
            moved = reclassify_cc_bills()
            db.set_meta("cc_reclassified_v1", "1")
            if moved:
                print(f"[init] reclassified {moved} credit-card bill payment(s).")
        except Exception as e:
            print("[init] cc reclassify skipped:", e)
    # one-time: recover reference numbers for transactions stored before we parsed them
    if db.get_meta("refs_backfilled_v1") != "1":
        try:
            found = backfill_refs()
            db.set_meta("refs_backfilled_v1", "1")
            if found:
                print(f"[init] recovered {found} reference number(s) from cached emails.")
        except Exception as e:
            print("[init] ref backfill skipped:", e)
    return cfg


def backfill_refs():
    """One-time: recover each transaction's bank reference number by re-reading its
    cached email. Only fills blanks, so it's safe to re-run."""
    c = db.conn()
    rows = c.execute("SELECT id, account, uid FROM txns WHERE ref IS NULL OR ref=''").fetchall()
    n = 0
    for r in rows:
        em = cache.get(r["account"], r["uid"])
        if not em:
            continue                       # email no longer cached — nothing to recover
        ref = mailreader._ref(em.get("subject") or "", em.get("body") or "")
        if ref:
            c.execute("UPDATE txns SET ref=? WHERE id=?", (ref, r["id"]))
            n += 1
    c.commit()
    return n


def _d(r):
    return {k: r[k] for k in r.keys()}


def mlabel(ym):
    try:
        y, m = ym.split("-")
        return f"{calendar.month_abbr[int(m)]} {y[2:]}"
    except Exception:
        return ym or "?"


_merch_key = db.merch_key          # canonical normalisation lives in db
card_last4 = db.card_last4


def counts():
    return db.counts()


def total_stored():
    return db.total_txns()


def filter_options():
    """Choices for the dashboard's scope pickers: banks, cards (collapsed to their
    last 4 digits) and sources — a.k.a. "filters". Each card/source carries the bank
    it belongs to so the pickers can narrow one another."""
    banks, sources, cards = {}, {}, {}
    for r in db.scope_rows():
        bank = (r["bank"] or "").strip()
        src = (r["source"] or "").strip()
        n = r["n"]
        if bank:
            banks[bank] = banks.get(bank, 0) + n
        if src:
            s = sources.setdefault(src, {"n": 0, "bank": bank})
            s["n"] += n
            s["bank"] = s["bank"] or bank
        last4 = db.card_last4(r["card"])
        if last4:
            c = cards.setdefault(last4, {"n": 0, "bank": bank, "sources": set()})
            c["n"] += n
            c["bank"] = c["bank"] or bank
            if src:
                c["sources"].add(src)

    def _big_first(d):
        return sorted(d.items(), key=lambda kv: -kv[1]["n"])

    return dict(
        banks=[{"value": b, "n": n} for b, n in sorted(banks.items(), key=lambda kv: -kv[1])],
        cards=[{"value": k, "n": v["n"], "bank": v["bank"], "sources": sorted(v["sources"])}
               for k, v in _big_first(cards)],
        sources=[{"value": s, "n": v["n"], "bank": v["bank"]} for s, v in _big_first(sources)],
    )


def build_dashboard(start=None, end=None, bank=None, card=None, source=None):
    rows = [_d(r) for r in db.rows_filtered(start, end, bank, card, source)]
    spend = defaultdict(float); income = defaultdict(float)
    spend_n = defaultdict(int); income_n = defaultdict(int)
    m_in = defaultdict(float); m_out = defaultdict(float)
    cat_m = defaultdict(lambda: defaultdict(int))   # spend cat -> month -> txn count
    tin = tout = 0.0
    cc_bills = 0.0; cc_n = 0
    large = []
    for r in rows:
        amt = r["amount"]
        m = r["month"] or (r["tdate"][:7] if r["tdate"] else "unknown")
        cat = r["category"] or r["guessed_category"] or "Uncategorised"
        r["_cat"] = cat
        # credit-card bill payments: own bucket, excluded from money-in AND money-out
        if cat in CC_BILL_CATEGORIES:
            cc_bills += amt; cc_n += 1
            continue
        if r["direction"] == "OUT":
            spend[cat] += amt; spend_n[cat] += 1; m_out[m] += amt; tout += amt
            if m and m != "unknown":
                cat_m[cat][m] += 1
            if amt > 1000:
                large.append(r)
        else:
            income[cat] += amt; income_n[cat] += 1; m_in[m] += amt; tin += amt

    months = sorted(k for k in (set(m_in) | set(m_out)) if k and k != "unknown")
    sp = sorted(spend.items(), key=lambda x: -x[1])
    spend_data = [(k, v, T.PAL[i % len(T.PAL)]) for i, (k, v) in enumerate(sp)]
    inc = sorted(income.items(), key=lambda x: -x[1])
    income_data = [(k, v, T.PAL[(i + 2) % len(T.PAL)]) for i, (k, v) in enumerate(inc)]
    mnames = {m: mlabel(m) for m in months}

    mg = {}
    for r in rows:
        k = _merch_key(r["merchant"])
        g = mg.get(k)
        if not g:
            g = mg[k] = {"disp": r["merchant"] or "(unknown)", "n": 0,
                         "out": 0.0, "in": 0.0, "cats": set(), "ids": [], "rows": []}
        g["n"] += 1
        if r["direction"] == "IN":
            g["in"] += r["amount"]
        else:
            g["out"] += r["amount"]
        c = r["category"] or r["guessed_category"]
        if c:
            g["cats"].add(c)
        g["ids"].append(str(r["id"]))
        g["rows"].append(r)
    merchants = sorted(mg.values(), key=lambda g: -(g["out"] + g["in"]))
    for g in merchants:
        g["ids"] = ",".join(g["ids"])
        g["cats"] = ", ".join(sorted(g["cats"]))
        g["total"] = g["out"] + g["in"]

    return dict(
        rows_n=len(rows), tin=tin, tout=tout, net=tin - tout,
        cc_bills=cc_bills, cc_bills_n=cc_n,
        spend=spend_data, income=income_data,
        spend_n=dict(spend_n), income_n=dict(income_n),
        months=months, m_in=dict(m_in), m_out=dict(m_out), mnames=mnames,
        cat_months={c: dict(v) for c, v in cat_m.items()},
        large=sorted(large, key=lambda r: -r["amount"])[:80],
        merchants=merchants, all_rows=rows,
    )


def txns_filtered(start=None, end=None, direction=None, category=None, bucket=None,
                  bank=None, card=None, source=None):
    """Rows in the range, optionally narrowed to one bank / card / source. bucket:
    'in' (money-in, excl. CC bills) | 'out' (money-out, excl. CC bills) |
    'cc' (credit-card bill payments only) | None (use direction/category)."""
    out = []
    for r in db.rows_filtered(start, end, bank, card, source):
        cat = r["category"] or r["guessed_category"] or "Uncategorised"
        is_cc = cat in CC_BILL_CATEGORIES
        if bucket == "cc":
            if not is_cc:
                continue
        elif bucket == "in":
            if is_cc or r["direction"] != "IN":
                continue
        elif bucket == "out":
            if is_cc or r["direction"] != "OUT":
                continue
        else:
            if direction and r["direction"] != direction:
                continue
            if category and cat != category:
                continue
        out.append(_d(r))
    return out


# ----- statement export (dashboard) -----
# (key, label shown in the picker, sort key, reverse)
STATEMENT_SORTS = [
    ("date_asc",     "Date — oldest first",     lambda r: (r.get("tdate") or "", r.get("received_at") or 0), False),
    ("date_desc",    "Date — newest first",     lambda r: (r.get("tdate") or "", r.get("received_at") or 0), True),
    ("amount_desc",  "Amount — largest first",  lambda r: r.get("amount") or 0, True),
    ("amount_asc",   "Amount — smallest first", lambda r: r.get("amount") or 0, False),
    ("merchant",     "Description — A to Z",    lambda r: (r.get("merchant") or "").upper(), False),
    ("category",     "Category — A to Z",       lambda r: (r.get("category") or r.get("guessed_category") or "").upper(), False),
]


def statement(start=None, end=None, bank=None, card=None, source=None, sort="date_asc"):
    """The rows behind an export: the current dashboard scope, in the chosen order,
    each carrying a running balance. Money in adds, money out subtracts — so the
    balance column reads like a bank statement's, accumulated in the order shown."""
    rows = txns_filtered(start, end, bank=bank, card=card, source=source)
    _, _, keyfn, rev = next((s for s in STATEMENT_SORTS if s[0] == sort), STATEMENT_SORTS[0])
    bal = 0.0
    out = []
    for r in sorted(rows, key=keyfn, reverse=rev):
        signed = r["amount"] if r["direction"] == "IN" else -r["amount"]
        bal += signed
        out.append({
            "date": r.get("tdate") or "", "datetime": r.get("email_date") or "",
            "ref": r.get("ref") or "", "description": r.get("merchant") or "(unknown)",
            "category": r.get("category") or r.get("guessed_category") or "",
            "direction": r["direction"], "amount": signed, "balance": bal,
            "bank": r.get("bank") or "", "card": r.get("card") or "", "id": r["id"],
        })
    return out


def reclassify_cc_bills():
    """One-time: move existing credit-card *bill payments* into the CC-bill category
    so they stop being counted as income/spending. Only clear matches are touched."""
    c = db.conn()
    rows = c.execute("SELECT id, merchant, subject, category FROM txns").fetchall()
    n = 0
    for r in rows:
        if (r["category"] or "") in CC_BILL_CATEGORIES:
            continue
        if is_cc_bill_payment(f"{r['merchant'] or ''} {r['subject'] or ''}"):
            c.execute("UPDATE txns SET category=?, guessed_category=?, status='tagged' WHERE id=?",
                      (CC_BILL_CATEGORY, CC_BILL_CATEGORY, r["id"]))
            n += 1
    c.commit()
    return n


def txns_in_category(cat, start=None, end=None, direction=None):
    return txns_filtered(start, end, direction, cat)


def tag(txn_id, category, note="", status="tagged"):
    db.tag(txn_id, category, note, status)


def set_category_many(ids, category):
    return db.set_category_many(ids, category)


def get_txn(txn_id):
    r = db.get(txn_id)
    return _d(r) if r else None


def recall_for_merchant(merchant):
    """The category the user previously chose for this merchant/payee, if any."""
    return db.recall_merchant(db.merch_key(merchant))


def tag_and_learn(txn_id, category, note="", status="tagged", apply_all=True):
    """Tag a transaction, REMEMBER the merchant->category, and (by default) apply
    that category to EVERY transaction of the same merchant across the whole DB.
    So re-categorising a payee updates all their past + future transactions.
    Returns how many transactions were updated."""
    row = db.get(txn_id)
    db.tag(txn_id, category, note, status)
    if not (row and category):
        return 1
    mk = db.merch_key(row["merchant"])
    if not mk or mk == "(UNKNOWN)":
        return 1                       # never blanket-apply for unnamed/unknown payees
    db.remember_merchant(mk, category)
    if not apply_all:
        return 1
    ids = [i for i in db.ids_for_merchant(mk) if i != txn_id]
    return db.set_category_many(ids, category) + 1


def remember_merchant(merchant, category):
    if category:
        db.remember_merchant(db.merch_key(merchant), category)


def forget_merchant(merchant):
    db.forget_merchant(db.merch_key(merchant))


# ----- custom user categories (config['custom_categories']) -----
def custom_categories():
    return list(config.load().get("custom_categories", []))


def add_custom_category(name):
    name = (name or "").strip()
    if not name:
        return False
    cfg = config.load()
    cats = cfg.setdefault("custom_categories", [])
    if name in (set(EXPENSE_CATEGORIES) | set(INCOME_CATEGORIES) | set(cats)):
        return False
    cats.append(name)
    config.save(cfg)
    return True


def remove_custom_category(name):
    cfg = config.load()
    cats = cfg.get("custom_categories", [])
    if name in cats:
        cats.remove(name)
        config.save(cfg)
        return True
    return False


def pending():
    return [_d(r) for r in db.pending()]


def recent(limit=1000):
    return [_d(r) for r in db.recent(limit)]


def totals_by_category():
    return [_d(r) for r in db.totals_by_category()]


def send_recent_to_review(days=3):
    """Move recently AUTO-categorised transactions back to 'pending' so they show
    up in Review for the user to verify. Leaves anything the user hand-tagged
    (category differs from the guess, or has a note) alone."""
    from datetime import date, timedelta
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    c = db.conn()
    cur = c.execute(
        "UPDATE txns SET status='pending' "
        "WHERE status='tagged' AND tdate >= ? AND (note IS NULL OR note='') "
        "AND (category IS NULL OR category='' OR category = guessed_category)",
        (cutoff,))
    c.commit()
    return cur.rowcount


def recover_from_cache():
    cfg = config.load()
    # (account, uid, seq) already stored — so we can add missing transactions of a
    # multi-transaction email even if one of them already exists.
    existing = {(r["account"], r["uid"], r["seq"]) for r in
                db.conn().execute("SELECT account, uid, seq FROM txns")}
    rows = cache.conn().execute(
        "SELECT account, uid, from_addr, subject, body, email_date FROM email_cache").fetchall()
    rec = 0
    for r in rows:
        if not mailreader._tracked(cfg, r["from_addr"] or "", r["subject"] or ""):
            continue
        src = mailreader.matching_source(cfg, r["from_addr"] or "", r["subject"] or "")
        for i, p in enumerate(mailreader.parse_emails(r["subject"] or "", r["body"] or "", r["from_addr"] or "")):
            if (r["account"], r["uid"], i) in existing:
                continue
            p["source"] = src
            p["guessed_category"] = guess_category(
                f"{p['merchant']} {r['subject'] or ''}", p["direction"])
            p.update(uid=r["uid"], account=r["account"], subject=(r["subject"] or "")[:200],
                     from_addr=(r["from_addr"] or "")[:160], email_date=r["email_date"], seq=i)
            if db.add_txn(p, status="tagged", seq=i):
                rec += 1
    return rec


def cache_count():
    try:
        return cache.count()
    except Exception:
        return 0


def clear_cache():
    cache.clear()


def parse_debug(subject, body, from_addr):
    cfg = config.load()
    mailreader.apply_custom(cfg)
    res = mailreader.parse_debug(subject, body, from_addr)
    res["tracked"] = mailreader._tracked(cfg, from_addr, subject)
    res["source"] = mailreader.matching_source(cfg, from_addr, subject)
    return res


def test_connection(acc):
    return mailreader.test_connection(acc)
