# -*- coding: utf-8 -*-
"""Background QThread workers: live poller + range scanner. They touch only the
DB / IMAP and report back via Qt signals (queued to the UI thread automatically)."""
import threading, time, socket, imaplib
from datetime import date

from PyQt5.QtCore import QThread, pyqtSignal

import config, db, mailreader
from categorize import guess_category, CC_BILL_CATEGORY

_NET_ERRORS = (socket.gaierror, socket.timeout, TimeoutError, ConnectionError,
               OSError, imaplib.IMAP4.error, imaplib.IMAP4.abort)


class PollerWorker(QThread):
    pollStart = pyqtSignal()
    pollDone = pyqtSignal(dict)          # {found, online}
    newTxn = pyqtSignal(dict)            # {id, merchant, amount, dir, bank, cat}
    logLine = pyqtSignal(str)            # human-readable activity for the log panel

    def __init__(self):
        super().__init__()
        self._trigger = threading.Event()
        self._stop = threading.Event()

    def check_now(self):
        self._trigger.set()

    def stop(self):
        self._stop.set()
        self._trigger.set()

    def _log(self, s):
        try:
            self.logLine.emit(s)
        except Exception:
            pass

    def _poll_once(self):
        cfg = config.load()
        accts = cfg.get("accounts", [])
        self._log(f"Checking {len(accts)} mailbox(es) for new transactions…")
        total_new = 0
        net_error = False
        for acc in accts:
            label = acc.get("label", "?")
            if not acc.get("email"):
                self._log(f"  {label}: skipped (missing email).")
                continue
            # OAuth mailboxes (Google/Microsoft) have no app password — they sign in
            # with a stored refresh token. Require a token for those, and an app
            # password only for the app-password method. (Previously this required an
            # app_password for every account, which silently skipped all OAuth ones.)
            if mailreader._is_oauth(acc):
                import oauth
                if not oauth.has_token(acc["email"]):
                    self._log(f"  {label}: skipped (not signed in — use 'Sign in' in Settings).")
                    continue
            elif not acc.get("app_password"):
                self._log(f"  {label}: skipped (missing app password).")
                continue
            # everything for one account is guarded so nothing can escape and
            # leave the UI stuck on "Checking…"
            try:
                key = f"lastuid::{label}"
                raw = db.get_meta(key)
                try:
                    lu = int(raw)
                except (TypeError, ValueError):
                    lu = None
                # A 0/blank/negative cursor must NOT mean "scan UID 1:* (the whole
                # mailbox)" — that's tens of thousands of emails. Treat it as a first
                # run: back-fill a few days, then jump the cursor to the newest email.
                if lu is not None and lu <= 0:
                    lu = None
                if lu is None:
                    self._log(f"  {label}: first check — scanning the last "
                              f"{cfg.get('backfill_days', 3)} day(s), then watching for new mail only.")
                self._log(f"  {label}: connecting to Gmail (IMAP)…")
                seen = {"n": 0}

                def on_uid(u, lbl=label, seen=seen):
                    db.mark_scanned(lbl, u)
                    seen["n"] += 1
                    if seen["n"] % 200 == 0:
                        self._log(f"  {label}: scanned {seen['n']} emails so far…")
                txns, new_last = mailreader.poll_account(acc, cfg, lu, on_uid=on_uid)
                added = 0
                for t in txns:
                    # Pre-fill the category (from merchant memory if we've seen this
                    # payee, else a guess) but ALWAYS add as 'pending' so every new
                    # transaction shows up in Review for the user to see & verify.
                    remembered = db.recall_merchant(db.merch_key(t["merchant"]))
                    t["guessed_category"] = remembered or guess_category(
                        f"{t['merchant']} {t['subject']}", t["direction"])
                    rid = db.add_txn(t)          # status defaults to 'pending' -> Review
                    if rid:
                        added += 1
                        total_new += 1
                        self._log(f"      + Rs {t['amount']:,.0f}  {(t['merchant'] or '')[:26]}  "
                                  f"->  {t['guessed_category']}  (to review)")
                        self.newTxn.emit({
                            "id": rid, "merchant": t["merchant"], "amount": t["amount"],
                            "dir": t["direction"], "bank": t.get("bank") or label,
                            "cat": t["guessed_category"], "auto": False})
                db.set_meta(key, new_last)
                self._log(f"  {label}: {len(txns)} matched, {added} new "
                          f"(cursor now {new_last}).")
            except _NET_ERRORS as e:
                net_error = True
                self._log(f"  {label}: offline/unreachable ({type(e).__name__}: {e}) — will retry.")
            except Exception as e:
                net_error = True
                self._log(f"  {label}: ERROR {type(e).__name__}: {e}")
        self._log(f"Check finished — {total_new} new transaction(s)."
                  + ("  (a mailbox was offline; will retry)" if net_error else ""))
        return total_new, net_error

    def run(self):
        time.sleep(1.0)
        fails = 0
        while not self._stop.is_set():
            self.pollStart.emit()
            found = 0
            net_error = False
            try:
                found, net_error = self._poll_once()
            except Exception as e:
                net_error = True
                self._log(f"Check crashed unexpectedly: {type(e).__name__}: {e}")
            finally:
                # ALWAYS resolve the UI status — never leave it stuck on "Checking…"
                self.pollDone.emit({"found": found, "online": not net_error})
            base = int(config.load().get("poll_interval_seconds", 300))
            if net_error:
                fails += 1
                wait = min(base, 30 * fails)
                self._log(f"Offline — next retry in ~{max(10, wait)}s.")
            else:
                fails = 0
                wait = base
            self._trigger.wait(timeout=max(10, wait))
            self._trigger.clear()


class ScanWorker(QThread):
    logLine = pyqtSignal(str)
    accStart = pyqtSignal(dict)          # {idx, total, label}
    totalKnown = pyqtSignal(dict)        # {to_read, in_range}
    progress = pyqtSignal(dict)          # {done, total, added, scanned}
    finishedScan = pyqtSignal(dict)      # {scanned, added, skipped, from_cache, downloaded, cache}

    def __init__(self, sd, ed, force):
        super().__init__()
        self.sd, self.ed, self.force = sd, ed, force
        self._stop = threading.Event()

    def cancel(self):
        self._stop.set()

    def run(self):
        cfg = config.load()
        accts = cfg.get("accounts", [])
        st = {"scanned": 0, "added": 0, "skipped": 0, "from_cache": 0, "downloaded": 0}
        mode = "FORCE re-fetch (ignore history)" if self.force else "new emails only (skip already-fetched)"
        self.logLine.emit(f"Scan {self.sd} -> {self.ed} across {len(accts)} mailbox(es) — {mode}.")
        if not accts:
            self.logLine.emit("No mailboxes configured. Add one in Settings.")
            self.finishedScan.emit({**st, "cache": _cache_count()})
            return
        for i, acc in enumerate(accts):
            if self._stop.is_set():
                break
            label = acc.get("label", "?")
            self.accStart.emit({"idx": i + 1, "total": len(accts), "label": label})
            self.logLine.emit(f"[{i+1}/{len(accts)}] Connecting to {label} ({acc.get('email')}) ...")
            skip = set() if self.force else db.scanned_uids(label)

            def on_total(to_read, in_range, skipped, label=label):
                st["skipped"] += skipped
                filtered = in_range - skipped - to_read
                self.totalKnown.emit({"to_read": to_read, "in_range": in_range})
                if in_range == 0:
                    self.logLine.emit("   No emails in this date range.")
                else:
                    self.logLine.emit(f"   {in_range} emails in range: {skipped} already-fetched, "
                                      f"{filtered} filtered out, {to_read} to read.")

            def on_step(done, total, uid, plist, label=label):
                if self._stop.is_set():
                    raise _Cancelled()
                st["scanned"] += 1
                db.mark_scanned(label, uid)
                for p in (plist or []):        # one email can yield several txns
                    p["guessed_category"] = guess_category(
                        f"{p['merchant']} {p['subject']}", p["direction"])
                    if db.add_txn(p, status="tagged"):
                        st["added"] += 1
                        sign = "+" if p["direction"] == "IN" else "-"
                        self.logLine.emit(f"   {sign} Rs {p['amount']:,.0f}  "
                                          f"{p['merchant'][:26]}  ->  {p['guessed_category']}")
                self.progress.emit({"done": done, "total": total,
                                    "added": st["added"], "scanned": st["scanned"]})

            def on_fetch(from_cache):
                st["from_cache" if from_cache else "downloaded"] += 1

            try:
                mailreader.scan_range(acc, cfg, self.sd, self.ed, on_total=on_total,
                                      on_step=on_step, skip_uids=skip, on_fetch=on_fetch)
                self.logLine.emit(f"   {label}: finished.")
            except _Cancelled:
                self.logLine.emit("   Scan cancelled by user.")
                break
            except _NET_ERRORS as e:
                self.logLine.emit(f"   {label}: network error ({type(e).__name__}) — skipped.")
            except Exception as e:
                self.logLine.emit(f"   ERROR {label}: {e}")
        self.finishedScan.emit({**st, "cache": _cache_count()})
        self.logLine.emit(f"Done. Processed {st['scanned']} emails "
                          f"({st['from_cache']} from cache, {st['downloaded']} downloaded, "
                          f"{st['skipped']} skipped) — added {st['added']} transactions.")


class OAuthWorker(QThread):
    """Runs the interactive OAuth sign-in (opens the browser, waits for the
    loopback redirect) off the UI thread so the window stays responsive.
    provider is 'google' or 'microsoft'."""
    done = pyqtSignal(dict)              # {ok, message, email, provider}

    def __init__(self, email, provider, client_id, client_secret=""):
        super().__init__()
        self.email, self.provider = email, provider
        self.cid, self.csec = client_id, client_secret

    def run(self):
        try:
            import oauth
            ok, msg = oauth.authorize(self.email, self.provider, self.cid, self.csec)
        except Exception as e:
            ok, msg = False, f"{type(e).__name__}: {e}"
        self.done.emit({"ok": ok, "message": msg, "email": self.email,
                        "provider": self.provider})


class _Cancelled(Exception):
    pass


def _cache_count():
    try:
        import cache
        return cache.count()
    except Exception:
        return 0
