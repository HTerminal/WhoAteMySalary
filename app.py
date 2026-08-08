# -*- coding: utf-8 -*-
"""WhoAteMySalary — PyQt5 desktop edition.

Native Qt GUI: reads Gmail over IMAP, detects bank/transaction alerts, notifies
you (system tray), and lets you categorise + analyse spending. Smooth rendering,
native sortable tables, native calendar date-pickers, expandable merchant tree.

Run:  py -3.12 app.py
"""
import sys, os, csv, time, re
from html import escape
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass
from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime

from PyQt5.QtCore import (Qt, QDate, QTimer, QPropertyAnimation, QAbstractAnimation,
                          pyqtSignal, QRectF, QObject, QEvent, QUrl, QRect, QPoint, QSize)
from PyQt5.QtGui import (QColor, QFont, QIcon, QPixmap, QPainter, QTextCharFormat,
                         QPainterPath, QLinearGradient, QBrush, QPen, QTextDocument, QCursor,
                         QFontMetrics)
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFrame, QLabel, QPushButton, QVBoxLayout,
    QHBoxLayout, QGridLayout, QStackedWidget, QScrollArea, QComboBox, QLineEdit,
    QDateEdit, QCheckBox, QSpinBox, QPlainTextEdit, QTableWidget, QHeaderView,
    QAbstractItemView, QTreeWidget, QTreeWidgetItem, QDialog, QMessageBox,
    QButtonGroup, QSystemTrayIcon, QGraphicsOpacityEffect, QSizePolicy, QSplashScreen,
    QFileDialog, QAbstractScrollArea, QLayout, QSpacerItem, QGraphicsDropShadowEffect)

import theme as T
import engine
import charts
from charts import DonutChart, HBars, TimeBars, KPICard, NumItem
from workers import PollerWorker, ScanWorker, OAuthWorker
import config
import mailreader
import notify
import oauth
import goblin
from categorize import EXPENSE_CATEGORIES, INCOME_CATEGORIES

DONUT_RES = "wams://donut.png"      # in-document name for the report's donut image

NAV = [
    ("Overview",     "◈", "Overview",     "Your spending at a glance"),
    ("Inbox",        "✉", "Review",       "Confirm what new transactions were for"),
    ("Transactions", "≣", "Transactions", "Every detected transaction"),
    ("Scan",         "⟳", "Scan mailbox", "Fetch a date range from Gmail"),
    ("Parser",       "⚡", "Parser",       "See & tweak how emails are read"),
    ("Settings",     "⚙", "Settings",     "Mailboxes, filters & preferences"),
]


# ---------------- small helpers ----------------
def card():
    f = QFrame(); f.setObjectName("card"); return f


def lbl(text, obj=None, color=None, bold=False, size=None, wrap=False):
    q = QLabel(text)
    if obj:
        q.setObjectName(obj)
    if wrap:
        q.setWordWrap(True)      # long help texts flow with the window width
    css = "background:transparent;"
    if color:
        css += f"color:{color};"
    if bold:
        css += "font-weight:700;"
    if size:
        css += f"font-size:{size}pt;"
    if css:
        q.setStyleSheet(css)
    return q


def btn(text, slot=None, obj=None):
    b = QPushButton(text)
    if obj:
        b.setObjectName(obj)
    if slot:
        b.clicked.connect(slot)
    return b


def _form_row(text, widget, label_w=120):
    row = QHBoxLayout()
    L = lbl(text, color=T.MUTED, size=9)
    L.setFixedWidth(label_w)
    row.addWidget(L)
    row.addWidget(widget, 1)
    return row


def scroll_area(inner):
    sa = QScrollArea()
    sa.setWidgetResizable(True)
    sa.setWidget(inner)
    # AsNeeded (not AlwaysOff): on a window narrower than the content's minimum,
    # the tail end must stay reachable instead of being clipped away
    sa.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    return sa


class FlowLayout(QLayout):
    """A QHBoxLayout stand-in that wraps items onto extra rows when the window is
    too narrow to fit them all — toolbars adapt to the screen instead of getting
    clipped at the right edge. add_stretch() inserts a spring: whenever a row has
    leftover width, the spring absorbs it, so items after the spring sit flush
    right exactly like QHBoxLayout.addStretch() on a wide window.

    fill=True additionally stretches each row's items to share its full width
    (equal widths, like QHBoxLayout with equal stretch factors) — used for card
    rows, which then collapse from side-by-side into stacked full-width cards
    when the window can't fit them next to each other."""

    def __init__(self, parent=None, hspacing=8, vspacing=8, fill=False):
        super().__init__(parent)
        self._items = []
        self._h = hspacing
        self._v = vspacing
        self._fill = fill

    # ---- QLayout plumbing
    def addItem(self, item):
        self._items.append(item)

    def add_stretch(self):
        self.addItem(QSpacerItem(0, 0, QSizePolicy.Expanding, QSizePolicy.Minimum))

    def count(self):
        return len(self._items)

    def itemAt(self, i):
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i):
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientations(Qt.Orientation(0))

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        s = QSize()
        for it in self._items:
            if it.widget() is not None:
                s = s.expandedTo(it.minimumSize())
        m = self.contentsMargins()
        return s + QSize(m.left() + m.right(), m.top() + m.bottom())

    # ---- the actual flow
    def _do_layout(self, rect, test_only):
        m = self.contentsMargins()
        x0 = rect.x() + m.left()
        right = rect.right() - m.right()
        y = rect.y() + m.top()
        line, x = [], x0
        for it in self._items:
            spring = it.widget() is None
            hint = QSize(0, 0) if spring else it.sizeHint()
            if not spring and line and x + hint.width() > right + 1:
                y += self._flush(line, y, x0, right, test_only) + self._v
                line, x = [], x0
            line.append((it, hint, spring))
            if not spring:
                x += hint.width() + self._h
        y += self._flush(line, y, x0, right, test_only)
        return y + m.bottom() - rect.y()

    def _flush(self, line, y, x0, right, test_only):
        """Place one row (vertically centred); returns the row height."""
        widgets = [(it, h) for it, h, sp in line if not sp]
        if not widgets:
            return 0
        line_h = max(h.height() for _, h in widgets)
        if test_only:
            return line_h
        springs = sum(1 for _, _, sp in line if sp)
        avail = right + 1 - x0 - self._h * (len(widgets) - 1)
        widths = [float(h.width()) for _, h in widgets]
        if self._fill and not springs and avail > sum(widths):
            # equalise like QHBoxLayout with stretch 1,1,…, but never shrink an
            # item below its hint: keep raising the smallest until the extra runs out
            extra = avail - sum(widths)
            while extra > 0.5:
                lo = min(widths)
                idxs = [j for j, ww in enumerate(widths) if ww <= lo + 0.5]
                nxt = min((ww for ww in widths if ww > lo + 0.5), default=None)
                room = extra if nxt is None else (nxt - lo) * len(idxs)
                if nxt is None or room >= extra:
                    for j in idxs:
                        widths[j] += extra / len(idxs)
                    break
                for j in idxs:
                    widths[j] = nxt
                extra -= room
        spring_w = (max(0.0, avail - sum(widths)) / springs) if springs else 0.0
        x, i = float(x0), 0
        for it, h, sp in line:
            if sp:
                x += spring_w
                continue
            w = widths[i]; i += 1
            if self._fill:
                it.setGeometry(QRect(round(x), y, round(w), line_h))
            else:
                it.setGeometry(QRect(QPoint(round(x), y + (line_h - h.height()) // 2), h))
            x += w + self._h
        return line_h


def hgroup(*widgets, spacing=6):
    """Pack widgets into one unit so a FlowLayout wraps them together."""
    w = QWidget()
    w.setStyleSheet("background:transparent;")
    h = QHBoxLayout(w)
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(spacing)
    for x in widgets:
        h.addWidget(x)
    return w


def make_table(headers, stretch=None, sort_col=None, order=Qt.DescendingOrder):
    t = QTableWidget()
    t.setColumnCount(len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.verticalHeader().setVisible(False)
    t.setSortingEnabled(True)
    t.setSelectionBehavior(QAbstractItemView.SelectRows)
    t.setEditTriggers(QAbstractItemView.NoEditTriggers)
    t.setAlternatingRowColors(True)
    hh = t.horizontalHeader()
    hh.setHighlightSections(False)
    if stretch is not None:
        hh.setSectionResizeMode(stretch, QHeaderView.Stretch)
    return t


def txt_item(text):
    from PyQt5.QtWidgets import QTableWidgetItem
    return QTableWidgetItem(str(text))


def dt_str(r):
    """'YYYY-MM-DD HH:MM' from the email timestamp; falls back to just the date."""
    ed = r.get("email_date") or ""
    if ed:
        try:
            d = parsedate_to_datetime(ed)
            if d is not None:
                return d.strftime("%Y-%m-%d %H:%M")
        except Exception:
            pass
    return r.get("tdate") or ed[:16] or "—"


def _bank_card(r):
    """'ICICI · ••••6004' — whichever of the two the transaction actually carries."""
    bank = (r.get("bank") or r.get("source") or "").strip()
    last4 = engine.card_last4(r.get("card"))
    return "  ·  ".join(x for x in (bank, "••••" + last4 if last4 else "") if x) or "—"


class _WheelGuard(QObject):
    """Takes the wheel away from a picker that isn't focused. Date fields and combos
    live inside the scrolling pages, and by default a wheel notch over one of them
    silently changes its value while the user is only trying to scroll. The scroll
    is handed to the page underneath so hovering a picker isn't a dead zone."""
    def eventFilter(self, obj, ev):
        if ev.type() != QEvent.Wheel or obj.hasFocus():
            return False
        page = obj.parentWidget()
        while page is not None and not isinstance(page, QAbstractScrollArea):
            page = page.parentWidget()
        if page is not None:
            QApplication.sendEvent(page.viewport(), ev)
        return True


_WHEEL_GUARD = None


def no_wheel(w):
    """Make w ignore stray scrolling. Click or tab into it and the wheel works again."""
    global _WHEEL_GUARD
    if _WHEEL_GUARD is None:
        _WHEEL_GUARD = _WheelGuard()
    w.setFocusPolicy(Qt.StrongFocus)        # wheel alone must not focus it either
    w.installEventFilter(_WHEEL_GUARD)
    return w


def date_edit(iso=None):
    """A QDateEdit with a calendar popup that highlights TODAY."""
    de = QDateEdit()
    no_wheel(de)
    de.setCalendarPopup(True)
    de.setDisplayFormat("yyyy-MM-dd")
    if iso:
        d = QDate.fromString(iso, "yyyy-MM-dd")
        if d.isValid():
            de.setDate(d)
    cal = de.calendarWidget()
    if cal is not None:
        cal.setGridVisible(True)
        fmt = QTextCharFormat()
        fmt.setBackground(QColor(T.ACCENT))
        fmt.setForeground(QColor("#ffffff"))
        fmt.setFontWeight(QFont.Bold)
        cal.setDateTextFormat(QDate.currentDate(), fmt)   # highlight today
    return de


def _resource(name):
    """Path to a bundled resource in dev and inside a PyInstaller build."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


def _app_pixmap(size):
    """The app icon at `size` px — the generated PNG if present, else a drawn ₹ tile."""
    path = _resource("app_icon.png")
    if os.path.isfile(path):
        pm = QPixmap(path)
        if not pm.isNull():
            return pm.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    pm = QPixmap(size, size); pm.fill(Qt.transparent)
    p = QPainter(pm); p.setRenderHint(QPainter.Antialiasing); p.setPen(Qt.NoPen)
    r = int(size * 0.26)
    p.setBrush(QColor(T.ACCENT)); p.drawRoundedRect(1, 1, size - 2, size - 2, r, r)
    p.setPen(QColor("white")); f = QFont(T.FONT, int(size * 0.46)); f.setBold(True); p.setFont(f)
    p.drawText(pm.rect(), Qt.AlignCenter, "₹"); p.end()
    return pm


def make_icon():
    return QIcon(_app_pixmap(256))


# =================================================== splash / loading screen
def make_splash_pixmap(w=520, h=300):
    """The startup card: logo, name, tagline. The status line and loading bar are
    painted on top by Splash.drawContents()."""
    pm = QPixmap(w, h)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.SmoothPixmapTransform, True)

    card = QPainterPath()
    card.addRoundedRect(QRectF(0, 0, w, h), 18, 18)
    g = QLinearGradient(0, 0, w, h)
    g.setColorAt(0.0, QColor("#182034")); g.setColorAt(1.0, QColor(T.BG))
    p.fillPath(card, QBrush(g))
    p.setBrush(Qt.NoBrush); p.setPen(QPen(QColor(255, 255, 255, 28), 1))
    p.drawPath(card)

    icon = _app_pixmap(88)
    p.drawPixmap(int((w - 88) / 2), 40, icon)

    p.setPen(QColor(T.TEXT))
    f = QFont(T.FONT, 19); f.setBold(True); p.setFont(f)
    p.drawText(QRectF(0, 140, w, 34), Qt.AlignCenter, "WhoAteMySalary")

    p.setPen(QColor(T.MUTED))
    f2 = QFont(T.FONT, 10); p.setFont(f2)
    p.drawText(QRectF(0, 174, w, 20), Qt.AlignCenter, "where'd it go?")
    p.end()
    return pm


class Splash(QSplashScreen):
    """A proper startup splash: shows the logo while the app boots, with a status
    line and an indeterminate progress bar so it never looks frozen."""

    def __init__(self):
        super().__init__(make_splash_pixmap())
        self.setWindowFlags(Qt.SplashScreen | Qt.FramelessWindowHint |
                            Qt.WindowStaysOnTopHint)
        self._phase = 0.0
        self._msg = "Starting up…"

    def note(self, text):
        self._msg = text
        self.repaint()
        QApplication.processEvents()

    def tick(self, dt=0.03):
        self._phase = (self._phase + dt * 0.75) % 1.0
        self.repaint()
        QApplication.processEvents()

    def drawContents(self, p):
        p.setRenderHint(QPainter.Antialiasing, True)
        w, h = self.width(), self.height()

        p.setPen(QColor(T.TEXT2))
        f = QFont(T.FONT, 9); p.setFont(f)
        p.drawText(QRectF(0, h - 78, w, 20), Qt.AlignCenter, self._msg)

        bw, bh = 300.0, 4.0
        bx, by = (w - bw) / 2.0, h - 48.0
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 28))
        p.drawRoundedRect(QRectF(bx, by, bw, bh), 2, 2)

        seg = 96.0                       # the sliding highlight
        x = bx + (bw + seg) * self._phase - seg
        x0, x1 = max(bx, x), min(bx + bw, x + seg)
        if x1 > x0:
            p.setBrush(QColor(T.ACCENT))
            p.drawRoundedRect(QRectF(x0, by, x1 - x0, bh), 2, 2)


class TreeItem(QTreeWidgetItem):
    """Tree item with numeric-aware column sorting."""
    def __init__(self, values, sortvals=None):
        super().__init__([str(v) for v in values])
        self._sort = sortvals or {}
        self._merch = None
        self._row = None
        self._loaded = False

    def __lt__(self, other):
        tw = self.treeWidget()
        col = tw.sortColumn() if tw else 0
        a = self._sort.get(col)
        b = getattr(other, "_sort", {}).get(col)
        if a is not None and b is not None:
            return a < b
        return super().__lt__(other)


def cat_combo(current=""):
    cb = no_wheel(QComboBox())                 # Review scrolls — never re-tag by wheel
    cb.setEditable(True)                       # let users type / invent a category
    cb.setInsertPolicy(QComboBox.NoInsert)     # we persist new ones ourselves
    cb.addItems(EXPENSE_CATEGORIES)
    cb.insertSeparator(len(EXPENSE_CATEGORIES))
    cb.addItems(INCOME_CATEGORIES)
    customs = engine.custom_categories()
    if customs:
        cb.insertSeparator(cb.count())
        cb.addItems(customs)
    cb.setCurrentText(current or "")
    return cb


# =================================================== dialogs
class TagDialog(QDialog):
    def __init__(self, win, row, on_done=None):
        super().__init__(win)
        self.win, self.row, self.on_done = win, row, on_done
        self.setWindowTitle("Tag transaction")
        self.setMinimumWidth(440)
        v = QVBoxLayout(self); v.setContentsMargins(22, 20, 22, 20); v.setSpacing(6)
        sign = "+" if row["direction"] == "IN" else "−"
        col = T.GREEN if row["direction"] == "IN" else T.RED
        v.addWidget(lbl(f"{sign} ₹{T.inr(row['amount'])}", color=col, bold=True, size=22))
        v.addWidget(lbl((row.get("merchant") or "(transaction)"), bold=True, size=12))
        meta = f"{(row.get('bank') or row.get('source') or '')}  ·  {dt_str(row)}"
        v.addWidget(lbl(meta, color=T.MUTED, size=9))
        subj = (row.get("subject") or "")[:120]
        if subj:
            s = lbl(subj, color=T.TEXT2, size=9); s.setWordWrap(True); v.addWidget(s)
        v.addSpacing(6)
        v.addWidget(lbl("WHAT WAS THIS FOR?", color=T.MUTED, bold=True, size=8))
        self.cat = cat_combo(row.get("category") or row.get("guessed_category") or "")
        v.addWidget(self.cat)
        v.addWidget(lbl("NOTE (optional)", color=T.MUTED, bold=True, size=8))
        self.note = QLineEdit(row.get("note") or "")
        v.addWidget(self.note)
        v.addSpacing(10)
        row_b = QHBoxLayout()
        row_b.addWidget(btn("Save", self._save, "green"))
        row_b.addWidget(btn("Skip / ignore", self._ignore, "ghost"))
        row_b.addStretch(1)
        row_b.addWidget(btn("Cancel", self.reject, "ghost"))
        v.addLayout(row_b)

    def _save(self):
        cat = self.cat.currentText().strip()
        engine.add_custom_category(cat)          # persist if it's a brand-new category
        n = engine.tag_and_learn(self.row["id"], cat, self.note.text().strip())
        self.win.session_new_ids.discard(self.row["id"])
        if n > 1:
            self.win.toast("Applied to this payee",
                           f"Set '{cat}' on {n} transactions from {self.row.get('merchant') or 'this payee'}.", "in")
        self._finish()

    def _ignore(self):
        engine.tag(self.row["id"], self.row.get("category") or "", "", "ignored")
        self.win.session_new_ids.discard(self.row["id"])
        self._finish()

    def _finish(self):
        self.accept()
        self.win.refresh_after_change()
        if self.on_done:
            self.on_done()


class BulkDialog(QDialog):
    def __init__(self, win, ids, disp, on_done=None):
        super().__init__(win)
        self.win, self.ids, self.disp, self.on_done = win, ids, disp, on_done
        self.setWindowTitle("Tag merchant")
        self.setMinimumWidth(420)
        n = len([i for i in ids.split(",") if i.strip()])
        v = QVBoxLayout(self); v.setContentsMargins(22, 20, 22, 20); v.setSpacing(8)
        v.addWidget(lbl("Bulk-tag merchant", bold=True, size=14))
        v.addWidget(lbl(f"{disp}  ·  {n} transaction(s)", color=T.MUTED, size=10))
        v.addWidget(lbl("CATEGORY", color=T.MUTED, bold=True, size=8))
        self.cat = cat_combo()
        v.addWidget(self.cat)
        v.addSpacing(8)
        rb = QHBoxLayout()
        rb.addWidget(btn(f"Tag all {n}", self._save))
        rb.addStretch(1)
        rb.addWidget(btn("Cancel", self.reject, "ghost"))
        v.addLayout(rb)

    def _save(self):
        cat = self.cat.currentText().strip()
        if not cat:
            return
        engine.add_custom_category(cat)
        engine.set_category_many(self.ids.split(","), cat)
        engine.remember_merchant(self.disp, cat)   # learn this payee for next time
        self.accept()
        self.win.refresh_after_change()
        if self.on_done:
            self.on_done()


class TxnPopup(QDialog):
    """A cute little card for what a chart bar holds — one transaction shows its
    full details, several show the total plus a scrollable mini-list. Read-only:
    glance at it, then ✕ (or Esc) and it's gone. Pops up next to the pointer
    and can be dragged around."""

    def __init__(self, win, rows, context=""):
        super().__init__(win)
        self.rows = rows if isinstance(rows, list) else [rows]
        rows = self.rows = sorted(self.rows, key=lambda r: r.get("_dt") or "", reverse=True)
        self.setWindowFlags(self.windowFlags() | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setModal(True)
        self._drag = None
        out = rows[0]["direction"] != "IN"
        col = T.RED if out else T.GREEN
        total = sum(r["amount"] for r in rows)

        c = QFrame(); c.setObjectName("card")
        c.setStyleSheet(f"QFrame#card{{border-left:4px solid {col};}}")
        sh = QGraphicsDropShadowEffect(self)
        sh.setBlurRadius(28); sh.setOffset(0, 6); sh.setColor(QColor(0, 0, 0, 170))
        c.setGraphicsEffect(sh)
        outer = QVBoxLayout(self); outer.setContentsMargins(16, 16, 16, 16)
        outer.addWidget(c)

        v = QVBoxLayout(c); v.setContentsMargins(16, 12, 12, 14); v.setSpacing(5)
        top = QHBoxLayout(); top.setSpacing(8)
        top.addWidget(lbl("💸" if out else "💰", size=15))
        top.addWidget(lbl(("−" if out else "+") + "₹" + T.inr(total),
                          color=col, bold=True, size=16))
        top.addStretch(1)
        x = btn("✕", self.reject, "ghost")
        x.setFixedSize(26, 26)
        x.setStyleSheet("QPushButton{padding:0px; border-radius:13px; font-weight:400;}")
        x.setToolTip("Close (Esc)")
        top.addWidget(x, alignment=Qt.AlignTop)
        v.addLayout(top)

        if len(rows) == 1:
            r = rows[0]
            m = lbl((r.get("merchant") or "(transaction)")[:70], bold=True, size=12)
            m.setWordWrap(True)
            v.addWidget(m)
            v.addWidget(lbl(self._when(r), color=T.TEXT2, size=9))
            cat = r.get("category") or r.get("guessed_category") or "Uncategorised"
            pill = lbl(cat, bold=True, size=8)
            pill.setStyleSheet(f"background:{T.PANEL2}; color:{T.TEXT}; "
                               "border-radius:9px; padding:4px 10px;")
            pr = QHBoxLayout(); pr.setSpacing(6)
            pr.addWidget(pill)
            pr.addWidget(lbl(_bank_card(r), color=T.MUTED, size=9))
            pr.addStretch(1)
            v.addLayout(pr)
        else:
            v.addWidget(lbl(f"{len(rows)} transactions"
                            + (f"  ·  {context}" if context else ""),
                            color=T.MUTED, size=9))
            body = QWidget(); body.setStyleSheet("background:transparent;")
            bv = QVBoxLayout(body); bv.setContentsMargins(0, 0, 0, 0); bv.setSpacing(0)
            for i, r in enumerate(rows):
                if i:
                    sep = QFrame(); sep.setFixedHeight(1)
                    sep.setStyleSheet(f"background:{T.BORDER};")
                    bv.addWidget(sep)
                bv.addWidget(self._mini(r, col, out))
            if body.sizeHint().height() + 4 > 236:      # list will scroll —
                bv.setContentsMargins(0, 0, 14, 0)      # clear the scrollbar
            sa = QScrollArea()
            sa.setWidgetResizable(True)
            sa.setWidget(body)
            sa.setFrameShape(QFrame.NoFrame)
            sa.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            # the app-wide QSS paints scroll-area interiors page-colour; inside
            # the card they must stay see-through
            sa.setStyleSheet("QScrollArea{background:transparent;}"
                             "QScrollArea>QWidget>QWidget{background:transparent;}")
            sa.setFixedHeight(min(body.sizeHint().height() + 4, 236))
            v.addWidget(sa)

        self.setFixedWidth(340)
        self.adjustSize()

    def _mini(self, r, col, out):
        """One line of the multi-transaction list: merchant + when on the left,
        amount on the right."""
        w = QWidget(); w.setStyleSheet("background:transparent;")
        h = QHBoxLayout(w); h.setContentsMargins(0, 5, 0, 5); h.setSpacing(8)
        left = QVBoxLayout(); left.setSpacing(1)
        f = QFont(T.FONT, 10); f.setBold(True)
        name = lbl(QFontMetrics(f).elidedText(r.get("merchant") or "(transaction)",
                                              Qt.ElideRight, 170), bold=True, size=10)
        cat = (r.get("category") or r.get("guessed_category") or "")[:16]
        meta = lbl(self._when_short(r) + (f"  ·  {cat}" if cat else ""),
                   color=T.MUTED, size=8)
        # a long name must clip itself, never push the amount off the card
        name.setMinimumWidth(1); meta.setMinimumWidth(1)
        left.addWidget(name); left.addWidget(meta)
        h.addLayout(left, 1)
        h.addWidget(lbl(("−" if out else "+") + "₹" + T.inr(r["amount"]),
                        color=col, bold=True, size=11))
        return w

    @staticmethod
    def _when(r):
        s = dt_str(r)
        try:
            d = datetime.strptime(s, "%Y-%m-%d %H:%M")
            return f"{d:%a, %d %b %Y}  ·  {d:%H:%M}"
        except ValueError:
            return s

    @staticmethod
    def _when_short(r):
        s = dt_str(r)
        try:
            d = datetime.strptime(s, "%Y-%m-%d %H:%M")
            return f"{d:%d %b %y} · {d:%H:%M}"
        except ValueError:
            return s

    def showEvent(self, e):
        super().showEvent(e)
        # appear right where the user just clicked, kept fully on screen
        g = QCursor.pos()
        scr = QApplication.screenAt(g) or QApplication.primaryScreen()
        av = scr.availableGeometry()
        self.move(min(max(g.x() - self.width() // 2, av.left() + 8),
                      av.right() - self.width() - 8),
                  min(max(g.y() + 12, av.top() + 8),
                      av.bottom() - self.height() - 8))

    # frameless -> make the card draggable
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag = e.globalPos() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self._drag is not None and e.buttons() & Qt.LeftButton:
            self.move(e.globalPos() - self._drag)

    def mouseReleaseEvent(self, e):
        self._drag = None


class TxnDialog(QDialog):
    """Sortable, SEARCHABLE transaction list. Used for category drill-in, the
    money-in / money-out / all-transactions KPI cards, and dashboard search.
    The Analytics toggle swaps the list for charts + how-often stats."""
    def __init__(self, win, title, direction=None, category=None, search="", bucket=None,
                 rows=None):
        """rows: optional pre-selected transactions — the dialog then shows exactly
        those instead of querying (used when a chart bar is clicked)."""
        super().__init__(win)
        self.win, self.dir, self.cat, self.bucket = win, direction, category, bucket
        self.rows_override = rows
        self.setWindowTitle(title)
        self.resize(760, 620)
        self._visible = []
        self._an_dated, self._an_bucket, self._an_names = [], None, {}
        v = QVBoxLayout(self); v.setContentsMargins(18, 16, 18, 16); v.setSpacing(8)
        trow = QHBoxLayout()
        trow.addWidget(lbl(title, bold=True, size=14))
        trow.addStretch(1)
        self.an_btn = btn("📊  Analytics", self._toggle_view, "ghost")
        trow.addWidget(self.an_btn)
        v.addLayout(trow)
        self.sub = lbl("", color=T.MUTED, size=10)
        v.addWidget(self.sub)
        srow = QHBoxLayout()
        srow.addWidget(lbl("🔍", size=12))
        self.search = QLineEdit()
        self.search.setText(search)
        self.search.setPlaceholderText("Search by date, name or amount…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._apply)
        srow.addWidget(self.search)
        v.addLayout(srow)
        self.table = make_table(["Date & time", "Merchant", "Category", "Bank / card", "Amount"], stretch=1)
        self.table.setColumnWidth(0, 158)
        self.table.setColumnWidth(3, 150)
        self.table.doubleClicked.connect(self._dbl)
        tpage = QWidget(); tv = QVBoxLayout(tpage)
        tv.setContentsMargins(0, 0, 0, 0); tv.setSpacing(8)
        tv.addWidget(self.table, 1)
        tv.addWidget(lbl("Click a column header to sort · double-click a row to tag", color=T.MUTED, size=9))
        self.stack = QStackedWidget()
        self.stack.addWidget(tpage)
        self.stack.addWidget(self._build_analytics())
        v.addWidget(self.stack, 1)
        rb = QHBoxLayout(); rb.addStretch(1); rb.addWidget(btn("Close", self.reject, "ghost"))
        v.addLayout(rb)
        self.reload()
        self.search.setFocus()

    def reload(self):
        if self.rows_override is not None:
            self._rows = self.rows_override
        else:
            # inherits the dashboard's bank / card / filter scope
            self._rows = engine.txns_filtered(self.win.rng_from, self.win.rng_to,
                                              self.dir, self.cat, self.bucket,
                                              self.win.f_bank or None, self.win.f_card or None,
                                              self.win.f_source or None)
        for r in self._rows:
            r["_dt"] = dt_str(r)
        self._apply()

    def _hay(self, r):
        d = r.get("_dt") or dt_str(r)
        return " ".join([str(d), r.get("merchant") or "",
                         r.get("category") or r.get("guessed_category") or "",
                         r.get("bank") or r.get("source") or "",
                         f"{r['amount']:.0f}", f"{r['amount']:,.0f}"]).lower()

    def _apply(self):
        q = self.search.text().strip().lower()
        rows = self._rows if not q else [r for r in self._rows if q in self._hay(r)]
        t = self.table
        t.setSortingEnabled(False)
        t.setRowCount(len(rows))
        for i, r in enumerate(rows):
            t.setItem(i, 0, txt_item(r.get("_dt") or dt_str(r)))
            m = txt_item((r.get("merchant") or "")[:44]); m.setData(Qt.UserRole, r["id"])
            t.setItem(i, 1, m)
            t.setItem(i, 2, txt_item(r.get("category") or r.get("guessed_category") or "—"))
            t.setItem(i, 3, txt_item(_bank_card(r)))
            sign = "+" if r["direction"] == "IN" else "−"
            a = NumItem(sign + "₹" + T.inr(r["amount"]), r["amount"])
            a.setForeground(QColor(T.GREEN if r["direction"] == "IN" else T.TEXT))
            a.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            t.setItem(i, 4, a)
        t.setSortingEnabled(True)
        t.sortItems(0, Qt.DescendingOrder)      # newest first
        total = sum(r["amount"] for r in rows)
        if self.rows_override is not None:
            # a fixed bucket of rows — the window range doesn't describe it
            self.sub.setText(f"{len(rows)} transaction(s)  ·  ₹{T.inr(total)}"
                             + (f"   (filtered from {len(self._rows)})" if q else ""))
        else:
            scope = self.win.scope_text()
            self.sub.setText(f"{self.win.rng_from} → {self.win.rng_to}"
                             + (f"  ·  {scope}" if scope else "")
                             + f"  ·  {len(rows)} transaction(s)  ·  ₹{T.inr(total)}"
                             + (f"   (filtered from {len(self._rows)})" if q else ""))
        self._visible = rows
        if self.stack.currentIndex() == 1:      # analytics is showing — keep it live
            self._fill_analytics(rows, animate=False)

    def _dbl(self, idx):
        item = self.table.item(idx.row(), 1)
        rid = item.data(Qt.UserRole) if item else None
        r = next((x for x in self._rows if x["id"] == rid), None)
        if r:
            TagDialog(self.win, r, on_done=self.reload).exec_()

    # ---- analytics view
    WDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    WDAYS_FULL = ["Monday", "Tuesday", "Wednesday", "Thursday",
                  "Friday", "Saturday", "Sunday"]

    def _build_analytics(self):
        body = QWidget()
        av = QVBoxLayout(body); av.setContentsMargins(0, 0, 8, 0); av.setSpacing(10)
        self.an_note = lbl("", color=T.MUTED, size=9, wrap=True)
        av.addWidget(self.an_note)
        self.an_chips_w = QWidget(); self.an_chips_w.setStyleSheet("background:transparent;")
        self.an_chips = FlowLayout(self.an_chips_w, hspacing=8, vspacing=8, fill=True)
        av.addWidget(self.an_chips_w)

        c1 = card(); v1 = QVBoxLayout(c1); v1.setContentsMargins(14, 12, 14, 12)
        self.an_t1 = lbl("Spending over time", bold=True, size=11)
        v1.addWidget(self.an_t1)
        self.an_t1sub = lbl("", color=T.MUTED, size=8)
        v1.addWidget(self.an_t1sub)
        self.an_time = TimeBars(min_h=190)
        self.an_time.barClicked.connect(self._time_bar)
        v1.addWidget(self.an_time)
        av.addWidget(c1)

        c2 = card(); v2 = QVBoxLayout(c2); v2.setContentsMargins(14, 12, 14, 12)
        v2.addWidget(lbl("By day of week", bold=True, size=11))
        v2.addWidget(lbl("which weekdays this money moves on · click a bar to see those transactions",
                         color=T.MUTED, size=8))
        self.an_wday = TimeBars(min_h=150, color="#8b5cf6")
        self.an_wday.barClicked.connect(self._wday_bar)
        v2.addWidget(self.an_wday)
        av.addWidget(c2)

        c3 = card(); v3 = QVBoxLayout(c3); v3.setContentsMargins(14, 12, 14, 12)
        v3.addWidget(lbl("Top merchants", bold=True, size=11))
        self.an_merch = HBars(label_w=190, empty="no data")
        v3.addWidget(self.an_merch)
        av.addWidget(c3)
        av.addStretch(1)
        return scroll_area(body)

    def _toggle_view(self):
        to_analytics = self.stack.currentIndex() == 0
        self.stack.setCurrentIndex(1 if to_analytics else 0)
        self.an_btn.setText("≣  Transactions" if to_analytics else "📊  Analytics")
        if to_analytics:
            self._fill_analytics(self._visible)

    @staticmethod
    def _chip(title, value, sub=""):
        f = card(); cv = QVBoxLayout(f)
        cv.setContentsMargins(12, 9, 12, 9); cv.setSpacing(1)
        cv.addWidget(lbl(title, color=T.MUTED, bold=True, size=7))
        cv.addWidget(lbl(value, bold=True, size=11))
        if sub:
            cv.addWidget(lbl(sub, color=T.MUTED, size=8))
        return f

    def _fill_analytics(self, rows, animate=True):
        """Frequency + rhythm of the money in this list: how much, how often
        (gap between purchase days), when (timeline, weekday), and where (top
        merchants). Mixed lists analyse the money-out side; pure money-in lists
        analyse the incoming side."""
        outs = [r for r in rows if r["direction"] == "OUT"]
        kind = "money out"
        if not outs and rows:
            outs, kind = [r for r in rows if r["direction"] == "IN"], "money in"
        self.an_t1.setText(("Spending" if kind == "money out" else "Incoming") + " over time")

        while self.an_chips.count():
            it = self.an_chips.takeAt(0)
            w = it.widget()
            if w:
                w.deleteLater()

        if not outs:
            self.an_note.setText("Nothing to analyse — no transactions in this list.")
            self.an_t1sub.setText("")
            self._an_dated, self._an_bucket, self._an_names = [], None, {}
            self.an_time.setData([], {}, {}, animate=False)
            self.an_wday.setData([], {}, {}, animate=False)
            self.an_merch.setData([], animate=False)
            return

        note = f"Analysing the {len(outs)} {kind} transaction(s) in this list"
        if len(outs) != len(rows):
            note += f" (of the {len(rows)} shown)"
        self.an_note.setText(note + ". The search box above narrows this too.")

        total = sum(r["amount"] for r in outs)
        n = len(outs)
        dated = []
        for r in outs:
            try:
                dated.append((date.fromisoformat((r.get("_dt") or "")[:10]), r))
            except ValueError:
                continue
        udays = sorted({d for d, _ in dated})
        wd_tot = [0.0] * 7
        for d, r in dated:
            wd_tot[d.weekday()] += r["amount"]

        chips = [("TOTAL", "₹" + T.inr(total), ""),
                 ("TRANSACTIONS", str(n), ""),
                 ("AVG PER TRANSACTION", "₹" + T.inr(total / n), "")]
        start = end = None
        if udays:
            try:
                r_from, r_to = (date.fromisoformat(self.win.rng_from),
                                date.fromisoformat(self.win.rng_to))
            except ValueError:
                r_from, r_to = udays[0], udays[-1]
            # measure from the first purchase actually in view, so "All time"
            # doesn't dilute the averages with empty years
            start = max(r_from, udays[0])
            end = max(r_to, udays[-1])
            span = max(1, (end - start).days + 1)
            k = len(udays)
            if k >= 2:
                gap = (udays[-1] - udays[0]).days / (k - 1)
                how = "≈ daily" if gap < 1.5 else f"every ~{gap:.1f} days"
            else:
                how = "seen on one day only"
            word = "purchase" if kind == "money out" else "credit"
            chips += [("HOW OFTEN", how, f"average gap between {word} days"),
                      ("ACTIVE DAYS", f"{k} of {span}", f"{start:%d %b %y} → {end:%d %b %y}"),
                      ("MONTHLY PACE", "₹" + T.inr(total / span * 30.44),
                       "what this window extrapolates to")]
            bi = max(range(7), key=lambda i: wd_tot[i])
            chips.append(("BUSIEST WEEKDAY", self.WDAYS_FULL[bi], "₹" + T.inr(wd_tot[bi])))
        big = max(outs, key=lambda r: r["amount"])
        chips.append(("BIGGEST ONE", "₹" + T.inr(big["amount"]),
                      (big.get("merchant") or "—")[:24]))
        m_tot = {}
        for r in outs:
            m = (r.get("merchant") or "").strip() or "(no name)"
            m_tot[m] = m_tot.get(m, 0.0) + r["amount"]
        top = sorted(m_tot.items(), key=lambda x: -x[1])
        chips.append(("TOP MERCHANT", top[0][0][:24],
                      f"₹{T.inr(top[0][1])}  ·  {top[0][1] / total * 100:.0f}% of the total"))
        for c in chips:
            self.an_chips.addWidget(self._chip(*c))

        # timeline — bucket size picked from the window the data actually spans
        keys, vals, names = [], {}, {}
        sub1, bucket = "", None
        if udays:
            span = (end - start).days + 1
            if span <= 70:
                sub1 = "per day"
                cur = start
                while cur <= end:
                    kk = cur.isoformat()
                    keys.append(kk); names[kk] = f"{cur.day} {cur:%b}"
                    cur += timedelta(days=1)
                bucket = lambda d: d.isoformat()
            elif span <= 430:
                sub1 = "per week (label = week start)"
                cur = start - timedelta(days=start.weekday())
                stop = end - timedelta(days=end.weekday())
                while cur <= stop:
                    kk = cur.isoformat()
                    keys.append(kk); names[kk] = f"{cur.day} {cur:%b}"
                    cur += timedelta(days=7)
                bucket = lambda d: (d - timedelta(days=d.weekday())).isoformat()
            else:
                sub1 = "per month"
                cur = date(start.year, start.month, 1)
                while cur <= end:
                    kk = cur.strftime("%Y-%m")
                    keys.append(kk); names[kk] = cur.strftime("%b %y")
                    cur = date(cur.year + (cur.month == 12), cur.month % 12 + 1, 1)
                bucket = lambda d: d.strftime("%Y-%m")
            for d, r in dated:
                b = bucket(d)
                vals[b] = vals.get(b, 0.0) + r["amount"]
        # remembered so a clicked bar can pop up exactly its transactions
        self._an_dated, self._an_bucket, self._an_names = dated, bucket, names
        self.an_t1sub.setText(sub1 + (" · click a bar to see those transactions" if keys else ""))
        self.an_time.setData(keys, vals, names, animate=animate)
        self.an_wday.setData(list(range(7)), {i: wd_tot[i] for i in range(7)},
                             {i: self.WDAYS[i] for i in range(7)}, animate=animate)
        self.an_merch.setData([((m[:21] + "…") if len(m) > 22 else m, v, T.PAL[i % len(T.PAL)])
                               for i, (m, v) in enumerate(top[:8])], animate=animate)

    def _time_bar(self, key):
        """A clicked timeline bar -> the little card with that day/week/month's
        transaction(s); several scroll inside it."""
        if not self._an_bucket:
            return
        rows = [r for d, r in self._an_dated if self._an_bucket(d) == key]
        if rows:
            TxnPopup(self.win, rows, context=str(self._an_names.get(key, key))).exec_()

    def _wday_bar(self, wd):
        """A clicked weekday bar -> the little card with that weekday's txns."""
        rows = [r for d, r in getattr(self, "_an_dated", []) if d.weekday() == wd]
        if rows:
            TxnPopup(self.win, rows, context=f"{self.WDAYS_FULL[wd]}s").exec_()


class ExportDialog(QDialog):
    """Statement export for whatever the dashboard is currently showing — the date
    range and the bank / card / filter scope. Date · Reference · Description ·
    Amount · Closing balance, ordered however you pick, as PDF or CSV."""

    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.rows = []
        self.setWindowTitle("Export statement")
        self.resize(900, 660)
        v = QVBoxLayout(self); v.setContentsMargins(18, 16, 18, 16); v.setSpacing(8)
        v.addWidget(lbl("Export statement", bold=True, size=14))
        self.sub = lbl("", color=T.MUTED, size=10)
        v.addWidget(self.sub)

        row = QHBoxLayout()
        row.addWidget(lbl("ORDER BY", color=T.MUTED, bold=True, size=9))
        self.cb_sort = no_wheel(QComboBox())
        self.cb_sort.setMinimumWidth(210)
        for key, label, _f, _r in engine.STATEMENT_SORTS:
            self.cb_sort.addItem(label, key)
        self.cb_sort.currentIndexChanged.connect(self.reload)
        row.addWidget(self.cb_sort)
        row.addStretch(1)
        row.addWidget(btn("Save PDF", self._pdf))
        row.addWidget(btn("Save CSV", self._csv, "ghost"))
        v.addLayout(row)

        self.table = make_table(["Date", "Reference", "Description", "Amount",
                                 "Closing balance"], stretch=2)
        # the balance accumulates down the rows, so the order must stay as exported
        self.table.setSortingEnabled(False)
        self.table.setColumnWidth(0, 100)
        self.table.setColumnWidth(1, 130)
        self.table.setColumnWidth(3, 120)
        self.table.setColumnWidth(4, 140)
        v.addWidget(self.table, 1)
        v.addWidget(lbl("Closing balance runs down the rows in the order shown — money in adds, "
                        "money out subtracts. Re-order above and it re-accumulates.",
                        color=T.MUTED, size=9))
        rb = QHBoxLayout(); rb.addStretch(1); rb.addWidget(btn("Close", self.reject, "ghost"))
        v.addLayout(rb)
        self.reload()

    # ---- data
    def reload(self):
        self.rows = engine.statement(self.win.rng_from, self.win.rng_to,
                                     self.win.f_bank or None, self.win.f_card or None,
                                     self.win.f_source or None,
                                     sort=self.cb_sort.currentData())
        closing = self.rows[-1]["balance"] if self.rows else 0.0
        self.sub.setText(f"{self.win.rng_from} → {self.win.rng_to}  ·  "
                         f"{self.win.scope_text() or 'every bank & card'}  ·  "
                         f"{len(self.rows)} transaction(s)  ·  closing balance ₹{T.inr2(closing)}")
        t = self.table
        t.setRowCount(len(self.rows))
        for i, r in enumerate(self.rows):
            t.setItem(i, 0, txt_item(r["date"] or "—"))
            t.setItem(i, 1, txt_item(r["ref"] or "—"))
            t.setItem(i, 2, txt_item(r["description"][:70]))
            for col, val in ((3, r["amount"]), (4, r["balance"])):
                it = txt_item(T.inr2(val))
                it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                it.setForeground(QColor(T.GREEN if val >= 0 else T.TEXT))
                t.setItem(i, col, it)

    def _default_name(self, ext):
        bits = ["statement", self.win.rng_from, "to", self.win.rng_to]
        for part in (self.win.f_bank, self.win.f_card, self.win.f_source):
            if part:
                bits.append(re.sub(r"[^A-Za-z0-9]+", "-", part).strip("-"))
        return "_".join(b for b in bits if b) + "." + ext

    def _ask_path(self, label, ext):
        start = os.path.join(os.path.dirname(os.path.abspath(__file__)), self._default_name(ext))
        path, _ = QFileDialog.getSaveFileName(self, f"Save {label}", start,
                                              f"{label} files (*.{ext})")
        if path and not path.lower().endswith("." + ext):
            path += "." + ext
        return path

    def _saved(self, path):
        QMessageBox.information(self, "Exported",
                                f"{len(self.rows)} transaction(s) saved to:\n{path}")

    # ---- writers
    def _csv(self):
        path = self._ask_path("CSV", "csv")
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                w.writerow(["Date", "Reference", "Description", "Amount", "Closing balance",
                            "Category", "Direction", "Bank", "Card", "Date & time"])
                for r in self.rows:
                    w.writerow([r["date"], r["ref"], r["description"],
                                f'{r["amount"]:.2f}', f'{r["balance"]:.2f}',
                                r["category"], r["direction"], r["bank"], r["card"],
                                r["datetime"]])
            self._saved(path)
        except Exception as e:
            QMessageBox.critical(self, "Export failed", str(e))

    def _pdf(self):
        path = self._ask_path("PDF", "pdf")
        if not path:
            return
        try:
            from PyQt5.QtPrintSupport import QPrinter
        except ImportError:
            QMessageBox.critical(self, "PDF unavailable",
                                 "QtPrintSupport isn't installed, so PDF export can't run.\n"
                                 "Save as CSV instead.")
            return
        try:
            doc = QTextDocument()
            d = self._summary()
            donut = charts.render_donut(
                d["spend"], px=900, center_top="spending",
                center_big="Rs " + T.lakh(d["tout"]))
            doc.addResource(QTextDocument.ImageResource, QUrl(DONUT_RES), donut)
            doc.setHtml(self._html(d))
            pr = QPrinter(QPrinter.HighResolution)
            pr.setOutputFormat(QPrinter.PdfFormat)
            pr.setOutputFileName(path)
            pr.setPageSize(QPrinter.A4)
            pr.setPageMargins(12, 12, 12, 14, QPrinter.Millimeter)
            # no setPageSize() on the document — print_() paginates against the
            # printer's page and scales for its DPI. Forcing the page to the
            # high-resolution device rect lays every row onto one giant page.
            doc.print_(pr)
            self._saved(path)
        except Exception as e:
            QMessageBox.critical(self, "Export failed", str(e))

    def _summary(self):
        """The same numbers the dashboard is showing, for the report's first page."""
        return engine.build_dashboard(self.win.rng_from or None, self.win.rng_to or None,
                                      self.win.f_bank or None, self.win.f_card or None,
                                      self.win.f_source or None)

    @staticmethod
    def _kpi(label, value, color):
        return (f'<td width="20%" align="center" style="background-color:#f6f8fc;">'
                f'<font size="1" color="{color}"><b>{label.upper()}</b></font><br>'
                f'<font size="5"><b>{value}</b></font></td>')

    def _html(self, d):
        """Printable report — light-on-white, this goes on paper not on the dark UI.
        Page 1 summarises (totals, donut, category split); the ledger follows."""
        e = escape
        scope = e(self.win.scope_text()) if self.win.scope_text() else "All banks &amp; cards"
        closing = self.rows[-1]["balance"] if self.rows else 0.0

        kpis = "".join([
            self._kpi("Money out", "Rs " + T.lakh(d["tout"]), "#c2410c"),
            self._kpi("Card bills", "Rs " + T.lakh(d["cc_bills"]), "#7c3aed"),
            self._kpi("Money in", "Rs " + T.lakh(d["tin"]), "#15803d"),
            self._kpi("Net", "Rs " + T.lakh(d["net"]), "#1d4ed8"),
            self._kpi("Transactions", f'{d["rows_n"]:,}', "#a16207"),
        ])

        # category split — the donut's legend, as a table
        tout = d["tout"] or 1
        cats = []
        for cat, val, color in d["spend"]:
            cats.append(
                "<tr>"
                f'<td width="3%" bgcolor="{color}" style="background-color:{color};">&nbsp;</td>'
                f'<td>{e(cat[:34])}</td>'
                f'<td align="right">{d["spend_n"].get(cat, 0):,}</td>'
                f'<td align="right">{val / tout * 100:.1f}%</td>'
                f'<td align="right"><b>{e(T.inr2(val))}</b></td>'
                "</tr>")
        if not cats:
            cats.append('<tr><td colspan="5"><i>No spending in this period.</i></td></tr>')

        # incoming, when there is any
        income = ""
        if d["income"]:
            rows = "".join(
                "<tr>"
                f'<td width="6%" bgcolor="{color}" style="background-color:{color};">&nbsp;</td>'
                f'<td>{e(cat[:24])}</td>'
                f'<td align="right">{d["income_n"].get(cat, 0):,}</td>'
                f'<td align="right"><b>{e(T.inr2(val))}</b></td>'
                "</tr>" for cat, val, color in d["income"])
            # sits under the donut: uses the dead space and keeps the heading with
            # its table instead of orphaning it at a page foot
            income = f"""
<p style="margin:16px 0 4px 0; font-size:9.5pt;"><b>Incoming by source</b></p>
<table width="100%" cellspacing="0" cellpadding="4" border="1"
       style="border-collapse:collapse; font-size:8.5pt; border-color:#ccc;">
<tr style="background-color:#eef1f7;"><td width="6%">&nbsp;</td><td><b>Source</b></td>
  <td align="right"><b>Txns</b></td><td align="right" width="38%"><b>Total</b></td></tr>
{rows}</table>"""

        led = []
        for i, r in enumerate(self.rows):
            bg = ' bgcolor="#eef2f8"' if i % 2 else ''       # stripe long ledgers
            amt = e(T.inr2(r["amount"]))
            if r["amount"] > 0:                              # credits stand out
                amt = f'<font color="#15803d"><b>+{amt}</b></font>'
            led.append(
                "<tr>"
                f'<td{bg}>{e(r["date"] or "")}</td>'
                f'<td{bg}>{e(r["ref"]) if r["ref"] else "&ndash;"}</td>'
                f'<td{bg}>{e(r["description"][:70])}</td>'
                f'<td{bg} align="right">{amt}</td>'
                f'<td{bg} align="right">{e(T.inr2(r["balance"]))}</td>'
                "</tr>")
        ledger = "".join(led)

        return f"""
<html><body style="font-family:Segoe UI,Arial,sans-serif; color:#111;">

<h2 style="margin:0 0 3px 0;">Spending report</h2>
<p style="margin:0 0 12px 0; font-size:9pt; color:#555;">
  {e(self.win.rng_from)} to {e(self.win.rng_to)} &nbsp;&middot;&nbsp; {scope}</p>

<table width="100%" cellspacing="4" cellpadding="7" border="0">
  <tr>{kpis}</tr>
</table>

<h3 style="margin:18px 0 4px 0; font-size:11pt;">Where the money went</h3>
<table width="100%" cellspacing="0" cellpadding="0" border="0"><tr>
  <td width="38%" valign="top" align="center">
    <img src="{DONUT_RES}" width="215" height="215">
    {income}
  </td>
  <td width="62%" valign="top">
    <table width="100%" cellspacing="0" cellpadding="4" border="1"
           style="border-collapse:collapse; font-size:8.5pt; border-color:#ccc;">
    <tr style="background-color:#eef1f7;"><td width="3%">&nbsp;</td><td><b>Category</b></td>
      <td align="right" width="14%"><b>Txns</b></td><td align="right" width="14%"><b>Share</b></td>
      <td align="right" width="26%"><b>Total</b></td></tr>
    {"".join(cats)}
    </table>
  </td>
</tr></table>

<h3 style="page-break-before:always; margin:0 0 3px 0; font-size:11pt;">Transactions</h3>
<p style="margin:0 0 8px 0; font-size:8.5pt; color:#555;">
  Ordered by {e(self.cb_sort.currentText())} &middot; {len(self.rows)} transaction(s) &middot;
  <b>closing balance Rs {e(T.inr2(closing))}</b></p>
<table width="100%" cellspacing="0" cellpadding="3" border="1"
       style="border-collapse:collapse; font-size:8.5pt; border-color:#bbb;">
<thead><tr style="background-color:#eef1f7; font-weight:bold;">
  <td width="14%">Date</td><td width="16%">Reference</td><td>Description</td>
  <td width="14%" align="right">Amount</td><td width="16%" align="right">Closing balance</td>
</tr></thead>
<tbody>{ledger}</tbody>
</table>
<p style="margin-top:10px; font-size:7.5pt; color:#777;">
  Closing balance accumulates down the rows in the order shown: money in adds, money out
  subtracts. Credit-card bill payments are counted in their own bucket, not as spending.
  Generated by WhoAteMySalary from bank e-mail alerts &mdash; not a bank document.</p>
</body></html>"""


class SourceDialog(QDialog):
    """Edit an existing tracked source (filter)."""
    def __init__(self, win, src, on_done=None):
        super().__init__(win)
        self.win, self.orig, self.on_done = win, src.get("name", ""), on_done
        self.setWindowTitle("Edit source")
        self.setMinimumWidth(460)
        m, p = mailreader.effective_mode(src)
        v = QVBoxLayout(self); v.setContentsMargins(22, 20, 22, 20); v.setSpacing(8)
        v.addWidget(lbl("Edit tracked source (filter)", bold=True, size=14))
        v.addWidget(lbl("An email is tracked when it matches this. 'both' checks the primary field first.",
                        color=T.MUTED, size=9))
        self.e_name = QLineEdit(src.get("name", ""))
        self.e_from = QLineEdit(src.get("from_contains", ""))
        self.e_subj = QLineEdit(src.get("subject_contains", ""))
        self.e_match = no_wheel(QComboBox()); self.e_match.addItems(["both", "from", "subject", "either"]); self.e_match.setCurrentText(m)
        self.e_primary = no_wheel(QComboBox()); self.e_primary.addItems(["from", "subject"]); self.e_primary.setCurrentText(p)
        v.addSpacing(4)
        for t, w in [("Name", self.e_name), ("From contains", self.e_from),
                     ("Subject contains", self.e_subj), ("Match", self.e_match),
                     ("Primary", self.e_primary)]:
            v.addLayout(_form_row(t, w))
        v.addSpacing(6)
        rb = QHBoxLayout()
        rb.addWidget(btn("Save changes", self._save))
        rb.addStretch(1)
        rb.addWidget(btn("Cancel", self.reject, "ghost"))
        v.addLayout(rb)

    def _save(self):
        name = self.e_name.text().strip()
        if not name or not (self.e_from.text().strip() or self.e_subj.text().strip()):
            QMessageBox.information(self, "Missing", "Give a name and at least a from/subject filter.")
            return
        cfg = config.load()
        for s in cfg.get("sources", []):
            if s.get("name") == self.orig:
                s["name"] = name
                s["from_contains"] = self.e_from.text().strip()
                s["subject_contains"] = self.e_subj.text().strip()
                s["match"] = self.e_match.currentText()
                s["primary"] = self.e_primary.currentText()
                break
        config.save(cfg)
        mailreader.apply_custom(cfg)
        self.accept()
        if self.on_done:
            self.on_done()


class ActivityLog(QDialog):
    """Live, non-modal log of what the background checker is doing."""
    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.setWindowTitle("Activity & logs")
        self.resize(720, 460)
        v = QVBoxLayout(self); v.setContentsMargins(18, 16, 18, 16); v.setSpacing(8)
        v.addWidget(lbl("Live activity — what the checker is doing", bold=True, size=13))
        v.addWidget(lbl("Updates in real time each time it checks your mailboxes for new transactions.",
                        color=T.MUTED, size=9))
        self.box = QPlainTextEdit(); self.box.setReadOnly(True)
        self.box.setStyleSheet(f"background:{T.PANEL2}; font-family:Consolas; font-size:9pt; color:{T.TEXT2};")
        v.addWidget(self.box, 1)
        row = QHBoxLayout()
        row.addWidget(btn("⟳  Check now", self.win.check_now))
        row.addWidget(btn("🔔  Test notification", self.win.send_test_notification, "ghost"))
        row.addStretch(1)
        row.addWidget(btn("Close", self.reject, "ghost"))
        v.addLayout(row)

    def set_lines(self, lines):
        self.box.setPlainText("\n".join(lines))
        self._scroll()

    def append(self, line):
        self.box.appendPlainText(line)
        self._scroll()

    def _scroll(self):
        sb = self.box.verticalScrollBar()
        sb.setValue(sb.maximum())


# =================================================== pages
class Page(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.build()

    def build(self):
        pass

    def on_show(self):
        pass


class OverviewPage(Page):
    def build(self):
        body = QWidget()
        self.v = QVBoxLayout(body); self.v.setContentsMargins(0, 0, 8, 0); self.v.setSpacing(14)
        self._sig = None

        # date range bar — wraps onto extra rows when the window is narrow
        bar = card(); bh = FlowLayout(bar); bh.setContentsMargins(14, 10, 14, 10)
        bh.addWidget(lbl("PERIOD", color=T.MUTED, bold=True, size=9))
        for txt, fn in [("Last 2d", lambda: self._last(2)), ("Last 7d", lambda: self._last(7)),
                        ("Last 30d", lambda: self._last(30)), ("Last 90d", lambda: self._last(90)),
                        ("This month", self._month), ("This year", self._year), ("All time", self._all)]:
            bh.addWidget(btn(txt, fn, "ghost"))
        bh.add_stretch()
        self.de_from = date_edit()
        self.de_to = date_edit()
        self.de_from.dateChanged.connect(self._apply)
        self.de_to.dateChanged.connect(self._apply)
        bh.addWidget(hgroup(lbl("Range:", color=T.MUTED, bold=True, size=9),
                            self.de_from, lbl("to", color=T.MUTED), self.de_to))
        self.v.addWidget(bar)

        # scope bar — narrow the whole dashboard to one bank / card / filter
        scbar = card(); ph = FlowLayout(scbar); ph.setContentsMargins(14, 10, 14, 10)
        ph.addWidget(lbl("SHOW", color=T.MUTED, bold=True, size=9))
        self.cb_bank = self._scope_combo("All banks")
        self.cb_card = self._scope_combo("All cards")
        self.cb_src = self._scope_combo("All filters")
        for name, cb in (("Bank", self.cb_bank), ("Card", self.cb_card), ("Filter", self.cb_src)):
            ph.addWidget(hgroup(lbl(name, color=T.MUTED, size=9), cb))
        ph.addWidget(btn("Reset", self._scope_reset, "ghost"))
        ph.add_stretch()
        self.scope_note = lbl("", color=T.MUTED, size=9)
        ph.addWidget(self.scope_note)
        ph.addWidget(btn("See these transactions", self._scope_txns))
        ph.addWidget(btn("Export…", self._export, "ghost"))
        self.v.addWidget(scbar)

        # global search across all transactions
        sbar = card(); sh = QHBoxLayout(sbar); sh.setContentsMargins(14, 8, 14, 8)
        sh.addWidget(lbl("🔍  SEARCH", color=T.MUTED, bold=True, size=9))
        self.search = QLineEdit()
        self.search.setPlaceholderText("Find any transaction by date, name or amount…  (press Enter)")
        self.search.setClearButtonEnabled(True)
        self.search.returnPressed.connect(self._do_search)
        sh.addWidget(self.search, 1)
        sh.addWidget(btn("Search", self._do_search))
        self.v.addWidget(sbar)

        # KPI row — cards wrap onto a second row when the window is narrow
        kw = QWidget(); kw.setStyleSheet("background:transparent;")
        krow = FlowLayout(kw, hspacing=12, vspacing=12, fill=True)
        self.k_out = KPICard("Money out", T.RED)
        self.k_cc = KPICard("Credit card bills", "#8b5cf6")
        self.k_in = KPICard("Money in", T.GREEN)
        self.k_net = KPICard("Net", T.ACCENT)
        self.k_n = KPICard("Transactions", T.YELLOW)
        for k in (self.k_out, self.k_cc, self.k_in, self.k_net, self.k_n):
            krow.addWidget(k)
        # click a card -> its transactions (searchable). money-in/out exclude CC bills.
        self.k_out.clicked.connect(lambda: self.win.open_txns("Money out", bucket="out"))
        self.k_cc.clicked.connect(lambda: self.win.open_txns("Credit Card bills", bucket="cc"))
        self.k_in.clicked.connect(lambda: self.win.open_txns("Money in", bucket="in"))
        self.k_net.clicked.connect(lambda: self.win.open_txns("All transactions"))
        self.k_n.clicked.connect(lambda: self.win.open_txns("All transactions"))
        self.v.addWidget(kw)
        self.v.addWidget(lbl("Tip: click a card above to see its transactions (searchable).",
                             color=T.MUTED, size=8))

        # donut + category habits — side by side, stacking vertically on narrow windows
        mw = QWidget(); mw.setStyleSheet("background:transparent;")
        mid = FlowLayout(mw, hspacing=12, vspacing=12, fill=True)
        dcard = card(); dv = QVBoxLayout(dcard); dv.setContentsMargins(16, 14, 16, 14)
        dv.addWidget(lbl("Where the money went", bold=True, size=12))
        dv.addWidget(lbl("click a slice or a legend row to see the transactions", color=T.MUTED, size=9))
        drow = QHBoxLayout()
        self.donut = DonutChart(size=230)
        self.donut.sliceClicked.connect(lambda c: self.win.open_category(c, "OUT"))
        drow.addWidget(self.donut)
        self.legend = QVBoxLayout(); self.legend.setSpacing(3)
        lw = QWidget(); lw.setLayout(self.legend)
        drow.addWidget(lw, 1)
        dv.addLayout(drow)
        mid.addWidget(dcard)

        mcard = card(); mv = QVBoxLayout(mcard); mv.setContentsMargins(16, 14, 16, 14)
        mv.addWidget(lbl("Category habits", bold=True, size=12))
        mv.addWidget(lbl("how often each category gets used in this period · double-click to open it",
                         color=T.MUTED, size=9))
        self.habits = make_table(["Category", "Times", "/ month", "Quietest", "Busiest"], stretch=0)
        for col, w in ((1, 58), (2, 66), (3, 102), (4, 102)):
            self.habits.setColumnWidth(col, w)
        self.habits.setMinimumHeight(250)
        self.habits.doubleClicked.connect(self._habit_dbl)
        mv.addWidget(self.habits, 1)
        mid.addWidget(mcard)
        self.v.addWidget(mw)

        # income
        icard = card(); iv = QVBoxLayout(icard); iv.setContentsMargins(16, 14, 16, 14)
        iv.addWidget(lbl("Incoming by source", bold=True, size=12))
        self.income = HBars()
        iv.addWidget(self.income)
        self.v.addWidget(icard)

        # merchants (expandable)
        mccard = card(); mcv = QVBoxLayout(mccard); mcv.setContentsMargins(16, 14, 16, 14)
        htop = QHBoxLayout()
        htop.addWidget(lbl("Top merchants", bold=True, size=12))
        htop.addStretch(1)
        htop.addWidget(btn("Bulk-tag selected", self._bulk_selected, "ghost"))
        mcv.addLayout(htop)
        mcv.addWidget(lbl("click ▸ to expand a merchant into its transactions · double-click a transaction to tag it",
                          color=T.MUTED, size=9))
        self.tree = QTreeWidget()
        self.tree.setColumnCount(4)
        self.tree.setHeaderLabels(["Merchant", "Txns", "Total", "Category"])
        self.tree.setSortingEnabled(True)
        self.tree.setAlternatingRowColors(True)
        self.tree.setRootIsDecorated(True)
        self.tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tree.header().setHighlightSections(False)
        self.tree.itemExpanded.connect(self._expand)
        self.tree.itemDoubleClicked.connect(self._tree_dbl)
        self.tree.setMinimumHeight(280)
        mcv.addWidget(self.tree)
        self.v.addWidget(mccard)

        # highlighted
        hcard = card(); hv = QVBoxLayout(hcard); hv.setContentsMargins(16, 14, 16, 14)
        hv.addWidget(lbl("Highlighted — single transactions over ₹1,000", bold=True, size=12))
        self.large = make_table(["Date & time", "Merchant", "Category", "Amount"], stretch=1)
        self.large.setColumnWidth(0, 158)
        self.large.doubleClicked.connect(self._large_dbl)
        self.large.setMinimumHeight(260)
        hv.addWidget(self.large)
        self.v.addWidget(hcard)

        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll_area(body))

    # ---- range helpers
    def _qd(self, iso):
        d = QDate.fromString(iso, "yyyy-MM-dd")
        return d if d.isValid() else QDate.currentDate()

    def _set_dates(self, frm, to):
        for de, val in ((self.de_from, frm), (self.de_to, to)):
            self._set_one(de, self._qd(val))

    def _all(self):
        self.win.rng_from, self.win.rng_to = "2000-01-01", date.today().isoformat()
        self._set_dates(self.win.rng_from, self.win.rng_to); self.refresh()

    def _month(self):
        t = date.today()
        self.win.rng_from, self.win.rng_to = t.replace(day=1).isoformat(), t.isoformat()
        self._set_dates(self.win.rng_from, self.win.rng_to); self.refresh()

    def _year(self):
        y = date.today().year
        self.win.rng_from, self.win.rng_to = f"{y}-01-01", date.today().isoformat()
        self._set_dates(self.win.rng_from, self.win.rng_to); self.refresh()

    def _last(self, days):
        from datetime import timedelta
        self.win.rng_from = (date.today() - timedelta(days=days)).isoformat()
        self.win.rng_to = date.today().isoformat()
        self._set_dates(self.win.rng_from, self.win.rng_to); self.refresh()

    def _apply(self):
        frm, to = self.de_from.date(), self.de_to.date()
        if frm > to:
            # dragging one end past the other pushes the other along, rather than
            # leaving an inverted range that silently matches nothing
            if self.sender() is self.de_to:
                self._set_one(self.de_from, to); frm = to
            else:
                self._set_one(self.de_to, frm); to = frm
        self.win.rng_from = frm.toString("yyyy-MM-dd")
        self.win.rng_to = to.toString("yyyy-MM-dd")
        self.refresh()

    @staticmethod
    def _set_one(de, qdate):
        de.blockSignals(True); de.setDate(qdate); de.blockSignals(False)

    # ---- scope (bank / card / filter)
    def _scope_combo(self, all_label):
        cb = no_wheel(QComboBox())
        cb.setMinimumWidth(140)
        cb.addItem(all_label, "")
        cb.currentIndexChanged.connect(self._scope_changed)
        return cb

    @staticmethod
    def _fill_combo(cb, all_label, items, current):
        """Refill a picker, re-selecting `current` if it's still on offer.
        Returns the value actually selected — '' when the old one is gone."""
        cb.blockSignals(True)
        cb.clear()
        cb.addItem(all_label, "")
        for value, label in items:
            cb.addItem(label, value)
        i = cb.findData(current)
        cb.setCurrentIndex(i if i >= 0 else 0)
        cb.blockSignals(False)
        return cb.currentData() or ""

    def _load_scope(self):
        """(Re)fill the pickers from what's actually in the DB. A chosen bank narrows
        the card + filter lists, and a chosen filter narrows the cards, so the pickers
        can never be combined into an empty selection."""
        o = engine.filter_options()
        # each picker is resolved before it narrows the next one, so a bank change
        # that invalidates the filter can't leave the card list narrowed by it
        bank = self.win.f_bank = self._fill_combo(
            self.cb_bank, "All banks",
            [(b["value"], f'{b["value"]}  ({b["n"]:,})') for b in o["banks"]], self.win.f_bank)
        src = self.win.f_source = self._fill_combo(
            self.cb_src, "All filters",
            [(s["value"], f'{s["value"]}  ({s["n"]:,})') for s in o["sources"]
             if not bank or s["bank"] == bank], self.win.f_source)
        self.win.f_card = self._fill_combo(
            self.cb_card, "All cards",
            [(c["value"], "••••" + c["value"]
              + (f'  ·  {c["bank"]}' if c["bank"] and not bank else "") + f'  ({c["n"]:,})')
             for c in o["cards"]
             if (not bank or c["bank"] == bank) and (not src or src in c["sources"])],
            self.win.f_card)

    def _scope_changed(self):
        self.win.f_bank = self.cb_bank.currentData() or ""
        self.win.f_card = self.cb_card.currentData() or ""
        self.win.f_source = self.cb_src.currentData() or ""
        self._load_scope()          # a new bank re-narrows the card / filter lists
        self.refresh()

    def _scope_reset(self):
        self.win.f_bank = self.win.f_card = self.win.f_source = ""
        self._load_scope()
        self.refresh()

    def _scope_txns(self):
        self.win.open_txns(self.win.scope_text() or "All transactions")

    def _export(self):
        ExportDialog(self.win).exec_()

    def _do_search(self):
        self.win.open_txns("Search results", search=self.search.text().strip())

    def _bulk_selected(self):
        it = self.tree.currentItem()
        while it is not None and getattr(it, "_merch", None) is None:
            it = it.parent()
        if it is None:
            QMessageBox.information(self.win, "Pick a merchant", "Select a merchant row first, then Bulk-tag.")
            return
        m = it._merch
        self.win.open_bulk(m["ids"], m["disp"], on_done=self.refresh)

    # ---- tree
    def _expand(self, item):
        if getattr(item, "_merch", None) is None or item._loaded:
            return
        item._loaded = True
        item.takeChildren()
        for r in sorted(item._merch["rows"], key=lambda r: -(r.get("amount") or 0)):
            d = dt_str(r)
            sign = "+" if r["direction"] == "IN" else "−"
            ch = TreeItem([d, "", sign + "₹" + T.inr(r["amount"]),
                           (r.get("category") or r.get("guessed_category") or "")[:36]],
                          sortvals={2: r["amount"]})
            ch._row = r
            ch.setForeground(2, QColor(T.GREEN if r["direction"] == "IN" else T.TEXT2))
            item.addChild(ch)

    def _tree_dbl(self, item, col):
        if getattr(item, "_row", None) is not None:
            TagDialog(self.win, item._row, on_done=self.refresh).exec_()

    def _large_dbl(self, idx):
        item = self.large.item(idx.row(), 1)
        rid = item.data(Qt.UserRole) if item else None
        r = next((x for x in self._large_rows if x["id"] == rid), None)
        if r:
            TagDialog(self.win, r, on_done=self.refresh).exec_()

    def on_show(self):
        if self.win.rng_from and self.win.rng_to:
            self._set_dates(self.win.rng_from, self.win.rng_to)
        self._load_scope()
        self.refresh()

    def refresh(self):
        d = engine.build_dashboard(self.win.rng_from or None, self.win.rng_to or None,
                                   self.win.f_bank or None, self.win.f_card or None,
                                   self.win.f_source or None)
        scope = self.win.scope_text()
        note = ("Showing " + scope) if scope else "Showing every bank & card"
        if not d["rows_n"]:
            note += "  —  nothing in this date range"
        self.scope_note.setText(note)
        sig = (self.win.rng_from, self.win.rng_to, scope, round(d["tout"]), round(d["tin"]),
               round(d["cc_bills"]), d["rows_n"], len(d["spend"]), len(d["merchants"]))
        anim = sig != self._sig
        self._sig = sig
        self.k_out.setValue(d["tout"], "₹", animate=anim)
        self.k_cc.setValue(d["cc_bills"], "₹", animate=anim)
        self.k_in.setValue(d["tin"], "₹", animate=anim)
        self.k_net.setValue(d["net"], "₹", animate=anim)
        self.k_n.setValue(d["rows_n"], "", fmt=lambda v: f"{int(v):,}", animate=anim)
        self.donut.setData(d["spend"], "spending", "₹" + T.lakh(d["tout"]), animate=anim)
        self.income.setData(d["income"], animate=anim)
        self._fill_legend(d["spend"], d["tout"] or 1)
        self._fill_habits(d)
        self._fill_tree(d["merchants"])
        self._fill_large(d["large"])

    def _fill_habits(self, d):
        """The 'Category habits' table: for every spending category in range,
        how many times it was used, its average per month, and its quietest /
        busiest month (by number of transactions) — e.g. Fuel: 42×, ~5.2/month,
        quietest Jan 26 (2×), busiest Mar 26 (9×)."""
        cat_m = d.get("cat_months", {})
        # calendar months of the window, clamped to the first transaction so
        # "All time" doesn't drown the averages in empty years
        try:
            r_from = date.fromisoformat(self.win.rng_from)
            r_to = date.fromisoformat(self.win.rng_to)
        except ValueError:
            r_from = r_to = date.today()
        first = min((m for mm in cat_m.values() for m in mm), default=None)
        start = date(r_from.year, r_from.month, 1)
        if first:
            start = max(start, date(int(first[:4]), int(first[5:7]), 1))
        months, cur, stop = [], start, date(r_to.year, r_to.month, 1)
        while cur <= stop and len(months) < 1200:
            months.append(cur.strftime("%Y-%m"))
            cur = date(cur.year + (cur.month == 12), cur.month % 12 + 1, 1)
        nm = max(1, len(months))

        def ml(m):
            return f"{datetime.strptime(m, '%Y-%m'):%b %y}"

        colors = {c: col for c, _v, col in d["spend"]}
        t = self.habits
        t.setSortingEnabled(False)
        t.setRowCount(len(cat_m))
        for i, (cat, mm) in enumerate(sorted(cat_m.items(), key=lambda x: -sum(x[1].values()))):
            n = sum(mm.values())
            it = txt_item(cat)
            it.setForeground(QColor(colors.get(cat, T.TEXT)))
            t.setItem(i, 0, it)
            t.setItem(i, 1, NumItem(f"{n}×", n))
            t.setItem(i, 2, NumItem(f"{n / nm:.1f}×", n / nm))
            if nm >= 2:
                counts = [(m, mm.get(m, 0)) for m in months]
                lo = min(counts, key=lambda x: x[1])
                hi = max(counts, key=lambda x: x[1])
                t.setItem(i, 3, NumItem(f"{ml(lo[0])} ({lo[1]}×)", lo[1]))
                t.setItem(i, 4, NumItem(f"{ml(hi[0])} ({hi[1]}×)", hi[1]))
            else:
                t.setItem(i, 3, NumItem("—", 0))
                t.setItem(i, 4, NumItem("—", 0))
        t.setSortingEnabled(True)
        t.sortItems(1, Qt.DescendingOrder)

    def _habit_dbl(self, idx):
        it = self.habits.item(idx.row(), 0)
        if it:
            self.win.open_category(it.text(), "OUT")

    def _fill_legend(self, spend, total):
        while self.legend.count():
            it = self.legend.takeAt(0)
            w = it.widget()
            if w:
                w.deleteLater()
        if not spend:
            self.legend.addWidget(lbl("No spending in this period.", color=T.MUTED, size=10))
            return
        for cat, val, color in spend[:9]:
            row = QWidget(); row.setCursor(Qt.PointingHandCursor)
            rh = QHBoxLayout(row); rh.setContentsMargins(0, 1, 0, 1); rh.setSpacing(8)
            dot = QLabel("●"); dot.setStyleSheet(f"color:{color}; background:transparent;")
            rh.addWidget(dot)
            nm = lbl(cat if len(cat) <= 24 else cat[:23] + "…", color=T.TEXT2, size=9)
            rh.addWidget(nm); rh.addStretch(1)
            rh.addWidget(lbl(f"{val/total*100:.0f}%", color=T.MUTED, size=8))
            rh.addWidget(lbl("₹" + T.inr(val), bold=True, size=9))
            row.mousePressEvent = lambda e, c=cat: self.win.open_category(c, "OUT")
            self.legend.addWidget(row)
        self.legend.addStretch(1)

    def _fill_tree(self, merchants):
        self.tree.setSortingEnabled(False)
        self.tree.clear()
        for m in merchants[:120]:
            it = TreeItem([m["disp"][:46], m["n"], "₹" + T.inr(m["total"]), (m["cats"] or "")[:40]],
                          sortvals={1: m["n"], 2: m["total"]})
            it._merch = m
            if m.get("rows"):
                it.addChild(QTreeWidgetItem(["loading…"]))
            self.tree.addTopLevelItem(it)
        self.tree.setSortingEnabled(True)
        self.tree.sortItems(2, Qt.DescendingOrder)

    def _fill_large(self, rows):
        self._large_rows = rows
        self.large.setSortingEnabled(False)
        self.large.setRowCount(len(rows))
        for i, r in enumerate(rows):
            d = dt_str(r)
            self.large.setItem(i, 0, txt_item(d))
            m = txt_item((r.get("merchant") or "")[:46]); m.setData(Qt.UserRole, r["id"])
            self.large.setItem(i, 1, m)
            self.large.setItem(i, 2, txt_item(r.get("_cat", "")))
            a = NumItem("−₹" + T.inr(r["amount"]), r["amount"])
            a.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.large.setItem(i, 3, a)
        self.large.setSortingEnabled(True)
        self.large.sortItems(3, Qt.DescendingOrder)


class InboxPage(Page):
    def build(self):
        self.body = QWidget()
        self.v = QVBoxLayout(self.body); self.v.setContentsMargins(0, 0, 8, 0); self.v.setSpacing(8)
        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll_area(self.body))

    def on_show(self):
        while self.v.count():
            it = self.v.takeAt(0)
            w = it.widget()
            if w:
                w.deleteLater()
        pend = engine.pending()
        head = QHBoxLayout()
        head.addWidget(lbl(f"{len(pend)} transaction(s) to review", bold=True, size=14))
        head.addStretch(1)
        head.addWidget(btn("Check for new", self.win.check_now, "ghost"))
        self.v.addLayout(head)
        if pend:
            self.v.addWidget(lbl(goblin.review(len(pend)), color=T.TEXT2, size=10))
        if not pend:
            c = card(); cv = QVBoxLayout(c); cv.setContentsMargins(30, 40, 30, 40); cv.setAlignment(Qt.AlignCenter)
            cv.addWidget(lbl("✓", color=T.GREEN, bold=True, size=32), alignment=Qt.AlignCenter)
            cv.addWidget(lbl("All caught up!", bold=True, size=14), alignment=Qt.AlignCenter)
            cv.addWidget(lbl(goblin.all_clear(), color=T.MUTED, size=10),
                         alignment=Qt.AlignCenter)
            self.v.addWidget(c)
        for r in pend:
            self.v.addWidget(self._card(r))
        self.v.addStretch(1)

    def _card(self, r):
        is_new = r["id"] in self.win.session_new_ids
        c = card()
        if is_new:
            c.setStyleSheet("QFrame#card{border:1px solid %s;}" % T.ACCENT)
        h = QHBoxLayout(c); h.setContentsMargins(16, 12, 16, 12)
        left = QVBoxLayout(); left.setSpacing(2)
        top = QHBoxLayout(); top.setSpacing(8)
        sign = "+" if r["direction"] == "IN" else "−"
        col = T.GREEN if r["direction"] == "IN" else T.RED
        top.addWidget(lbl(f"{sign} ₹{T.inr(r['amount'])}", color=col, bold=True, size=16))
        if is_new:
            b = lbl(" NEW ", color="#fff", bold=True, size=7)
            b.setStyleSheet(f"background:{T.ACCENT}; color:white; border-radius:4px; padding:1px 4px;")
            top.addWidget(b)
        top.addStretch(1)
        left.addLayout(top)
        left.addWidget(lbl((r.get("merchant") or "(transaction)")[:60], bold=True, size=11))
        meta = f"{(r.get('bank') or r.get('source') or '')}  ·  {dt_str(r)}  ·  guess: {r.get('guessed_category') or '—'}"
        left.addWidget(lbl(meta, color=T.MUTED, size=9))
        h.addLayout(left, 1)
        right = QVBoxLayout(); right.setSpacing(6)
        cb = cat_combo(r.get("guessed_category") or "")
        cb.setMinimumWidth(230)
        right.addWidget(cb)
        brow = QHBoxLayout()
        brow.addWidget(btn("Save", lambda _=0, rr=r, c=cb: self._save(rr, c.currentText()), "green"))
        brow.addWidget(btn("Skip", lambda _=0, rr=r: self._skip(rr), "ghost"))
        right.addLayout(brow)
        h.addLayout(right)
        return c

    def _save(self, r, cat):
        cat = (cat or "").strip()
        engine.add_custom_category(cat)
        n = engine.tag_and_learn(r["id"], cat, "")
        self.win.session_new_ids.discard(r["id"])
        if n > 1:
            self.win.toast("Applied to this payee",
                           f"Set '{cat}' on {n} transactions from {r.get('merchant') or 'this payee'}.", "in")
        self.win.refresh_counts(); self.on_show()

    def _skip(self, r):
        engine.tag(r["id"], r.get("category") or "", "", "ignored")
        self.win.session_new_ids.discard(r["id"])
        self.win.refresh_counts(); self.on_show()


class TransactionsPage(Page):
    def build(self):
        v = QVBoxLayout(self); v.setContentsMargins(0, 0, 0, 0); v.setSpacing(12)
        top = QHBoxLayout()
        top.addWidget(lbl("Search", color=T.MUTED, bold=True, size=9))
        self.search = QLineEdit(); self.search.setMaximumWidth(280)
        self.search.textChanged.connect(self._filter)
        top.addWidget(self.search); top.addStretch(1)
        top.addWidget(btn("Export CSV", self._export, "ghost"))
        v.addLayout(top)

        cc = card(); cv = QVBoxLayout(cc); cv.setContentsMargins(16, 12, 16, 12)
        cv.addWidget(lbl("By category (tagged)", bold=True, size=12))
        self.cattable = make_table(["Category", "Type", "Count", "Total"], stretch=0)
        self.cattable.setMinimumHeight(220)
        cv.addWidget(self.cattable)
        v.addWidget(cc)

        lc = card(); lv = QVBoxLayout(lc); lv.setContentsMargins(16, 12, 16, 12)
        lv.addWidget(lbl("Transaction log  ·  double-click to tag", bold=True, size=12))
        self.log = make_table(["Date & time", "Merchant", "Card / filter", "Amount", "Category", "Status"], stretch=1)
        self.log.setColumnWidth(0, 158)
        self.log.doubleClicked.connect(self._dbl)
        lv.addWidget(self.log, 1)
        v.addWidget(lc, 1)

    def on_show(self):
        self._all = engine.recent(1000)
        for r in self._all:
            r["_dt"] = dt_str(r)
        self._filter()
        totals = engine.totals_by_category()
        self.cattable.setSortingEnabled(False)
        self.cattable.setRowCount(len(totals))
        for i, r in enumerate(totals):
            self.cattable.setItem(i, 0, txt_item(r.get("category") or "—"))
            self.cattable.setItem(i, 1, txt_item(r.get("direction", "")))
            self.cattable.setItem(i, 2, NumItem(str(r.get("n", 0)), r.get("n", 0)))
            self.cattable.setItem(i, 3, NumItem("₹" + T.inr(r.get("total", 0)), r.get("total", 0)))
        self.cattable.setSortingEnabled(True)
        self.cattable.sortItems(3, Qt.DescendingOrder)

    def _filter(self):
        q = self.search.text().strip().lower()
        rows = self._all if not q else [
            r for r in self._all if q in (
                (r.get("merchant") or "") + " " + (r.get("category") or "") + " " +
                (r.get("subject") or "") + " " + (r.get("bank") or "")).lower()]
        self._rows = rows
        self.log.setSortingEnabled(False)
        self.log.setRowCount(len(rows))
        for i, r in enumerate(rows):
            self.log.setItem(i, 0, txt_item(r.get("_dt") or dt_str(r)))
            m = txt_item((r.get("merchant") or "")[:44]); m.setData(Qt.UserRole, r["id"])
            self.log.setItem(i, 1, m)
            self.log.setItem(i, 2, txt_item(r.get("card") or r.get("source") or r.get("bank") or "—"))
            sign = "+" if r["direction"] == "IN" else "−"
            a = NumItem(sign + "₹" + T.inr(r["amount"]), r["amount"])
            a.setForeground(QColor(T.GREEN if r["direction"] == "IN" else T.TEXT))
            a.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.log.setItem(i, 3, a)
            self.log.setItem(i, 4, txt_item(r.get("category") or r.get("guessed_category") or "—"))
            self.log.setItem(i, 5, txt_item(r.get("status", "")))
        self.log.setSortingEnabled(True)

    def _dbl(self, idx):
        item = self.log.item(idx.row(), 1)
        rid = item.data(Qt.UserRole) if item else None
        r = next((x for x in self._rows if x["id"] == rid), None)
        if r:
            TagDialog(self.win, r, on_done=self.on_show).exec_()

    def _export(self):
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "transactions_export.csv")
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["date", "account", "bank", "direction", "amount", "merchant",
                            "category", "note", "status", "subject"])
                for r in engine.recent(5000):
                    w.writerow([r.get("email_date"), r.get("account"), r.get("bank"),
                                r.get("direction"), f'{r["amount"]:.2f}', r.get("merchant"),
                                r.get("category") or "", r.get("note") or "",
                                r.get("status"), r.get("subject")])
            QMessageBox.information(self.win, "Exported", f"Saved to:\n{path}")
        except Exception as e:
            QMessageBox.critical(self.win, "Export failed", str(e))


class ScanPage(Page):
    def build(self):
        v = QVBoxLayout(self); v.setContentsMargins(0, 0, 0, 0); v.setSpacing(12)
        self._worker = None

        cc = card(); cv = QVBoxLayout(cc); cv.setContentsMargins(16, 14, 16, 14)
        cv.addWidget(lbl("Fetch a date range from your mailboxes", bold=True, size=12))
        cv.addWidget(lbl("Already-fetched emails are skipped (fetch-once). Tick force to re-read them.",
                         color=T.MUTED, size=9))
        row = QHBoxLayout()
        row.addWidget(lbl("From", color=T.MUTED, bold=True, size=9))
        self.de_from = date_edit()
        row.addWidget(self.de_from)
        row.addWidget(lbl("To", color=T.MUTED, bold=True, size=9))
        self.de_to = date_edit()
        row.addWidget(self.de_to)
        self.force = QCheckBox("Force re-fetch"); row.addWidget(self.force)
        row.addStretch(1)
        self.start_btn = btn("Start scan", self._start)
        self.cancel_btn = btn("Cancel", self._cancel, "danger"); self.cancel_btn.setVisible(False)
        row.addWidget(self.start_btn); row.addWidget(self.cancel_btn)
        cv.addLayout(row)
        v.addWidget(cc)

        pc = card(); pv = QVBoxLayout(pc); pv.setContentsMargins(16, 14, 16, 14)
        from PyQt5.QtWidgets import QProgressBar
        self.bar = QProgressBar(); self.bar.setTextVisible(False); self.bar.setFixedHeight(10)
        self.bar.setStyleSheet(f"QProgressBar{{background:{T.PANEL};border:none;border-radius:5px;}}"
                               f"QProgressBar::chunk{{background:{T.ACCENT};border-radius:5px;}}")
        pv.addWidget(self.bar)
        self.stat = lbl("Idle.", color=T.MUTED, size=9)
        pv.addWidget(self.stat)
        v.addWidget(pc)

        lc = card(); lv = QVBoxLayout(lc); lv.setContentsMargins(16, 12, 16, 12)
        lv.addWidget(lbl("Live log", bold=True, size=11))
        self.logbox = QPlainTextEdit(); self.logbox.setReadOnly(True)
        self.logbox.setStyleSheet(f"background:{T.PANEL2}; font-family:Consolas; font-size:9pt;")
        lv.addWidget(self.logbox, 1)
        v.addWidget(lc, 1)

    def on_show(self):
        # scanning is a history operation → default to the whole year, not the
        # dashboard's 2-day view (user can change it).
        if not self.de_from.date().isValid() or self.de_from.date().year() < 2001:
            self.de_from.setDate(QDate.fromString(date.today().replace(month=1, day=1).isoformat(), "yyyy-MM-dd"))
            self.de_to.setDate(QDate.fromString(date.today().isoformat(), "yyyy-MM-dd"))

    def _start(self):
        if self._worker and self._worker.isRunning():
            return
        sd = self.de_from.date().toPyDate()
        ed = self.de_to.date().toPyDate()
        if not config.load().get("accounts"):
            QMessageBox.information(self.win, "No mailbox", "Add a mailbox in Settings first.")
            return
        self.logbox.clear()
        self.bar.setRange(0, 100); self.bar.setValue(4)
        self.stat.setText("Starting…")
        self.start_btn.setVisible(False); self.cancel_btn.setVisible(True)
        self._worker = ScanWorker(sd, ed, self.force.isChecked())
        self._worker.logLine.connect(self._log)
        self._worker.accStart.connect(lambda p: self.stat.setText(f"Mailbox {p['idx']}/{p['total']} — {p['label']}"))
        self._worker.totalKnown.connect(lambda p: self.bar.setValue(8) if p.get("to_read") else None)
        self._worker.progress.connect(self._progress)
        self._worker.finishedScan.connect(self._done)
        self._worker.start()

    def _cancel(self):
        if self._worker:
            self._worker.cancel()
            self.stat.setText("Cancelling…")

    def _log(self, s):
        self.logbox.appendPlainText(s)

    def _progress(self, p):
        tot = max(1, p.get("total", 1))
        self.bar.setValue(int(min(99, p["done"] / tot * 100)))
        self.stat.setText(f"Read {p['done']}/{tot}  ·  added {p['added']} transactions")

    def _done(self, p):
        self.bar.setValue(100)
        self.stat.setText(f"Done — added {p.get('added',0)} · {p.get('scanned',0)} emails "
                          f"({p.get('from_cache',0)} cached, {p.get('downloaded',0)} downloaded) · "
                          f"cache holds {p.get('cache',0)}")
        self.start_btn.setVisible(True); self.cancel_btn.setVisible(False)
        self.win.refresh_counts()
        self.win.toast("Scan finished", f"Added {p.get('added',0)} transactions.", "in")


class ParserPage(Page):
    def build(self):
        body = QWidget()
        self.v = QVBoxLayout(body); self.v.setContentsMargins(0, 0, 8, 0); self.v.setSpacing(12)

        steps = card(); sv = QVBoxLayout(steps); sv.setContentsMargins(16, 14, 16, 14)
        sv.addWidget(lbl("How an email becomes a transaction", bold=True, size=12))
        for n, t in [("1", "Filter — does the sender/subject match a tracked source (Settings)?"),
                     ("2", "Amount — find the transaction amount, skipping balance/credit-limit figures."),
                     ("3", "Direction — debit/credit keywords decide money-in vs money-out."),
                     ("4", "Merchant — pull the payee from the narration; else clean the subject.")]:
            r = QHBoxLayout()
            b = lbl(f" {n} ", color="#fff", bold=True); b.setStyleSheet(f"background:{T.ACCENT}; color:white; border-radius:4px; padding:1px 6px;")
            r.addWidget(b); r.addWidget(lbl(t, color=T.TEXT2, size=10)); r.addStretch(1)
            sv.addLayout(r)
        self.v.addWidget(steps)
        self.v.addWidget(self._builtin_card())

        test = card(); tv = QVBoxLayout(test); tv.setContentsMargins(16, 14, 16, 14)
        tv.addWidget(lbl("Try it — paste an email", bold=True, size=12))
        tv.addWidget(lbl("FROM", color=T.MUTED, bold=True, size=8))
        self.t_from = QLineEdit(); tv.addWidget(self.t_from)
        tv.addWidget(lbl("SUBJECT", color=T.MUTED, bold=True, size=8))
        self.t_subj = QLineEdit(); tv.addWidget(self.t_subj)
        tv.addWidget(lbl("BODY", color=T.MUTED, bold=True, size=8))
        self.t_body = QPlainTextEdit(); self.t_body.setFixedHeight(110); tv.addWidget(self.t_body)
        tv.addWidget(btn("Analyze", self._analyze), alignment=Qt.AlignLeft)
        self.result = QVBoxLayout(); rw = QWidget(); rw.setLayout(self.result)
        tv.addWidget(rw)
        self.v.addWidget(test)

        cust = card(); self.custom = QVBoxLayout(cust); self.custom.setContentsMargins(16, 14, 16, 14)
        self.v.addWidget(cust)

        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll_area(body))

    def _builtin_card(self):
        c = card(); v = QVBoxLayout(c); v.setContentsMargins(16, 14, 16, 14); v.setSpacing(6)
        v.addWidget(lbl("Built-in rules — what the parser looks for", bold=True, size=12))
        v.addWidget(lbl("These are the keywords/patterns already applied to every email. "
                        "Add your own below to extend them.", color=T.MUTED, size=9))

        def chips(items):
            q = QLabel(", ".join(items) if items else "—")
            q.setWordWrap(True)
            q.setStyleSheet(f"background:{T.PANEL2}; padding:7px 10px; border-radius:6px; "
                            f"color:{T.TEXT}; font-size:9.5pt;")
            return q

        currencies = ["INR", "Rs", "₹", "USD", "US$", "GBP", "EUR", "AED", "SGD",
                      "AUD", "CAD", "JPY", "MYR", "THB", "$", "£", "€"]
        v.addWidget(lbl("CURRENCIES RECOGNISED", color=T.MUTED, bold=True, size=8))
        v.addWidget(chips(currencies))
        v.addWidget(lbl("MONEY-OUT KEYWORDS", color=T.MUTED, bold=True, size=8))
        v.addWidget(chips(mailreader.OUT_KW))
        v.addWidget(lbl("MONEY-IN KEYWORDS", color=T.MUTED, bold=True, size=8))
        v.addWidget(chips(mailreader.IN_KW))
        v.addWidget(lbl("MERCHANT PATTERNS (regex)", color=T.MUTED, bold=True, size=8))
        for pat in mailreader.MERCHANT_PATTERNS:
            pl = QLabel(pat); pl.setWordWrap(True)
            pl.setStyleSheet(f"background:{T.PANEL2}; font-family:Consolas; font-size:8.5pt; "
                             f"padding:4px 8px; border-radius:4px; color:{T.TEXT2};")
            v.addWidget(pl)
        return c

    def on_show(self):
        self._render_custom()

    def _analyze(self):
        res = engine.parse_debug(self.t_subj.text(), self.t_body.toPlainText().strip(), self.t_from.text())
        while self.result.count():
            it = self.result.takeAt(0); w = it.widget()
            if w:
                w.deleteLater()
        ok = res.get("is_txn")
        self.result.addWidget(lbl("✓ Detected as a transaction" if ok else "✗ Not detected as a transaction",
                                   color=T.GREEN if ok else T.RED2, bold=True, size=11))
        rows = [("Tracked by a source", "yes" if res.get("tracked") else "no — add a source in Settings"),
                ("Matched source", res.get("source") or "—"),
                ("Amount", (f"{res.get('currency') or ''} {res.get('amount')}" if res.get("amount") else "—")),
                ("Amount rule", res.get("amount_rule") or "—"),
                ("Direction", res.get("direction") or "—"),
                ("Merchant", res.get("merchant") or "—"),
                ("Card", res.get("card") or "—"),
                ("Reference", res.get("ref") or "— (this bank doesn't quote one)")]
        if not ok and res.get("why"):
            rows.append(("Why not", res["why"]))
        for k, val in rows:
            r = QHBoxLayout()
            r.addWidget(lbl(k, color=T.MUTED, size=9)); r.addWidget(lbl(str(val), color=T.TEXT2, bold=True, size=9))
            r.addStretch(1)
            self.result.addLayout(r)

    def _render_custom(self):
        while self.custom.count():
            it = self.custom.takeAt(0); w = it.widget()
            if w:
                w.deleteLater()
            elif it.layout():
                _clear_layout(it.layout())
        c = (config.load().get("custom", {}) or {})
        self.custom.addWidget(lbl("Custom rules", bold=True, size=12))
        self._group("Money-out keywords", "out_kw", c.get("out_keywords", []))
        self._group("Money-in keywords", "in_kw", c.get("in_keywords", []))
        self._group("Merchant patterns (regex, one capture group)", "merchant", c.get("merchant_patterns", []))

    def _group(self, title, typ, items):
        self.custom.addWidget(lbl(title.upper(), color=T.MUTED, bold=True, size=8))
        for val in items:
            r = QHBoxLayout()
            v = QLabel(val); v.setStyleSheet(f"background:{T.PANEL2}; font-family:Consolas; padding:3px 8px; border-radius:4px;")
            r.addWidget(v, 1)
            r.addWidget(btn("✕", lambda _=0, tp=typ, vv=val: self._remove(tp, vv), "ghost"))
            self.custom.addLayout(r)
        addr = QHBoxLayout()
        e = QLineEdit(); addr.addWidget(e, 1)
        addr.addWidget(btn("Add", lambda _=0, tp=typ, ed=e: self._add(tp, ed.text()), "ghost"))
        self.custom.addLayout(addr)

    def _add(self, typ, val):
        val = (val or "").strip()
        if not val:
            return
        cfg = config.load(); c = cfg.setdefault("custom", {})
        if typ == "merchant":
            import re
            try:
                if re.compile(val).groups < 1:
                    QMessageBox.information(self.win, "Pattern", "Needs one capture group ( … ).")
                    return
            except re.error as e:
                QMessageBox.critical(self.win, "Bad regex", str(e))
                return
            c.setdefault("merchant_patterns", []).append(val)
        elif typ == "out_kw":
            c.setdefault("out_keywords", []).append(val.lower())
        elif typ == "in_kw":
            c.setdefault("in_keywords", []).append(val.lower())
        config.save(cfg)
        import mailreader; mailreader.apply_custom(cfg)
        self._render_custom()

    def _remove(self, typ, val):
        cfg = config.load(); c = cfg.setdefault("custom", {})
        key = {"merchant": "merchant_patterns", "out_kw": "out_keywords", "in_kw": "in_keywords"}[typ]
        if val in (c.get(key) or []):
            c[key].remove(val); config.save(cfg)
            import mailreader; mailreader.apply_custom(cfg)
        self._render_custom()


class SettingsPage(Page):
    def build(self):
        self.body = QWidget()
        self.v = QVBoxLayout(self.body); self.v.setContentsMargins(0, 0, 8, 0); self.v.setSpacing(12)
        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll_area(self.body))

    def on_show(self):
        while self.v.count():
            it = self.v.takeAt(0); w = it.widget()
            if w:
                w.deleteLater()
        cfg = config.load()
        self._accounts(cfg)
        self._sources(cfg)
        self._general(cfg)
        self._categories(cfg)
        self._cache(cfg)
        self.v.addStretch(1)

    def _accounts(self, cfg):
        c = card(); v = QVBoxLayout(c); v.setContentsMargins(16, 14, 16, 14)
        v.addWidget(lbl("Mailboxes", bold=True, size=12))
        v.addWidget(lbl("Accounts to watch. Sign in with Google or Microsoft (recommended — "
                        "no password stored), or use a 16-character Gmail app password.",
                        color=T.MUTED, size=9, wrap=True))
        for a in cfg.get("accounts", []):
            em = a.get("email", "")
            is_o = (a.get("auth") or "app_password").lower() in (
                "oauth", "google", "google_oauth", "microsoft", "microsoft_oauth")
            connected = is_o and oauth.has_token(em)
            r = QHBoxLayout()
            r.addWidget(lbl(a.get("label", "?"), bold=True, size=10))
            r.addWidget(lbl(em, color=T.MUTED, size=9))
            if is_o:
                method = (oauth.provider_label(oauth.provider_of(a)) + " · "
                          + ("connected" if connected else "not signed in"))
            else:
                method = "App password"
            r.addWidget(lbl(method, color=(T.GREEN if connected else T.MUTED), size=8))
            r.addStretch(1)
            if is_o:
                r.addWidget(btn("Re-authorize" if connected else "Sign in",
                                lambda _=0, e=em: self._oauth_signin(e), "ghost"))
            r.addWidget(btn("Test", lambda _=0, ac=a: self._test(ac), "ghost"))
            r.addWidget(btn("Remove", lambda _=0, l=a["label"]: self._acc_remove(l), "ghost"))
            v.addLayout(r)
        v.addSpacing(10)

        v.addWidget(lbl("Add a mailbox", bold=True, size=10))
        self.a_label = QLineEdit(); self.a_label.setPlaceholderText("e.g. Personal")
        self.a_email = QLineEdit(); self.a_email.setPlaceholderText("you@gmail.com / you@outlook.com")
        self.a_method = no_wheel(QComboBox())
        self.a_method.addItems(["Sign in with Google (OAuth2)",
                                "Sign in with Microsoft / Outlook (OAuth2)",
                                "App password (Gmail)"])
        v.addLayout(_form_row("Label", self.a_label))
        v.addLayout(_form_row("Email address", self.a_email))
        v.addLayout(_form_row("Sign-in method", self.a_method))
        # app-password row — shown only when the app-password method is chosen
        self.a_pw = QLineEdit(); self.a_pw.setEchoMode(QLineEdit.Password)
        self.a_pw.setPlaceholderText("16-char app password (no spaces)")
        self.a_pw_row = QWidget(); pwl = QHBoxLayout(self.a_pw_row)
        pwl.setContentsMargins(0, 0, 0, 0)
        _pl = lbl("App password", color=T.MUTED, size=9); _pl.setFixedWidth(120)
        pwl.addWidget(_pl); pwl.addWidget(self.a_pw, 1)
        v.addWidget(self.a_pw_row)
        self.a_method.currentIndexChanged.connect(self._toggle_pw)
        self._toggle_pw()
        v.addSpacing(4)
        v.addWidget(btn("Add mailbox", self._acc_add), alignment=Qt.AlignLeft)
        v.addWidget(lbl("Google / Microsoft: a browser opens once for you to grant read-only "
                        "access. App password (Gmail only): Google Account → Security → "
                        "2-Step Verification → App passwords.", color=T.MUTED, size=8, wrap=True))
        self.v.addWidget(c)
        self._oauth_client_card(cfg)

    def _selected_method(self):
        t = self.a_method.currentText()
        if t.startswith("Sign in with Google"):
            return "google"
        if t.startswith("Sign in with Microsoft"):
            return "microsoft"
        return "app_password"

    def _toggle_pw(self):
        self.a_pw_row.setVisible(self._selected_method() == "app_password")

    def _acc_add(self):
        lb = self.a_label.text().strip(); em = self.a_email.text().strip()
        method = self._selected_method()
        if not (lb and em):
            QMessageBox.information(self.win, "Missing", "Label and email address are required.")
            return
        cfg = config.load()
        if any(a.get("label") == lb for a in cfg.get("accounts", [])):
            QMessageBox.information(self.win, "Duplicate", f"A mailbox labelled '{lb}' already exists.")
            return
        if method in ("google", "microsoft"):
            cfg.setdefault("accounts", []).append(
                {"label": lb, "email": em, "auth": "oauth", "provider": method, "folder": "INBOX"})
            config.save(cfg); self.on_show()
            self._oauth_signin(em)               # launch the browser sign-in now
        else:
            pw = self.a_pw.text().strip().replace(" ", "")
            if not pw:
                QMessageBox.information(self.win, "Missing",
                                        "Enter the app password, or choose Google / Microsoft sign-in.")
                return
            cfg.setdefault("accounts", []).append(
                {"label": lb, "email": em, "auth": "app_password", "app_password": pw, "folder": "INBOX"})
            config.save(cfg); self.on_show()

    def _oauth_signin(self, email):
        cfg = config.load()
        acc = next((a for a in cfg.get("accounts", []) if a.get("email") == email), None)
        prov = oauth.provider_of(acc)
        plabel = oauth.provider_label(prov)
        cid, csec, source = oauth.client_creds(account=acc, cfg=cfg, provider=prov)
        if not cid:
            QMessageBox.information(
                self.win, f"{plabel} client needed",
                f"Signing in with {plabel} needs an OAuth Client ID.\n\n"
                f"Add yours under '{plabel} sign-in setup' below (free — see the README), "
                f"or use a different sign-in method.")
            return
        self.win.toast("Opening browser…", f"Grant read access to {email} ({plabel}).", "info")
        self.win._log_line(f"{plabel} sign-in for {email} — client from {source}. Waiting for browser…")
        self._oauth_worker = OAuthWorker(email, prov, cid, csec)
        self._oauth_worker.done.connect(self._oauth_done)
        self._oauth_worker.start()

    def _oauth_done(self, r):
        plabel = oauth.provider_label(r.get("provider", "google"))
        if r.get("ok"):
            self.win.toast("Signed in", f"{r['email']} connected via {plabel}.", "in")
            self.win._log_line(f"{plabel} sign-in OK for {r['email']}.")
            self.win.check_now()
        else:
            self.win.toast(f"{plabel} sign-in failed", str(r.get("message", ""))[:140], "out",
                           on_click=self.win.show_logs)
            self.win._log_line(f"{plabel} sign-in failed for {r.get('email')}: {r.get('message')}")
        self.on_show()

    def _oauth_client_card(self, cfg):
        o = cfg.get("oauth", {}) or {}
        c = card(); v = QVBoxLayout(c); v.setContentsMargins(16, 14, 16, 14)
        v.addWidget(lbl("Google / Microsoft sign-in setup (advanced)", bold=True, size=12))
        v.addWidget(lbl("Only needed if the app doesn't already ship with a client. Create a "
                        "free OAuth client and paste it here (see the README). Leave a section "
                        "blank if you don't use that provider.", color=T.MUTED, size=9, wrap=True))

        # Google (Desktop app client: id + secret)
        gsrc = oauth.client_creds(cfg=cfg, provider="google")[2]
        v.addWidget(lbl(f"Google (Gmail) — {self._src_note(gsrc)}", bold=True, size=10, color=T.TEXT2))
        self.o_g_cid = QLineEdit(o.get("google_client_id", ""))
        self.o_g_cid.setPlaceholderText("xxxxx.apps.googleusercontent.com")
        self.o_g_csec = QLineEdit(o.get("google_client_secret", ""))
        self.o_g_csec.setEchoMode(QLineEdit.Password)
        self.o_g_csec.setPlaceholderText("client secret (from the Desktop app client)")
        v.addLayout(_form_row("Client ID", self.o_g_cid))
        v.addLayout(_form_row("Client secret", self.o_g_csec))

        v.addSpacing(6)
        # Microsoft (public/native client: id only, no secret needed)
        msrc = oauth.client_creds(cfg=cfg, provider="microsoft")[2]
        v.addWidget(lbl(f"Microsoft (Outlook/Office365) — {self._src_note(msrc)}",
                        bold=True, size=10, color=T.TEXT2))
        self.o_m_cid = QLineEdit(o.get("microsoft_client_id", ""))
        self.o_m_cid.setPlaceholderText("Application (client) ID from Azure — a public client")
        self.o_m_csec = QLineEdit(o.get("microsoft_client_secret", ""))
        self.o_m_csec.setEchoMode(QLineEdit.Password)
        self.o_m_csec.setPlaceholderText("(optional — leave blank for a public client)")
        v.addLayout(_form_row("Client ID", self.o_m_cid))
        v.addLayout(_form_row("Client secret", self.o_m_csec))

        v.addSpacing(4)
        v.addWidget(btn("Save clients", self._save_oauth_client), alignment=Qt.AlignLeft)
        self.v.addWidget(c)

    @staticmethod
    def _src_note(source):
        return {"bundled default": "a client ships with this app; override below only to use your own",
                "Settings": "using the client you configured here",
                "this mailbox": "using a per-mailbox client",
                "none": "not configured yet"}.get(source, source)

    def _save_oauth_client(self):
        cfg = config.load()
        cfg.setdefault("oauth", {})
        cfg["oauth"]["google_client_id"] = self.o_g_cid.text().strip()
        cfg["oauth"]["google_client_secret"] = self.o_g_csec.text().strip()
        cfg["oauth"]["microsoft_client_id"] = self.o_m_cid.text().strip()
        cfg["oauth"]["microsoft_client_secret"] = self.o_m_csec.text().strip()
        config.save(cfg)
        self.win.toast("Saved", "OAuth client(s) saved. Use 'Sign in' on a mailbox.", "in")
        self.on_show()

    def _acc_remove(self, label_):
        if QMessageBox.question(self.win, "Remove", f"Remove mailbox '{label_}'?") != QMessageBox.Yes:
            return
        cfg = config.load()
        cfg["accounts"] = [a for a in cfg.get("accounts", []) if a["label"] != label_]
        config.save(cfg); self.on_show()

    def _test(self, acc):
        self.win.toast("Testing…", f"Connecting to {acc['label']}", "info")
        ok, msg = engine.test_connection(acc)
        self.win.toast("Connection " + ("OK" if ok else "failed"), f"{acc['label']}: {str(msg)[:80]}",
                       "in" if ok else "out")

    def _sources(self, cfg):
        import mailreader
        c = card(); v = QVBoxLayout(c); v.setContentsMargins(16, 14, 16, 14)
        v.addWidget(lbl("Tracked sources (filters)", bold=True, size=12))
        v.addWidget(lbl("An email is tracked when it matches one of these. 'both' checks the primary field first.",
                        color=T.MUTED, size=9, wrap=True))
        for s in cfg.get("sources", []):
            m, p = mailreader.effective_mode(s)
            r = QHBoxLayout()
            dot = QLabel("●"); dot.setStyleSheet(f"color:{T.source_color(s.get('name'))}; background:transparent;")
            r.addWidget(dot)
            r.addWidget(lbl(s.get("name", "?"), bold=True, size=10))
            r.addWidget(lbl(f"from~'{s.get('from_contains','')}'  subj~'{s.get('subject_contains','')}'  [{m}, primary={p}]",
                            color=T.MUTED, size=8)); r.addStretch(1)
            r.addWidget(btn("Edit", lambda _=0, ss=dict(s): self._src_edit(ss), "ghost"))
            r.addWidget(btn("Remove", lambda _=0, n=s["name"]: self._src_remove(n), "ghost"))
            v.addLayout(r)
        v.addSpacing(8)
        self.s_name = QLineEdit(); self.s_from = QLineEdit(); self.s_subj = QLineEdit()
        self.s_match = no_wheel(QComboBox()); self.s_match.addItems(["both", "from", "subject", "either"])
        self.s_primary = no_wheel(QComboBox()); self.s_primary.addItems(["from", "subject"])
        for t, w in [("Name", self.s_name), ("From contains", self.s_from),
                     ("Subject contains", self.s_subj), ("Match", self.s_match), ("Primary", self.s_primary)]:
            v.addLayout(_form_row(t, w))
        v.addSpacing(4)
        v.addWidget(btn("Add source", self._src_add), alignment=Qt.AlignLeft)
        self.v.addWidget(c)

    def _src_add(self):
        name = self.s_name.text().strip(); fc = self.s_from.text().strip(); sc = self.s_subj.text().strip()
        if not name or not (fc or sc):
            QMessageBox.information(self.win, "Missing", "Give a name and at least a from/subject filter.")
            return
        cfg = config.load()
        cfg.setdefault("sources", []).append({"name": name, "from_contains": fc, "subject_contains": sc,
                                              "match": self.s_match.currentText(), "primary": self.s_primary.currentText()})
        config.save(cfg); self.on_show()

    def _src_edit(self, src):
        SourceDialog(self.win, src, on_done=self.on_show).exec_()

    def _src_remove(self, name):
        cfg = config.load()
        cfg["sources"] = [s for s in cfg.get("sources", []) if s["name"] != name]
        config.save(cfg); self.on_show()

    def _general(self, cfg):
        c = card(); v = QVBoxLayout(c); v.setContentsMargins(16, 14, 16, 14)
        v.addWidget(lbl("Preferences", bold=True, size=12))
        r1 = QHBoxLayout(); r1.addWidget(lbl("Check for new email every", color=T.TEXT2, size=9))
        self.g_poll = no_wheel(QSpinBox()); self.g_poll.setRange(15, 86400); self.g_poll.setSuffix(" seconds")
        self.g_poll.setValue(int(cfg.get("poll_interval_seconds", 60)))
        r1.addWidget(self.g_poll)
        for label_txt, secs in [("30s", 30), ("1 min", 60), ("2 min", 120), ("5 min", 300)]:
            b = btn(label_txt, lambda _=0, s=secs: self.g_poll.setValue(s), "ghost")
            b.setMaximumWidth(64); r1.addWidget(b)
        r1.addStretch(1); v.addLayout(r1)
        v.addWidget(lbl("Lower = new transactions are caught faster (more frequent Gmail checks). "
                        "60 seconds = once a minute.", color=T.MUTED, size=8, wrap=True))
        r2 = QHBoxLayout(); r2.addWidget(lbl("Backfill days on first run", color=T.TEXT2, size=9))
        self.g_back = no_wheel(QSpinBox()); self.g_back.setRange(0, 3650); self.g_back.setValue(int(cfg.get("backfill_days", 3)))
        r2.addWidget(self.g_back); r2.addStretch(1); v.addLayout(r2)
        self.g_all = QCheckBox("Catch-all: track every email that mentions an amount")
        self.g_all.setChecked(cfg.get("track_all_amount_emails", False)); v.addWidget(self.g_all)
        self.g_notif = QCheckBox("Desktop notifications on new transactions")
        self.g_notif.setChecked(cfg.get("notifications", True)); v.addWidget(self.g_notif)
        trow = QHBoxLayout()
        trow.addWidget(btn("🔔  Send test notification", self.win.send_test_notification, "ghost"))
        trow.addWidget(lbl("Fires a sample alert now — no real transaction needed.", color=T.MUTED, size=8))
        trow.addStretch(1)
        v.addLayout(trow)
        self.g_anim = QCheckBox("Smooth animations")
        self.g_anim.setChecked(cfg.get("animations", True)); v.addWidget(self.g_anim)
        v.addWidget(btn("Save preferences", self._save_general), alignment=Qt.AlignLeft)
        self.v.addWidget(c)

    def _save_general(self):
        cfg = config.load()
        old_interval = int(cfg.get("poll_interval_seconds", 60))
        new_interval = self.g_poll.value()
        cfg["poll_interval_seconds"] = new_interval
        cfg["backfill_days"] = self.g_back.value()
        cfg["track_all_amount_emails"] = self.g_all.isChecked()
        cfg["notifications"] = self.g_notif.isChecked()
        cfg["animations"] = self.g_anim.isChecked()
        config.save(cfg)
        charts.ANIM = self.g_anim.isChecked()
        if new_interval != old_interval:
            # apply the new cadence right away instead of waiting out the old timer
            self.win._log_line(f"Check interval changed to {new_interval}s — applying now.")
            self.win.check_now()
        self.win.toast("Saved", f"Now checking for new email every {new_interval}s.", "in")

    def _categories(self, cfg):
        c = card(); v = QVBoxLayout(c); v.setContentsMargins(16, 14, 16, 14)
        v.addWidget(lbl("Your categories", bold=True, size=12))
        v.addWidget(lbl(f"{len(EXPENSE_CATEGORIES) + len(INCOME_CATEGORIES)} built-in categories. "
                        "Add your own here — or just type a new one while tagging a transaction.",
                        color=T.MUTED, size=9, wrap=True))
        customs = engine.custom_categories()
        if customs:
            for name in customs:
                r = QHBoxLayout()
                r.addWidget(lbl("•  " + name, color=T.TEXT2, size=10)); r.addStretch(1)
                r.addWidget(btn("Remove", lambda _=0, n=name: self._cat_remove(n), "ghost"))
                v.addLayout(r)
        else:
            v.addWidget(lbl("No custom categories yet.", color=T.MUTED, size=9))
        row = QHBoxLayout()
        self.new_cat = QLineEdit(); self.new_cat.setPlaceholderText("New category name…")
        row.addWidget(self.new_cat, 1)
        row.addWidget(btn("Add category", self._cat_add))
        v.addLayout(row)
        self.v.addWidget(c)

    def _cat_add(self):
        name = self.new_cat.text().strip()
        if not name:
            return
        if engine.add_custom_category(name):
            self.win.toast("Category added", f"'{name}' is now in every dropdown.", "in")
        self.on_show()

    def _cat_remove(self, name):
        engine.remove_custom_category(name)
        self.on_show()

    def _cache(self, cfg):
        c = card(); v = QVBoxLayout(c); v.setContentsMargins(16, 14, 16, 14)
        v.addWidget(lbl("Email cache & recovery", bold=True, size=12))
        v.addWidget(lbl(f"Local cache holds {engine.cache_count():,} emails (speeds up re-scans).",
                        color=T.MUTED, size=9))
        r = QHBoxLayout()
        r.addWidget(btn("Recover missed txns from cache", self._recover, "ghost"))
        r.addWidget(btn("Send recent to Review", self._to_review, "ghost"))
        r.addWidget(btn("Clear cache", self._clear, "danger")); r.addStretch(1)
        v.addLayout(r)
        self.v.addWidget(c)

    def _to_review(self):
        n = engine.send_recent_to_review(3)
        self.win.toast("Sent to Review", f"{n} recent transaction(s) moved to Review to verify.", "in")
        self.win.refresh_after_change()

    def _recover(self):
        self.win.toast("Recovering…", "Re-parsing cached emails.", "info")
        n = engine.recover_from_cache()
        self.win.toast("Recovery done", f"Recovered {n} transaction(s).", "in")
        self.win.refresh_after_change()

    def _clear(self):
        if QMessageBox.question(self.win, "Clear cache", "Clear the local email cache? Next scan re-downloads.") != QMessageBox.Yes:
            return
        engine.clear_cache(); self.on_show()


def _clear_layout(lay):
    while lay.count():
        it = lay.takeAt(0); w = it.widget()
        if w:
            w.deleteLater()
        elif it.layout():
            _clear_layout(it.layout())


# =================================================== toast
class Toast(QFrame):
    def __init__(self, parent, title, msg, color, on_click=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.on_click = on_click
        self.setStyleSheet(f"QFrame#card{{border-left:4px solid {color};}}")
        v = QVBoxLayout(self); v.setContentsMargins(14, 10, 14, 10); v.setSpacing(2)
        v.addWidget(lbl(title, bold=True))
        m = lbl(msg, color=T.TEXT2, size=9); m.setWordWrap(True); v.addWidget(m)
        self.setFixedWidth(300)
        self.adjustSize()

    def mousePressEvent(self, e):
        if self.on_click:
            self.on_click()
        self.close()


# =================================================== main window
class MainWindow(QMainWindow):
    notifClicked = pyqtSignal()          # emitted (from any thread) when a toast is clicked

    def __init__(self):
        super().__init__()
        self.setWindowTitle("WhoAteMySalary")
        self.setWindowIcon(make_icon())
        # size to the screen actually in front of the user: the old fixed
        # 1240×820 / min 1080×700 spilled off small or DPI-scaled displays
        avail = QApplication.primaryScreen().availableGeometry()
        self.setMinimumSize(min(1000, avail.width() - 24), min(600, avail.height() - 24))
        self.resize(min(1240, avail.width() - 24), min(820, avail.height() - 24))

        cfg = engine.init()
        charts.ANIM = bool(cfg.get("animations", True))
        today = date.today()
        # default view = the last 2 days (user can widen it with the presets)
        self.rng_from = (today - timedelta(days=2)).isoformat()
        self.rng_to = today.isoformat()
        # dashboard scope: "" = everything. Set from the Overview page's pickers and
        # inherited by every drill-in dialog it opens.
        self.f_bank = self.f_card = self.f_source = ""
        self.session_new_ids = set()
        self._toasts = []
        self._activity = []
        self._logdlg = None

        central = QWidget(); self.setCentralWidget(central)
        h = QHBoxLayout(central); h.setContentsMargins(0, 0, 0, 0); h.setSpacing(0)
        h.addWidget(self._sidebar())
        main = QWidget(); mv = QVBoxLayout(main); mv.setContentsMargins(24, 18, 24, 20); mv.setSpacing(12)
        mv.addWidget(self._topbar())
        self.stack = QStackedWidget()
        self.pages = {
            "Overview": OverviewPage(self), "Inbox": InboxPage(self),
            "Transactions": TransactionsPage(self), "Scan": ScanPage(self),
            "Parser": ParserPage(self), "Settings": SettingsPage(self),
        }
        for key, *_ in NAV:
            self.stack.addWidget(self.pages[key])
        mv.addWidget(self.stack, 1)
        h.addWidget(main, 1)

        # tray
        self.tray = QSystemTrayIcon(make_icon(), self)
        self.tray.setToolTip("WhoAteMySalary")
        try:
            self.tray.show()
        except Exception:
            pass

        # poller
        self.poller = PollerWorker()
        self.poller.pollStart.connect(lambda: self.set_status("checking"))
        self.poller.pollDone.connect(self._poll_done)
        self.poller.newTxn.connect(self._new_txn)
        self.poller.logLine.connect(self._log_line)
        self.notifClicked.connect(self._focus_review)   # click a toast -> Review
        self.poller.start()

        self.show_page("Overview")
        self.refresh_counts()
        self._log_line("App started. Background checker running; first check in ~1s.")
        self._log_line("Tip: click the status pill (top-right) any time to see this log.")

    # ---- sidebar
    def _sidebar(self):
        s = QFrame(); s.setObjectName("sidebar"); s.setFixedWidth(224)
        v = QVBoxLayout(s); v.setContentsMargins(16, 20, 16, 16); v.setSpacing(6)
        head = QHBoxLayout()
        logo = QLabel(); logo.setPixmap(_app_pixmap(34))
        head.addWidget(logo)
        tt = QVBoxLayout(); tt.setSpacing(0)
        tt.addWidget(lbl("WhoAteMySalary", bold=True, size=11))
        tt.addWidget(lbl("where'd it go?", color=T.MUTED, size=8))
        head.addLayout(tt); head.addStretch(1)
        v.addLayout(head)
        v.addSpacing(12)
        self.nav_btns = {}
        grp = QButtonGroup(self); grp.setExclusive(True)
        for key, glyph, title, sub in NAV:
            b = QPushButton(f"  {glyph}   {title}")
            b.setObjectName("nav"); b.setCheckable(True); b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=0, k=key: self.show_page(k))
            grp.addButton(b); v.addWidget(b)
            self.nav_btns[key] = b
        v.addStretch(1)
        self.side_status = lbl("● connecting…", color=T.YELLOW, bold=True, size=9)
        self.side_status.setCursor(Qt.PointingHandCursor)
        self.side_status.setToolTip("Click to see the live activity log")
        self.side_status.mousePressEvent = lambda e: self.show_logs()
        v.addWidget(self.side_status)
        self.side_count = lbl("", color=T.MUTED, size=8)
        v.addWidget(self.side_count)
        logbtn = btn("View activity log", self.show_logs, "ghost")
        v.addWidget(logbtn)
        return s

    # ---- topbar
    def _topbar(self):
        t = QFrame(); t.setObjectName("topbar")
        h = QHBoxLayout(t); h.setContentsMargins(0, 0, 0, 0)
        left = QVBoxLayout(); left.setSpacing(2)
        self.title_lbl = lbl("Overview", bold=True, size=18)
        self.sub_lbl = lbl("Your spending at a glance", color=T.MUTED, size=10)
        left.addWidget(self.title_lbl); left.addWidget(self.sub_lbl)
        h.addLayout(left); h.addStretch(1)
        self.badge = lbl("", size=9)
        self.badge.setStyleSheet(f"background:{T.RED2}; color:white; padding:5px 10px; border-radius:9px;")
        self.badge.setVisible(False)
        h.addWidget(self.badge)
        self.status_pill = lbl("● connecting", color=T.YELLOW, bold=True, size=9)
        self.status_pill.setStyleSheet(f"background:{T.PANEL}; color:{T.YELLOW}; padding:6px 12px; border-radius:9px;")
        self.status_pill.setCursor(Qt.PointingHandCursor)
        self.status_pill.setToolTip("Click to see the live activity log")
        self.status_pill.mousePressEvent = lambda e: self.show_logs()
        h.addWidget(self.status_pill)
        h.addWidget(btn("⟳  Check now", self.check_now))
        return t

    # ---- navigation
    def show_page(self, key):
        self.stack.setCurrentWidget(self.pages[key])
        if key in self.nav_btns:
            self.nav_btns[key].setChecked(True)
        meta = next(n for n in NAV if n[0] == key)
        self.title_lbl.setText(meta[2]); self.sub_lbl.setText(meta[3])
        try:
            self.pages[key].on_show()
        except Exception as e:
            print("[page]", key, e)

    # ---- status / counts
    def set_status(self, mode):
        m = {"live": ("● Live", T.GREEN), "offline": ("○ Offline", T.RED2),
             "checking": ("◌ Checking…", T.YELLOW), "connecting": ("● connecting", T.YELLOW)}
        txt, col = m.get(mode, ("● Live", T.GREEN))
        self.status_pill.setText(txt)
        self.status_pill.setStyleSheet(f"background:{T.PANEL}; color:{col}; padding:6px 12px; border-radius:9px;")
        self.side_status.setText(txt)
        self.side_status.setStyleSheet(f"color:{col}; background:transparent; font-weight:700;")

    def refresh_counts(self):
        c = engine.counts()
        pend = c["pend"] or 0
        self.side_count.setText(f"{engine.total_stored():,} stored · {pend} to review")
        if pend:
            self.badge.setText(f"{pend} to review"); self.badge.setVisible(True)
        else:
            self.badge.setVisible(False)

    def check_now(self):
        self.set_status("checking")
        self._log_line("Manual check requested — waking the checker…")
        self.poller.check_now()

    # ---- activity log
    def _log_line(self, s):
        entry = f"[{time.strftime('%H:%M:%S')}] {s}"
        self._activity.append(entry)
        if len(self._activity) > 500:
            del self._activity[:len(self._activity) - 500]
        if self._logdlg is not None and self._logdlg.isVisible():
            self._logdlg.append(entry)
        try:
            print("[activity]", entry)
        except Exception:
            pass

    def show_logs(self):
        if self._logdlg is None:
            self._logdlg = ActivityLog(self)
        self._logdlg.set_lines(self._activity or ["(no activity yet — a check runs every few minutes)"])
        self._logdlg.show()
        self._logdlg.raise_()
        self._logdlg.activateWindow()

    def refresh_after_change(self):
        self.refresh_counts()
        cur = self.stack.currentWidget()
        try:
            cur.on_show()
        except Exception:
            pass

    def scope_text(self):
        """Human-readable summary of the active bank/card/filter scope ('' if none)."""
        bits = [b for b in (self.f_bank,
                            f"card ••••{self.f_card}" if self.f_card else "",
                            f"filter “{self.f_source}”" if self.f_source else "") if b]
        return "  ·  ".join(bits)

    # ---- dialogs
    def open_category(self, cat, direction):
        TxnDialog(self, cat, direction=direction, category=cat).exec_()

    def open_txns(self, title, direction=None, category=None, search="", bucket=None):
        TxnDialog(self, title, direction=direction, category=category,
                  search=search, bucket=bucket).exec_()

    def open_bulk(self, ids, disp, on_done=None):
        BulkDialog(self, ids, disp, on_done).exec_()

    def open_tag(self, row, on_done=None):
        TagDialog(self, row, on_done).exec_()

    # ---- poller slots
    def _poll_done(self, p):
        self.set_status("live" if p.get("online", True) else "offline")
        self.refresh_counts()
        if p.get("found"):
            self.pages["Inbox"].on_show()

    def _focus_review(self):
        """Bring the window forward and open the Review page (toast was clicked)."""
        try:
            if self.isMinimized():
                self.showNormal()
            self.raise_()
            self.activateWindow()
        except Exception:
            pass
        self.show_page("Inbox")

    def _new_txn(self, p):
        self.session_new_ids.add(p["id"])
        auto = p.get("auto")
        sign = "+" if p["dir"] == "IN" else "-"
        quip = goblin.found()                       # e.g. "🧌 The Money Goblin sniffed out…"
        facts = f"{sign} Rs {T.inr(p['amount'])}  ·  {p['merchant']}  ->  {p['cat']}"
        if config.load().get("notifications", True):
            # real Windows toast; the Money Goblin's line leads, the facts follow.
            fired = False
            try:
                fired = notify.notify(quip, facts, on_click=self.notifClicked.emit)
            except Exception:
                fired = False
            if not fired:
                try:
                    self.tray.showMessage(quip, facts, QSystemTrayIcon.Information, 6000)
                except Exception:
                    pass
        # in-app slide-in toast (also opens Review on click)
        self.toast(f"{sign} ₹{T.inr(p['amount'])}  ·  {p['bank']}",
                   f"{quip}\n{p['merchant']}  →  {p['cat']}"
                   + ("  (auto-filed)" if auto else "  · tap to review"),
                   "in" if p["dir"] == "IN" else "out",
                   on_click=self._focus_review)
        # if a transaction that still needs review arrives while the dashboard is
        # open, pop up its review right there
        if not auto and isinstance(self.stack.currentWidget(), OverviewPage):
            row = engine.get_txn(p["id"])
            if row:
                TagDialog(self, row, on_done=self.refresh_after_change).show()

    def send_test_notification(self):
        """Fire a sample notification through the real path — no payment needed."""
        self._log_line("Sending a test system notification…")
        title = goblin.found()
        msg = "- Rs 199  ·  Coffee Shop  ->  Food & dining  (test)"
        ok = False
        try:
            ok = notify.notify(title, msg)
        except Exception as e:
            self._log_line(f"Test notification error: {e}")
        if not ok:
            try:
                self.tray.showMessage("WhoAteMySalary (test)", msg,
                                      QSystemTrayIcon.Information, 6000)
                ok = True
            except Exception:
                pass
        self.toast("Test notification sent",
                   f"Shown via '{notify.backend()}'. If it didn't appear in your notification "
                   f"panel (or was silent), check Windows → System → Notifications / Focus assist.",
                   "info", on_click=self.show_logs)
        self._log_line(f"Test notification sent via '{notify.backend()}' "
                       f"({'ok' if ok else 'no toast backend — check console'}).")

    # ---- toasts
    def toast(self, title, msg, kind="info", on_click=None):
        colors = {"info": T.ACCENT, "in": T.GREEN, "out": T.RED, "warn": T.YELLOW}
        t = Toast(self, title, msg, colors.get(kind, T.ACCENT), on_click)
        self._toasts.append(t)
        t.show()
        self._reflow_toasts()
        eff = QGraphicsOpacityEffect(t); t.setGraphicsEffect(eff)
        anim = QPropertyAnimation(eff, b"opacity", t)
        anim.setStartValue(0.0); anim.setEndValue(1.0); anim.setDuration(220 if charts.ANIM else 1)
        anim.start(QAbstractAnimation.DeleteWhenStopped)
        QTimer.singleShot(5200, lambda: self._close_toast(t))

    def _close_toast(self, t):
        if t in self._toasts:
            self._toasts.remove(t)
            t.close(); t.deleteLater()
            self._reflow_toasts()

    def _reflow_toasts(self):
        y = self.height() - 20
        for t in reversed(self._toasts):
            t.adjustSize()
            y -= t.height() + 10
            t.move(self.width() - t.width() - 20, y)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._reflow_toasts()

    def closeEvent(self, e):
        try:
            self.poller.stop()
            self.poller.wait(2000)
        except Exception:
            pass
        super().closeEvent(e)


def _make_caret():
    """Draw a small down-caret PNG and return its (forward-slash) path for QSS."""
    import tempfile
    from PyQt5.QtGui import QPolygon
    from PyQt5.QtCore import QPoint
    path = os.path.join(tempfile.gettempdir(), "mmt_caret.png")
    pm = QPixmap(14, 9); pm.fill(Qt.transparent)
    p = QPainter(pm); p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen); p.setBrush(QColor(T.TEXT2))
    p.drawPolygon(QPolygon([QPoint(1, 1), QPoint(13, 1), QPoint(7, 8)]))
    p.end()
    pm.save(path)
    return path.replace("\\", "/")


def main():
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setFont(QFont(T.FONT, 10))
    app.setStyleSheet(T.QSS.replace("__CARET__", _make_caret()))
    app.setWindowIcon(make_icon())

    splash = Splash()
    splash.show()
    splash.note("Starting up…")

    t0 = time.time()
    splash.note("Opening your ledger…")
    win = MainWindow()                       # engine.init(): DB, config, migrations
    splash.note("Waking the Money Goblin…")

    # Keep the logo up briefly so it reads as a splash instead of a flash.
    while time.time() - t0 < 1.3:
        splash.tick()
        time.sleep(0.02)

    splash.finish(win)
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
