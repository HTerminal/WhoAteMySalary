# -*- coding: utf-8 -*-
"""Dark theme (Qt stylesheet), palette and number/colour helpers."""

FONT = "Segoe UI"

BG      = "#0e1422"
SIDEBAR = "#0a0f1c"
PANEL   = "#161d2e"
CARD    = "#161d2e"
PANEL2  = "#1d2740"
BORDER  = "#28324b"
BORDER2 = "#39456a"
TEXT    = "#e9eef8"
TEXT2   = "#aab4cc"
MUTED   = "#7c88a4"
ACCENT  = "#5b7cfa"
ACCENT2 = "#89a2ff"
GREEN   = "#26c281"
RED     = "#f2683c"
RED2    = "#ef5350"
YELLOW  = "#f2b134"

PAL = ["#5b7cfa", "#e8663d", "#26c281", "#f2b134", "#8b5cf6", "#ef4d7a",
       "#12b5cb", "#c084fc", "#f97316", "#38bdf8", "#a3e635", "#fb7185",
       "#2dd4bf", "#facc15", "#94a3b8"]


QSS = f"""
* {{ font-family: "{FONT}"; font-size: 10.5pt; color: {TEXT}; }}
QWidget {{ background: {BG}; }}
QMainWindow, QDialog {{ background: {BG}; }}

/* cards / surfaces */
QFrame#card {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 14px; }}
QFrame#sidebar {{ background: {SIDEBAR}; border: none; }}
QFrame#topbar {{ background: {BG}; border: none; }}
QFrame#hline {{ background: {BORDER}; max-height: 1px; border: none; }}

QLabel {{ background: transparent; }}
QLabel#h1 {{ font-size: 18pt; font-weight: 700; }}
QLabel#h2 {{ font-size: 13pt; font-weight: 700; }}
QLabel#muted {{ color: {MUTED}; }}
QLabel#sub {{ color: {MUTED}; font-size: 9.5pt; }}

/* nav buttons */
QPushButton#nav {{ background: transparent; border: none; border-radius: 9px;
    text-align: left; padding: 10px 14px; color: {TEXT2}; font-weight: 600; }}
QPushButton#nav:hover {{ background: {PANEL}; }}
QPushButton#nav:checked {{ background: {PANEL}; color: {TEXT}; border-left: 3px solid {ACCENT}; }}

/* buttons */
QPushButton {{ background: {ACCENT}; color: white; border: none; border-radius: 8px;
    padding: 8px 16px; font-weight: 600; }}
QPushButton:hover {{ background: {ACCENT2}; }}
QPushButton:pressed {{ background: #4a68e0; }}
QPushButton#ghost {{ background: {PANEL2}; color: {TEXT}; border: 1px solid {BORDER2}; }}
QPushButton#ghost:hover {{ background: {BORDER2}; }}
QPushButton#green {{ background: {GREEN}; color: #06281c; }}
QPushButton#green:hover {{ background: #37d494; }}
QPushButton#danger {{ background: {RED2}; }}
QPushButton#danger:hover {{ background: #ff6b66; }}
QPushButton:disabled {{ background: {PANEL2}; color: {MUTED}; }}

/* inputs */
QLineEdit, QComboBox, QDateEdit, QSpinBox, QPlainTextEdit, QTextEdit {{
    background: {PANEL2}; border: 1px solid {BORDER}; border-radius: 8px;
    padding: 6px 8px; color: {TEXT}; selection-background-color: {ACCENT}; }}
QLineEdit:focus, QComboBox:focus, QDateEdit:focus {{ border: 1px solid {ACCENT}; }}
QComboBox::drop-down, QDateEdit::drop-down {{ subcontrol-origin: padding;
    subcontrol-position: center right; border: none; width: 24px; }}
/* caret icon — generated at runtime, path substituted for __CARET__ */
QComboBox::down-arrow, QDateEdit::down-arrow {{ image: url(__CARET__); width: 12px; height: 8px; }}
QComboBox QAbstractItemView {{ background: {PANEL2}; color: {TEXT};
    selection-background-color: {ACCENT}; border: 1px solid {BORDER}; outline: none; }}
QCheckBox {{ background: transparent; color: {TEXT2}; spacing: 8px; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border-radius: 4px;
    border: 1px solid {BORDER2}; background: {PANEL2}; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border: 1px solid {ACCENT}; }}

/* calendar popup for QDateEdit */
QCalendarWidget QWidget {{ alternate-background-color: {PANEL}; background: {PANEL2}; }}
QCalendarWidget QAbstractItemView:enabled {{ background: {PANEL2}; color: {TEXT};
    selection-background-color: {ACCENT}; selection-color: white; }}
QCalendarWidget QToolButton {{ background: {PANEL2}; color: {TEXT}; }}
QCalendarWidget QToolButton:hover {{ background: {BORDER2}; }}
QCalendarWidget QMenu {{ background: {PANEL2}; color: {TEXT}; }}
QCalendarWidget QSpinBox {{ background: {PANEL2}; color: {TEXT}; }}

/* tables & trees */
QTableWidget, QTreeWidget, QTableView, QTreeView {{ background: {PANEL}; alternate-background-color: #12192a;
    border: none; gridline-color: {BORDER}; outline: none; }}
QTableWidget::item, QTreeWidget::item {{ padding: 4px 6px; border: none; }}
QTableWidget::item:selected, QTreeWidget::item:selected {{ background: {ACCENT}; color: white; }}
QHeaderView::section {{ background: {PANEL2}; color: {TEXT2}; padding: 7px 8px;
    border: none; border-right: 1px solid {BORDER}; font-weight: 600; }}
QHeaderView::section:hover {{ background: {BORDER2}; color: {TEXT}; }}
QTreeWidget::branch {{ background: transparent; }}

/* scrollbars */
QScrollBar:vertical {{ background: {BG}; width: 11px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {PANEL2}; border-radius: 5px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {BORDER2}; }}
QScrollBar:horizontal {{ background: {BG}; height: 11px; margin: 0; }}
QScrollBar::handle:horizontal {{ background: {PANEL2}; border-radius: 5px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollArea {{ border: none; background: {BG}; }}
QScrollArea > QWidget > QWidget {{ background: {BG}; }}

QToolTip {{ background: {PANEL2}; color: {TEXT}; border: 1px solid {BORDER2}; padding: 5px; }}
"""


# ---------- number formatting (Indian grouping) ----------
def inr(n):
    n = float(n); neg = n < 0; n = abs(n); whole = f"{n:.0f}"
    if len(whole) > 3:
        last3 = whole[-3:]; rest = whole[:-3]; parts = []
        while len(rest) > 2:
            parts.insert(0, rest[-2:]); rest = rest[:-2]
        if rest:
            parts.insert(0, rest)
        whole = ",".join(parts) + "," + last3
    return ("-" if neg else "") + whole


def inr2(n):
    """Indian-grouped amount keeping paise — '-1,60,306.75'. For statements, where
    inr()'s rounding to whole rupees would stop the column adding up."""
    n = round(float(n), 2)
    sign = "-" if n < 0 else ""
    n = abs(n)
    whole = int(n)
    paise = int(round((n - whole) * 100))
    if paise == 100:                       # 999.999 -> 1000.00, not 999.100
        whole += 1
        paise = 0
    return f"{sign}{inr(whole)}.{paise:02d}"


def lakh(n):
    n = float(n)
    if abs(n) >= 1e7:
        return f"{n/1e7:.2f} Cr"
    if abs(n) >= 1e5:
        return f"{n/1e5:.2f} L"
    return inr(n)


# ---------- colour helpers ----------
def _rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def _hx(t):
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(round(v)))) for v in t)


def mix(c1, c2, t):
    a = _rgb(c1); b = _rgb(c2)
    return _hx(tuple(a[i] + (b[i] - a[i]) * t for i in range(3)))


def lighten(c, t=0.2):
    return mix(c, "#ffffff", t)


def darken(c, t=0.2):
    return mix(c, "#000000", t)


def source_color(key):
    key = (key or "").strip()
    if not key:
        return MUTED
    h = sum(ord(c) * (i + 1) for i, c in enumerate(key))
    return PAL[h % len(PAL)]
