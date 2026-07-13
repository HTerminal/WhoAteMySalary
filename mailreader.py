# -*- coding: utf-8 -*-
"""Read Gmail over IMAP, find bank/transaction alert emails, extract the amount,
direction and merchant."""
import imaplib, email, re, html
from email.header import decode_header
from datetime import date, timedelta
import cache

IMAP_HOST = "imap.gmail.com"

# currency + number building blocks
_CUR = r'(?:INR|Rs\.?|RS\.?|₹|USD|US\$|GBP|EUR|AED|SGD|AUD|CAD|JPY|MYR|THB|\$|£|€)'
_NUM = r'(?:\d[\d,]*\.\d{1,2}|\.\d{1,2}|\d[\d,]*)'   # 56,509.00 | 0.31 | .31 | 31
_CURMAP = {"RS": "INR", "₹": "INR", "$": "USD", "US$": "USD", "£": "GBP", "€": "EUR", "INR": "INR"}
# amount tied to the transaction phrase (most reliable — avoids credit-limit figures)
_TXN_AMT_RE = re.compile(r'(?:transaction of|txn of|transaction for)\s*(' + _CUR + r')\s*(' + _NUM + r')', re.I)
# amount that FOLLOWS a debit/credit verb
_VERB_AMT_RE = re.compile(r'(?:spent|debited|credited|charged|paid|withdrawn|deducted|purchase of|received)\b[^0-9₹$£€]{0,25}?(' + _CUR + r')\s*(' + _NUM + r')', re.I)
# any currency amount (last resort)
_ANY_AMT_RE = re.compile(r'(' + _CUR + r')\s*(' + _NUM + r')', re.I)
# amount stated WITHOUT a currency symbol after a verb, e.g. PNB "Debited with 1800.00"
_VERB_NOCUR_RE = re.compile(r'(?:debited|credited|spent|withdrawn|deducted|paid)\s+'
                            r'(?:with|by|of)\s+(?:rs\.?\s*|inr\s*)?(' + _NUM + r')', re.I)


def _mk_amt(m):
    cur = m.group(1).upper().rstrip('.')
    cur = _CURMAP.get(cur, cur)
    try:
        return float(m.group(2).replace(",", "")), cur
    except ValueError:
        return None


def _extract_amount(blob):
    """Return (amount, currency). Prefers the amount stated as the transaction
    amount; never picks up the 'Available/Total Credit Limit' figures."""
    for rx in (_TXN_AMT_RE, _VERB_AMT_RE):
        m = rx.search(blob)
        if m:
            r = _mk_amt(m)
            if r:
                return r
    # amount with no currency symbol after a debit/credit verb -> assume INR
    m = _VERB_NOCUR_RE.search(blob)
    if m:
        try:
            val = float(m.group(1).replace(",", ""))
            if val > 0:
                return val, "INR"
        except ValueError:
            pass
    for m in _ANY_AMT_RE.finditer(blob):
        ctx = blob[max(0, m.start() - 48):m.start()].lower()
        if any(k in ctx for k in ("credit limit", "available", "avl limit", "avl.",
                                  "total credit", "limit on", "balance")):
            continue
        r = _mk_amt(m)
        if r:
            return r
    return None

IN_KW  = ["credited", "deposited", "received", "credit of", "has been credited",
          "money received", "added to", "refund of"]
OUT_KW = ["debited", "spent", "withdrawn", "paid", "purchase", "debit of",
          "sent", "transferred", "deducted", "has been debited",
          "used for a transaction", "has been used for", "used for a txn",
          "charged", "spent on", "transaction of inr", "transaction of rs"]

BANKS = {
    "canara": "Canara Bank", "pnb": "PNB", "punjab national": "PNB",
    "hdfc": "HDFC", "sbi": "SBI", "state bank": "SBI", "icici": "ICICI",
    "axis": "Axis", "kotak": "Kotak", "cred": "CRED", "yesbank": "YES",
    "idfc": "IDFC", "bob": "Bank of Baroda", "baroda": "Bank of Baroda",
}

_STOP = r'(?:\s+on\b|\s+via\b|\s+ref\b|\s+dated\b|\s+with\b|[\.,;]|$)'
MERCHANT_PATTERNS = [
    r'UPI/[A-Z]{2}/\d+/([^/]+)/',
    r'\bInfo[:\-]\s*([A-Za-z0-9&._/\- ]{2,40}?)' + _STOP,      # narration field (ICICI etc.)
    r'(?:card|xx\d{3,4})\s*[:\-]\s*([A-Za-z0-9&.\- ]{2,40}?)\s+on\b',   # Canara: "...CreditCard XX1009: ZOMATOLIMITED on 07-JUL"
    r'\bfor\s+([A-Za-z0-9&._\- ]{2,40}?)\s+on\s+\d',           # Canara: "...for SWIGGY on 04-MAY-26"
    r'\btowards\s+([A-Za-z0-9&._\- ]{2,40}?)' + _STOP,
    r'\bat\s+([A-Za-z0-9&._\- ]{2,40}?)' + _STOP,
    r'\bto\s+VPA\s+([^\s]{2,40})',
    r'\bby\s+([A-Za-z][A-Za-z0-9&._\- ]{2,40}?)' + _STOP,
    r'\bto\s+([A-Za-z0-9&._\- ]{2,40}?)' + _STOP,
    r'\bfrom\s+([A-Za-z0-9&._\- ]{2,40}?)\s+(?:on|has)\b',
    r'\bthru\s+([A-Za-z][A-Za-z/&\- ]{1,20}?)\s',        # PNB acct: "...thru IBS/MBS", "thru BRANCH"
    r'\bVPA\s+([^\s]{2,40})',
]
# words that are boilerplate, never a real merchant
_STOPWORDS = {"customer", "customer care", "dear customer", "you", "your", "the",
              "us", "we", "card", "credit card", "bank", "icici bank", "details",
              "info", "account", "a/c", "know more", "click here",
              "block your credit card", "block your card", "your credit card",
              "using canara credit card", "your registered", "registered e-mail id",
              "block", "your registered e-mail id"}


# user-defined additions (loaded from config['custom']); let users extend parsing
EXTRA_MERCHANT_PATTERNS = []
EXTRA_OUT_KW = []
EXTRA_IN_KW = []


def apply_custom(cfg):
    """Load user's custom parsing rules from config so they take effect."""
    global EXTRA_MERCHANT_PATTERNS, EXTRA_OUT_KW, EXTRA_IN_KW
    c = (cfg or {}).get("custom", {}) or {}
    pats = []
    for p in c.get("merchant_patterns", []):
        try:
            re.compile(p)
            pats.append(p)
        except re.error:
            pass
    EXTRA_MERCHANT_PATTERNS = pats
    EXTRA_OUT_KW = [k.lower() for k in c.get("out_keywords", []) if k.strip()]
    EXTRA_IN_KW = [k.lower() for k in c.get("in_keywords", []) if k.strip()]


def _dec(s):
    if not s:
        return ""
    out = []
    for part, enc in decode_header(s):
        if isinstance(part, bytes):
            try:
                out.append(part.decode(enc or "utf-8", "ignore"))
            except Exception:
                out.append(part.decode("utf-8", "ignore"))
        else:
            out.append(part)
    return "".join(out)


def _body(msg):
    """Return plain-text body (html stripped)."""
    def strip_html(h):
        h = re.sub(r'(?is)<(script|style).*?>.*?</\1>', ' ', h)
        h = re.sub(r'(?s)<[^>]+>', ' ', h)
        return html.unescape(re.sub(r'\s+', ' ', h)).strip()
    plain, htmlt = "", ""
    if msg.is_multipart():
        for p in msg.walk():
            ctype = p.get_content_type()
            disp = str(p.get("Content-Disposition") or "")
            if "attachment" in disp:
                continue
            try:
                payload = p.get_payload(decode=True)
                if not payload:
                    continue
                txt = payload.decode(p.get_content_charset() or "utf-8", "ignore")
            except Exception:
                continue
            if ctype == "text/plain":
                plain += txt + " "
            elif ctype == "text/html":
                htmlt += txt + " "
    else:
        try:
            txt = msg.get_payload(decode=True).decode(
                msg.get_content_charset() or "utf-8", "ignore")
        except Exception:
            txt = str(msg.get_payload())
        if msg.get_content_type() == "text/html":
            htmlt = txt
        else:
            plain = txt
    return (plain if plain.strip() else strip_html(htmlt))


def _bank(text):
    t = text.lower()
    for k, v in BANKS.items():
        if k in t:
            return v
    return ""


_CARD_RE = re.compile(r'(?:card|a/?c|account)\s+(?:no\.?\s*|ending\s+)?((?:x|\*){2,}\s?\d{3,4}|xx\d{3,4}|\d{4})\b', re.I)


def _card(subject, body):
    """Pull the card identifier (e.g. XX6004) from the alert, if present."""
    m = _CARD_RE.search(f"{subject} {body}")
    return m.group(1).upper().replace(" ", "").replace("*", "X") if m else ""


def matching_source(cfg, from_addr, subject):
    """Which configured source matched this email (for tagging). Returns the
    source name, or '(catch-all)' if it only passed via the global toggle."""
    fa, su = from_addr.lower(), subject.lower()
    for s in cfg.get("sources", []):
        if _source_matches(s, fa, su):
            return s.get("name", "") or "(source)"
    if cfg.get("track_all_amount_emails", True):
        return "(catch-all)"
    return ""


def _merchant(body, subject):
    for pat in (EXTRA_MERCHANT_PATTERNS + MERCHANT_PATTERNS):  # user patterns first
        try:
            m = re.search(pat, body, re.I)
        except re.error:
            continue
        if m:
            val = m.group(1).strip(" .-_")
            # reject pure numbers / times / dates (e.g. "at 06:09:11") and boilerplate
            if (val and not val.isdigit()
                    and not re.fullmatch(r'[\d\s:.\-/]+', val)
                    and val.lower() not in _STOPWORDS):
                return val[:40]
    # fall back to a cleaned subject
    s = re.sub(r'(?i)(alert|transaction|txn|your|a/c|account|update|dear customer)', '', subject)
    return re.sub(r'\s+', ' ', s).strip(" -:")[:40] or "(unknown)"


def parse_email(subject, body, from_addr):
    """Return a txn dict, or None if this is not a transaction alert."""
    blob = f"{subject}\n{body}"
    low = blob.lower()

    got = _extract_amount(blob)
    if not got:
        return None
    amount, currency = got
    if amount <= 0:
        return None

    is_in = any(k in low for k in IN_KW) or any(k in low for k in EXTRA_IN_KW)
    is_out = any(k in low for k in OUT_KW) or any(k in low for k in EXTRA_OUT_KW)
    if not (is_in or is_out):
        return None                      # no debit/credit verb -> not a txn alert
    direction = "IN" if (is_in and not is_out) else ("OUT" if is_out else "IN")

    merchant = _merchant(body, subject)
    if currency and currency != "INR":
        merchant = f"{merchant} [{currency} {amount:g}]"   # flag foreign-currency txns

    return {
        "amount": amount,
        "currency": currency or "INR",
        "direction": direction,
        "merchant": merchant,
        "card": _card(subject, body),
        "bank": _bank(f"{from_addr} {subject} {body[:200]}"),
    }


# splits a body at forwarded / nested-email boundaries ("email within an email")
_FWD_SPLIT = re.compile(
    r'(?:-{2,}\s*forwarded message\s*-{2,}'
    r'|-{2,}\s*original message\s*-{2,}'
    r'|\bbegin forwarded message\b'
    r'|^\s*On\b.{5,80}\bwrote:)', re.I | re.M)


def parse_emails(subject, body, from_addr):
    """Return a LIST of transactions. Usually one; more when the email contains a
    forwarded / nested email ('email within an email') that carries its own
    transaction. Falls back to a whole-body parse if splitting finds nothing."""
    body = body or ""
    parts = _FWD_SPLIT.split(body)
    results, seen = [], set()
    for i, seg in enumerate(parts):
        if not seg or not seg.strip():
            continue
        p = parse_email(subject if i == 0 else "", seg, from_addr)
        if not p:
            continue
        key = (round(p["amount"], 2), p["direction"])   # de-dup wrapper vs nested copy
        if key in seen:
            continue
        seen.add(key)
        results.append(p)
    if not results:
        p = parse_email(subject, body, from_addr)
        if p:
            results.append(p)
    return results


def effective_mode(src):
    """Resolve a source's (match, primary), inferring sensible defaults."""
    F = (src.get("from_contains") or "").strip()
    S = (src.get("subject_contains") or "").strip()
    mode = (src.get("match") or "").lower()
    if mode not in ("both", "from", "subject", "either"):
        mode = "both" if (F and S) else ("from" if F else ("subject" if S else "either"))
    primary = (src.get("primary") or "from").lower()
    if primary not in ("from", "subject"):
        primary = "from"
    return mode, primary


def _source_matches(src, fa, su):
    """Does one source match this email? fa/su are lowercased from-addr/subject.
    'both'  -> primary field must match FIRST, then the other (hierarchical).
    'from' / 'subject' -> only that field.  'either' -> primary first, then the other."""
    F = (src.get("from_contains") or "").strip().lower()
    S = (src.get("subject_contains") or "").strip().lower()
    from_ok = (F in fa) if F else None      # None => that field is not constraining
    subj_ok = (S in su) if S else None
    mode, primary = effective_mode(src)

    def ok(x):
        return True if x is None else x

    if mode == "from":
        return bool(F) and ok(from_ok)
    if mode == "subject":
        return bool(S) and ok(subj_ok)
    if mode == "either":
        if primary == "subject":
            return ok(subj_ok) or ok(from_ok)
        return ok(from_ok) or ok(subj_ok)
    # both -> check the primary field first; only if it matches, check the other
    if primary == "subject":
        if not ok(subj_ok):
            return False
        return ok(from_ok)
    if not ok(from_ok):
        return False
    return ok(subj_ok)


def parse_debug(subject, body, from_addr):
    """Explain what the parser extracts from an email (for the Parser page)."""
    blob = f"{subject}\n{body}"
    low = blob.lower()
    out = {"amount": None, "currency": None, "direction": None, "merchant": None,
           "card": None, "amount_rule": None, "merchant_rule": None,
           "is_txn": False, "why": ""}
    # amount + which rule
    for name, rx in (("transaction-phrase", _TXN_AMT_RE), ("debit/credit-verb", _VERB_AMT_RE)):
        m = rx.search(blob)
        if m and _mk_amt(m):
            out["amount"], out["currency"] = _mk_amt(m); out["amount_rule"] = name; break
    if out["amount"] is None:
        for m in _ANY_AMT_RE.finditer(blob):
            ctx = blob[max(0, m.start() - 48):m.start()].lower()
            if any(k in ctx for k in ("credit limit", "available", "avl limit", "avl.",
                                      "total credit", "limit on", "balance")):
                continue
            r = _mk_amt(m)
            if r:
                out["amount"], out["currency"] = r; out["amount_rule"] = "first-amount (skipping balance/limit)"; break
    # direction
    is_in = any(k in low for k in IN_KW) or any(k in low for k in EXTRA_IN_KW)
    is_out = any(k in low for k in OUT_KW) or any(k in low for k in EXTRA_OUT_KW)
    out["direction"] = "IN" if (is_in and not is_out) else ("OUT" if is_out else ("IN" if is_in else None))
    # merchant + which pattern
    for pat in (EXTRA_MERCHANT_PATTERNS + MERCHANT_PATTERNS):
        try:
            m = re.search(pat, body, re.I)
        except re.error:
            continue
        if m:
            val = m.group(1).strip(" .-_")
            if val and not val.isdigit() and not re.fullmatch(r'[\d\s:.\-/]+', val) and val.lower() not in _STOPWORDS:
                out["merchant"] = val[:40]; out["merchant_rule"] = pat; break
    if out["merchant"] is None:
        out["merchant"] = _merchant(body, subject)
        out["merchant_rule"] = "fallback: cleaned subject"
    out["card"] = _card(subject, body)
    if out["amount"] and (is_in or is_out):
        out["is_txn"] = True
    else:
        out["why"] = ("no amount found" if not out["amount"]
                      else "no debit/credit keyword found (not a transaction alert)")
    return out


def _tracked(cfg, from_addr, subject):
    fa, su = from_addr.lower(), subject.lower()
    for ig in cfg.get("ignore_senders", []):
        if ig.lower() in fa:
            return False
    srcs = cfg.get("sources") or []
    # 1) a defined source that matches always wins (precise, hierarchical)
    for s in srcs:
        if _source_matches(s, fa, su):
            return True
    # 2) otherwise, only the global catch-all can let it through
    if cfg.get("track_all_amount_emails", True):
        return True
    return False if srcs else True


def _process_uid(M, raw_uid, acc, cfg, use_cache=True, on_fetch=None):
    """Return a parsed txn dict or None. Reads the email body from the local
    cache when available (no Gmail round-trip); otherwise fetches and caches it.
    on_fetch(from_cache: bool) is called once the body is obtained."""
    u = int(raw_uid)
    label = acc["label"]
    c = cache.get(label, u) if use_cache else None
    if c:
        subject, frm, body, edate = c["subject"], c["from_addr"], c["body"], c["email_date"]
        if on_fetch:
            on_fetch(True)
    else:
        typ, md = M.uid("fetch", raw_uid, "(BODY.PEEK[])")
        if not md or not md[0]:
            return None
        msg = email.message_from_bytes(md[0][1])
        subject = _dec(msg.get("Subject"))
        frm = _dec(msg.get("From"))
        body = _body(msg)
        edate = msg.get("Date", "")
        try:
            cache.put(label, u, frm, subject, body, edate)
        except Exception:
            pass
        if on_fetch:
            on_fetch(False)
    if not _tracked(cfg, frm, subject):
        return []
    parsed_list = parse_emails(subject, body, frm)
    if not parsed_list:
        return []
    src = matching_source(cfg, frm, subject)
    out = []
    for i, parsed in enumerate(parsed_list):
        parsed["source"] = src
        parsed.update(uid=u, account=label, subject=subject[:200],
                      from_addr=frm[:160], email_date=edate, seq=i)
        out.append(parsed)
    return out


def _is_oauth(acc):
    return (acc.get("auth") or "app_password").lower() in (
        "oauth", "google", "google_oauth", "microsoft", "microsoft_oauth")


def _imap_host(acc):
    """The IMAP server for this mailbox: Gmail for app passwords / Google OAuth,
    Outlook for Microsoft OAuth, or an explicit per-mailbox 'imap_host' override."""
    if acc.get("imap_host"):
        return acc["imap_host"]
    if _is_oauth(acc):
        import oauth
        return oauth.imap_host(oauth.provider_of(acc))
    return IMAP_HOST


def _imap_login(M, acc):
    """Authenticate an open IMAP connection using the mailbox's chosen method:
    OAuth2 (Google or Microsoft, via XOAUTH2) or a Gmail app password."""
    if _is_oauth(acc):
        import oauth                      # lazy: only needed for OAuth mailboxes
        token = oauth.access_token(acc["email"])
        M.authenticate("XOAUTH2", lambda _=None: oauth.xoauth2_bytes(acc["email"], token))
    else:
        M.login(acc["email"], acc["app_password"])


def _connect(acc):
    M = imaplib.IMAP4_SSL(_imap_host(acc), timeout=25)   # never hang forever on connect
    _imap_login(M, acc)
    M.select(acc.get("folder", "INBOX"), readonly=True)
    return M


def poll_account(acc, cfg, last_uid, on_uid=None):
    """Connect, fetch new messages, return (list_of_txn_dicts, new_last_uid).
    on_uid(uid): called for every email actually fetched (for fetch-once bookkeeping)."""
    results = []
    M = _connect(acc)
    try:
        if last_uid is None:
            since = (date.today() - timedelta(days=int(cfg.get("backfill_days", 3)))
                     ).strftime("%d-%b-%Y")
            typ, data = M.uid("search", None, "SINCE", since)
        else:
            typ, data = M.uid("search", None, "UID", f"{last_uid+1}:*")
        uids = (data[0].split() if data and data[0] else [])
        new_last = last_uid or 0
        for raw_uid in uids:
            u = int(raw_uid)
            if last_uid is not None and u <= last_uid:
                continue
            new_last = max(new_last, u)
            if on_uid:
                on_uid(u)
            results.extend(_process_uid(M, raw_uid, acc, cfg))
        # On first run, advance the cursor to the mailbox's newest UID so later
        # polls only pick up genuinely new mail (never rescan full history).
        if last_uid is None:
            typ2, alld = M.uid("search", None, "ALL")
            allu = alld[0].split() if alld and alld[0] else []
            if allu:
                new_last = max(new_last, int(allu[-1]))
        return results, new_last
    finally:
        try:
            M.logout()
        except Exception:
            pass


def _chunks(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def _candidate_uids(M, cfg, since, before, skip_uids):
    """Return (uids_to_read, total_in_range, skipped_count).

    Gmail's server-side FROM/SUBJECT search only matches whole tokens (so a
    partial like 'credit_cards@icici' returns nothing). To filter reliably we
    bulk-fetch just the FROM/SUBJECT *headers* (tiny) for every email in the
    range and apply the exact rule client-side — then only the matches get a
    full body download. This keeps wide ranges fast."""
    typ, d = M.uid("search", None, "SINCE", since, "BEFORE", before)
    in_range = d[0].split() if d and d[0] else []
    not_skipped = [u for u in in_range if int(u) not in skip_uids]
    skipped = len(in_range) - len(not_skipped)

    srcs = cfg.get("sources") or []
    if cfg.get("track_all_amount_emails", True) or not srcs:
        return not_skipped, len(in_range), skipped

    matched = []
    for chunk in _chunks(not_skipped, 300):
        uidset = b",".join(chunk)
        try:
            typ, data = M.uid("fetch", uidset,
                              "(UID BODY.PEEK[HEADER.FIELDS (FROM SUBJECT)])")
        except Exception:
            matched.extend(chunk)          # on error, don't drop them
            continue
        for item in (data or []):
            if not isinstance(item, tuple) or len(item) < 2:
                continue
            meta, hdr = item[0] or b"", item[1] or b""
            mm = re.search(rb"UID\s+(\d+)", meta)
            if not mm:
                continue
            uid = mm.group(1)
            try:
                msg = email.message_from_bytes(hdr)
                frm = _dec(msg.get("From"))
                subj = _dec(msg.get("Subject"))
            except Exception:
                matched.append(uid)
                continue
            if _tracked(cfg, frm, subj):
                matched.append(uid)
    return matched, len(in_range), skipped


def scan_range(acc, cfg, start_date, end_date, on_total=None, on_step=None,
               skip_uids=None, on_fetch=None):
    """Full scan of a date window (by email received date). start/end = date objects.
    Returns a list of txn dicts. Does NOT move the live poller cursor.
    skip_uids: set of UIDs already fetched before (they are skipped = fetch-once).
    on_total(new, total): emails newly-to-read vs total in range.
    on_step(done, new_total, uid, parsed_or_None): called after each fetched email."""
    skip_uids = skip_uids or set()
    results = []
    M = _connect(acc)
    try:
        since = start_date.strftime("%d-%b-%Y")
        before = (end_date + timedelta(days=1)).strftime("%d-%b-%Y")   # BEFORE is exclusive
        new_uids, in_range_n, skipped_n = _candidate_uids(M, cfg, since, before, skip_uids)
        if on_total:
            on_total(len(new_uids), in_range_n, skipped_n)
        for i, raw_uid in enumerate(new_uids):
            plist = _process_uid(M, raw_uid, acc, cfg, on_fetch=on_fetch)
            results.extend(plist)
            if on_step:
                on_step(i + 1, len(new_uids), int(raw_uid), plist)
        return results
    finally:
        try:
            M.logout()
        except Exception:
            pass


def test_connection(acc):
    try:
        M = imaplib.IMAP4_SSL(_imap_host(acc), timeout=25)
        _imap_login(M, acc)
        M.select("INBOX", readonly=True)
        M.logout()
        return True, "OK"
    except Exception as e:
        return False, str(e)
