# -*- coding: utf-8 -*-
"""Custom QPainter chart widgets — smooth, GPU-composited, no jitter.
Donut (hover + click), grouped month bars, income bars, count-up KPI cards."""
import math
from PyQt5.QtWidgets import QWidget, QFrame, QLabel, QVBoxLayout, QTableWidgetItem
from PyQt5.QtCore import (Qt, QRectF, pyqtSignal, pyqtProperty, QPropertyAnimation,
                          QVariantAnimation, QEasingCurve, QAbstractAnimation)
from PyQt5.QtGui import QPainter, QColor, QPen, QFont, QImage
import theme as T

ANIM = True          # global switch (set from config at startup)


def render_donut(data, px=900, center_top="", center_big="",
                 bg="#ffffff", ink="#111111", muted="#666666"):
    """The dashboard's spending donut, painted onto a light QImage for the PDF
    report. Rendered oversized and scaled down in the document so it stays crisp
    in print. `data` is the (label, value, colour) list build_dashboard returns."""
    img = QImage(px, px, QImage.Format_ARGB32)
    img.fill(QColor(bg))
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    d = px * 0.94
    c = px / 2
    rect = QRectF(c - d / 2, c - d / 2, d, d)
    data = [(l, v, col) for (l, v, col) in data if v > 0]
    if not data:
        p.setPen(Qt.NoPen); p.setBrush(QColor("#eef1f7")); p.drawEllipse(rect)
        p.setPen(QColor(muted)); p.setFont(QFont(T.FONT, int(px / 22)))
        p.drawText(rect, Qt.AlignCenter, "no spending")
        p.end()
        return img

    total = sum(v for _, v, _ in data) or 1
    cum = 0.0
    for _label, val, color in data:
        span = val / total * 360
        p.setBrush(QColor(color))
        p.setPen(QPen(QColor(bg), max(2.0, px / 260)))     # thin gap between slices
        p.drawPie(rect, round((90 - cum) * 16), round(-span * 16))
        cum += span

    ir = d * 0.62 / 2                                       # punch the hole
    p.setBrush(QColor(bg)); p.setPen(Qt.NoPen)
    p.drawEllipse(QRectF(c - ir, c - ir, 2 * ir, 2 * ir))

    if center_top:
        p.setPen(QColor(muted)); p.setFont(QFont(T.FONT, int(px / 30)))
        p.drawText(QRectF(c - ir, c - px * 0.09, 2 * ir, px * 0.07),
                   Qt.AlignCenter, center_top)
    if center_big:
        f = QFont(T.FONT, int(px / 18)); f.setBold(True)
        p.setFont(f); p.setPen(QColor(ink))
        p.drawText(QRectF(c - ir, c - px * 0.035, 2 * ir, px * 0.09),
                   Qt.AlignCenter, center_big)
    p.end()
    return img


class NumItem(QTableWidgetItem):
    """Table item that sorts by an underlying number while showing formatted text."""
    def __init__(self, text, value):
        super().__init__(text)
        self._v = value

    def __lt__(self, other):
        try:
            return self._v < other._v
        except Exception:
            return super().__lt__(other)


class DonutChart(QWidget):
    sliceClicked = pyqtSignal(str)

    def __init__(self, parent=None, size=250):
        super().__init__(parent)
        self.setMinimumSize(size, size)
        self.setMouseTracking(True)
        self._data = []
        self._top = ""
        self._big = ""
        self._hover = None
        self._progress = 1.0
        self._anim = None

    def getProgress(self):
        return self._progress

    def setProgress(self, v):
        self._progress = v
        self.update()

    progress = pyqtProperty(float, fget=getProgress, fset=setProgress)

    def setData(self, data, center_top="", center_big="", animate=True):
        self._data = [(l, v, c) for (l, v, c) in data if v > 0]
        self._top, self._big = center_top, center_big
        self._hover = None
        if animate and ANIM and self._data:
            self._anim = QPropertyAnimation(self, b"progress")
            self._anim.setStartValue(0.0)
            self._anim.setEndValue(1.0)
            self._anim.setDuration(420)
            self._anim.setEasingCurve(QEasingCurve.OutCubic)
            self._anim.start(QAbstractAnimation.DeleteWhenStopped)
        else:
            self._progress = 1.0
            self.update()

    def _geom(self):
        W, H = self.width(), self.height()
        side = min(W, H)
        d = side - 16
        return W / 2, H / 2, d

    def _hit(self, x, y):
        cx, cy, d = self._geom()
        r = math.hypot(x - cx, y - cy)
        if not (d * 0.30 <= r <= d / 2) or not self._data:
            return None
        ma = math.degrees(math.atan2(cy - y, x - cx)) % 360
        off = (90 - ma) % 360
        total = sum(v for _, v, _ in self._data) or 1
        cum = 0.0
        for i, (label, val, color) in enumerate(self._data):
            span = val / total * 360
            if cum <= off < cum + span:
                return i
            cum += span
        return None

    def mouseMoveEvent(self, e):
        h = self._hit(e.x(), e.y())
        self.setCursor(Qt.PointingHandCursor if h is not None else Qt.ArrowCursor)
        if h != self._hover:
            self._hover = h
            self.update()

    def leaveEvent(self, e):
        if self._hover is not None:
            self._hover = None
            self.update()

    def mousePressEvent(self, e):
        h = self._hit(e.x(), e.y())
        if h is not None:
            self.sliceClicked.emit(self._data[h][0])

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        cx, cy, d = self._geom()
        rect = QRectF(cx - d / 2, cy - d / 2, d, d)
        if not self._data:
            p.setPen(Qt.NoPen); p.setBrush(QColor(T.PANEL2)); p.drawEllipse(rect)
            p.setPen(QColor(T.MUTED)); p.setFont(QFont(T.FONT, 11))
            p.drawText(rect, Qt.AlignCenter, "no data")
            return
        total = sum(v for _, v, _ in self._data) or 1
        maxoff = self._progress * 360
        cum = 0.0
        for i, (label, val, color) in enumerate(self._data):
            span = val / total * 360
            if cum >= maxoff:
                break
            draw = min(span, maxoff - cum)
            col = QColor(T.lighten(color, 0.22) if i == self._hover else color)
            p.setBrush(col)
            p.setPen(QPen(QColor(T.CARD), 2))
            p.drawPie(rect, round((90 - cum) * 16), round(-draw * 16))
            cum += span
        ir = d * 0.60 / 2
        p.setBrush(QColor(T.CARD)); p.setPen(Qt.NoPen)
        p.drawEllipse(QRectF(cx - ir, cy - ir, 2 * ir, 2 * ir))
        if self._hover is not None and self._hover < len(self._data):
            label, val, color = self._data[self._hover]
            self._center(p, cx, cy, label[:20], "Rs " + T.inr(val),
                         f"{val/total*100:.1f}%  ·  click to open", color)
        else:
            self._center(p, cx, cy, self._top, self._big, "", T.MUTED)

    def _center(self, p, cx, cy, top, big, sub, topcol):
        p.setPen(QColor(topcol)); p.setFont(QFont(T.FONT, 9))
        p.drawText(QRectF(cx - 80, cy - 32, 160, 18), Qt.AlignCenter, top)
        f = QFont(T.FONT, 15); f.setBold(True); p.setFont(f); p.setPen(QColor(T.TEXT))
        p.drawText(QRectF(cx - 85, cy - 12, 170, 24), Qt.AlignCenter, big)
        if sub:
            p.setPen(QColor(T.TEXT2)); p.setFont(QFont(T.FONT, 8))
            p.drawText(QRectF(cx - 80, cy + 14, 160, 14), Qt.AlignCenter, sub)


class MonthBars(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(250)
        self.setMouseTracking(True)
        self.months, self.m_in, self.m_out, self.mnames = [], {}, {}, {}
        self._progress = 1.0
        self._anim = None

    def getProgress(self):
        return self._progress

    def setProgress(self, v):
        self._progress = v
        self.update()

    progress = pyqtProperty(float, fget=getProgress, fset=setProgress)

    def setData(self, months, m_in, m_out, mnames, animate=True):
        self.months, self.m_in, self.m_out, self.mnames = months, m_in, m_out, mnames
        if animate and ANIM and months:
            self._anim = QPropertyAnimation(self, b"progress")
            self._anim.setStartValue(0.0); self._anim.setEndValue(1.0)
            self._anim.setDuration(440); self._anim.setEasingCurve(QEasingCurve.OutCubic)
            self._anim.start(QAbstractAnimation.DeleteWhenStopped)
        else:
            self._progress = 1.0; self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        W, H = self.width(), self.height()
        if not self.months:
            p.setPen(QColor(T.MUTED)); p.setFont(QFont(T.FONT, 11))
            p.drawText(self.rect(), Qt.AlignCenter, "no monthly data")
            return
        inc = [self.m_in.get(k, 0) for k in self.months]
        out = [self.m_out.get(k, 0) for k in self.months]
        mx = max(inc + out + [1])
        padl, padr, padt, padb = 56, 14, 18, 34
        cw = W - padl - padr
        ch = H - padt - padb
        n = len(self.months)
        slot = cw / n
        bw = min(24, slot * 0.30)
        base = padt + ch

        def Y(v):
            return base - (v / mx) * ch * self._progress
        p.setPen(QPen(QColor(T.BORDER), 1))
        for i in range(5):
            yy = base - ch * i / 4
            p.setPen(QPen(QColor(T.BORDER if i == 0 else T.PANEL2), 1))
            p.drawLine(int(padl), int(yy), int(W - padr), int(yy))
            p.setPen(QColor(T.MUTED)); p.setFont(QFont(T.FONT, 8))
            p.drawText(QRectF(0, yy - 8, padl - 8, 16), Qt.AlignRight | Qt.AlignVCenter, T.lakh(mx * i / 4))
        for i, k in enumerate(self.months):
            x0 = padl + slot * i + slot / 2
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(T.GREEN))
            p.drawRect(QRectF(x0 - bw - 2, Y(inc[i]), bw, base - Y(inc[i])))
            p.setBrush(QColor(T.RED))
            p.drawRect(QRectF(x0 + 2, Y(out[i]), bw, base - Y(out[i])))
            p.setPen(QColor(T.TEXT2)); p.setFont(QFont(T.FONT, 8))
            p.drawText(QRectF(x0 - slot / 2, base + 6, slot, 16), Qt.AlignCenter, self.mnames.get(k, k))
        # legend
        p.setPen(Qt.NoPen); p.setBrush(QColor(T.GREEN)); p.drawRect(QRectF(padl, 4, 10, 9))
        p.setPen(QColor(T.TEXT2)); p.setFont(QFont(T.FONT, 8))
        p.drawText(QRectF(padl + 14, 2, 30, 14), Qt.AlignVCenter, "in")
        p.setPen(Qt.NoPen); p.setBrush(QColor(T.RED)); p.drawRect(QRectF(padl + 46, 4, 10, 9))
        p.setPen(QColor(T.TEXT2)); p.drawText(QRectF(padl + 60, 2, 30, 14), Qt.AlignVCenter, "out")


class TimeBars(QWidget):
    """Single-series vertical bars over ordered buckets — days, weeks, months or
    weekdays. Bottom labels thin out automatically when buckets are narrow,
    hovering a bucket shows its exact value, and clicking a non-empty bucket
    emits barClicked(key). Used by the drill-in Analytics view."""

    barClicked = pyqtSignal(object)          # the clicked bucket's key

    def __init__(self, parent=None, color=None, min_h=180):
        super().__init__(parent)
        self.setMinimumHeight(min_h)
        self.setMouseTracking(True)
        self.keys, self.vals, self.names = [], {}, {}
        self.color = color or T.ACCENT
        self._progress = 1.0
        self._anim = None
        self._hover = None

    def getProgress(self):
        return self._progress

    def setProgress(self, v):
        self._progress = v
        self.update()

    progress = pyqtProperty(float, fget=getProgress, fset=setProgress)

    def setData(self, keys, vals, names, animate=True):
        self.keys, self.vals, self.names = keys, vals, names
        self._hover = None
        if animate and ANIM and keys:
            self._anim = QPropertyAnimation(self, b"progress")
            self._anim.setStartValue(0.0); self._anim.setEndValue(1.0)
            self._anim.setDuration(420); self._anim.setEasingCurve(QEasingCurve.OutCubic)
            self._anim.start(QAbstractAnimation.DeleteWhenStopped)
        else:
            self._progress = 1.0; self.update()

    _PADL, _PADR, _PADT, _PADB = 56, 14, 20, 30

    def _slot(self, x):
        cw = self.width() - self._PADL - self._PADR
        if not self.keys or cw <= 0:
            return None
        i = int((x - self._PADL) / (cw / len(self.keys)))
        return i if 0 <= i < len(self.keys) else None

    def _has_value(self, i):
        return i is not None and i < len(self.keys) and self.vals.get(self.keys[i], 0) > 0

    def mouseMoveEvent(self, e):
        h = self._slot(e.x())
        self.setCursor(Qt.PointingHandCursor if self._has_value(h) else Qt.ArrowCursor)
        if h != self._hover:
            self._hover = h
            self.update()

    def leaveEvent(self, e):
        if self._hover is not None:
            self._hover = None
            self.update()

    def mousePressEvent(self, e):
        i = self._slot(e.x())
        if self._has_value(i):
            self.barClicked.emit(self.keys[i])

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        W, H = self.width(), self.height()
        if not self.keys:
            p.setPen(QColor(T.MUTED)); p.setFont(QFont(T.FONT, 10))
            p.drawText(self.rect(), Qt.AlignCenter, "no data in this period")
            return
        vals = [self.vals.get(k, 0) for k in self.keys]
        mx = max(vals + [1])
        cw = W - self._PADL - self._PADR
        ch = H - self._PADT - self._PADB
        n = len(self.keys)
        slot = cw / n
        bw = max(2, min(26, slot * 0.62))
        base = self._PADT + ch
        for i in range(5):
            yy = base - ch * i / 4
            p.setPen(QPen(QColor(T.BORDER if i == 0 else T.PANEL2), 1))
            p.drawLine(int(self._PADL), int(yy), int(W - self._PADR), int(yy))
            p.setPen(QColor(T.MUTED)); p.setFont(QFont(T.FONT, 8))
            p.drawText(QRectF(0, yy - 8, self._PADL - 8, 16),
                       Qt.AlignRight | Qt.AlignVCenter, T.lakh(mx * i / 4))
        # bottom labels: draw only as many as fit without colliding
        step = max(1, math.ceil(n / max(1, int(cw // 52))))
        for i, k in enumerate(self.keys):
            v = vals[i]
            x0 = self._PADL + slot * i + slot / 2
            h = (v / mx) * ch * self._progress
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(T.lighten(self.color, 0.25) if i == self._hover else self.color))
            p.drawRoundedRect(QRectF(x0 - bw / 2, base - h, bw, h), 2, 2)
            if i % step == 0:
                p.setPen(QColor(T.TEXT2)); p.setFont(QFont(T.FONT, 8))
                p.drawText(QRectF(x0 - 34, base + 4, 68, 16), Qt.AlignCenter,
                           self.names.get(k, str(k)))
        if self._hover is not None and self._hover < n:
            k = self.keys[self._hover]
            p.setPen(QColor(T.TEXT)); p.setFont(QFont(T.FONT, 9))
            p.drawText(QRectF(self._PADL, 0, cw, 16), Qt.AlignRight | Qt.AlignVCenter,
                       f"{self.names.get(k, k)}  ·  Rs {T.inr(vals[self._hover])}"
                       + ("  ·  click to open" if vals[self._hover] > 0 else ""))


class HBars(QWidget):
    def __init__(self, parent=None, label_w=190, empty="no incoming data"):
        super().__init__(parent)
        self.label_w = label_w
        self.empty = empty
        self.data = []
        self._progress = 1.0
        self._anim = None

    def getProgress(self):
        return self._progress

    def setProgress(self, v):
        self._progress = v
        self.update()

    progress = pyqtProperty(float, fget=getProgress, fset=setProgress)

    def setData(self, data, animate=True):
        self.data = data
        self.setMinimumHeight(max(40, len(data) * 30 + 12))
        if animate and ANIM and data:
            self._anim = QPropertyAnimation(self, b"progress")
            self._anim.setStartValue(0.0); self._anim.setEndValue(1.0)
            self._anim.setDuration(400); self._anim.setEasingCurve(QEasingCurve.OutCubic)
            self._anim.start(QAbstractAnimation.DeleteWhenStopped)
        else:
            self._progress = 1.0; self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if not self.data:
            p.setPen(QColor(T.MUTED)); p.setFont(QFont(T.FONT, 10))
            p.drawText(self.rect(), Qt.AlignCenter, self.empty)
            return
        mx = max((v for _, v, _ in self.data), default=1) or 1
        chart_w = self.width() - self.label_w - 96
        y = 8
        rh = 30
        for label, val, color in self.data:
            w = max(3, (val / mx) * chart_w * self._progress)
            short = label if len(label) <= 26 else label[:25] + "…"
            p.setPen(QColor(T.TEXT2)); p.setFont(QFont(T.FONT, 9))
            p.drawText(QRectF(0, y, self.label_w - 10, rh - 6), Qt.AlignRight | Qt.AlignVCenter, short)
            p.setPen(Qt.NoPen); p.setBrush(QColor(color))
            p.drawRoundedRect(QRectF(self.label_w, y + 2, w, rh - 12), 4, 4)
            p.setPen(QColor(T.MUTED)); p.setFont(QFont(T.FONT, 9))
            p.drawText(QRectF(self.label_w + w + 8, y, 120, rh - 6), Qt.AlignLeft | Qt.AlignVCenter, "Rs " + T.inr(val))
            y += rh


class KPICard(QFrame):
    clicked = pyqtSignal()

    def __init__(self, title, accent=T.ACCENT, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.setFixedHeight(104)
        self.setMinimumWidth(124)
        self.setCursor(Qt.PointingHandCursor)
        v = QVBoxLayout(self)
        v.setContentsMargins(16, 14, 16, 14)
        v.setSpacing(4)
        t = QLabel(title.upper())
        t.setStyleSheet(f"color:{accent}; font-size:8.5pt; font-weight:700; background:transparent;")
        self.val = QLabel("0")
        self.val.setStyleSheet("font-size:18pt; font-weight:700; background:transparent;")
        # let the row of five compress on narrow windows: without this the labels'
        # text width becomes a hard minimum and the last card gets pushed off-screen
        t.setMinimumWidth(1)
        self.val.setMinimumWidth(1)
        v.addWidget(t)
        v.addWidget(self.val)
        v.addStretch(1)
        self._prefix = ""
        self._fmt = T.inr
        self._anim = None

    def mousePressEvent(self, e):
        self.clicked.emit()

    def setValue(self, value, prefix="", fmt=None, animate=True):
        self._prefix = prefix
        self._fmt = fmt or T.inr
        value = float(value)
        if animate and ANIM:
            self._anim = QVariantAnimation(self)
            self._anim.setStartValue(0.0)
            self._anim.setEndValue(value)
            self._anim.setDuration(480)
            self._anim.setEasingCurve(QEasingCurve.OutCubic)
            self._anim.valueChanged.connect(lambda v: self.val.setText(prefix + self._fmt(v)))
            self._anim.finished.connect(lambda: self.val.setText(prefix + self._fmt(value)))
            self._anim.start(QAbstractAnimation.DeleteWhenStopped)
        else:
            self.val.setText(prefix + self._fmt(value))
