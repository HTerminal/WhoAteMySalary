# -*- coding: utf-8 -*-
"""Generate the WhoAteMySalary app icon — a gold rupee coin with a bite taken
out of it (your salary, getting eaten), on the app's indigo tile.

Renders a 1024px master with QPainter (real fonts, so the rupee glyph is crisp),
then writes:
    docs/icon.png     - 1024px master (README / repo)
    icon.ico          - multi-size Windows icon (PyInstaller --icon)
    icon.icns         - macOS icon (PyInstaller BUNDLE)
    docs/icon-256.png - handy medium PNG

    py -3.12 tools/make_icon.py
"""
import os, sys
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import (QImage, QPainter, QColor, QLinearGradient, QRadialGradient,
                         QPen, QBrush, QFont, QPainterPath)
from PyQt5.QtCore import Qt, QRectF, QPointF

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ACCENT_A = "#8aa0ff"; ACCENT_B = "#5b7cfa"; ACCENT_C = "#4259d0"
GOLD_HI = "#ffe7a0"; GOLD_MID = "#f6c454"; GOLD_LO = "#ecb02f"; GOLD_RIM = "#cf8f27"
INK = "#16263f"

app = QApplication(sys.argv)          # default platform (no window shown) → real fonts


def tile_gradient(s):
    g = QLinearGradient(0, 0, s, s)
    g.setColorAt(0.0, QColor(ACCENT_A)); g.setColorAt(0.55, QColor(ACCENT_B))
    g.setColorAt(1.0, QColor(ACCENT_C))
    return g


def draw(s):
    img = QImage(s, s, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.SmoothPixmapTransform, True)
    k = s / 1024.0                     # scale factor from the 1024 design grid

    def S(v):  # scale a design-grid value
        return v * k

    # ---- tile ----
    tile = QPainterPath()
    tile.addRoundedRect(QRectF(0, 0, s, s), S(232), S(232))
    p.fillPath(tile, QBrush(tile_gradient(s)))
    # top gloss
    p.setClipPath(tile)
    gloss = QRadialGradient(QPointF(S(330), S(250)), S(620))
    gloss.setColorAt(0.0, QColor(255, 255, 255, 40)); gloss.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.fillRect(QRectF(0, 0, s, s), QBrush(gloss))
    p.setClipping(False)

    C = QPointF(S(512), S(540)); R = S(286)

    # ---- subtle halo behind the coin (soft, no hard ring) ----
    halo = QRadialGradient(C, S(360))
    halo.setColorAt(0.0, QColor(255, 255, 255, 30)); halo.setColorAt(0.82, QColor(255, 255, 255, 22))
    halo.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.setPen(Qt.NoPen); p.setBrush(QBrush(halo))
    p.drawEllipse(C, S(360), S(360))

    # ---- soft shadow under the coin ----
    sh = QRadialGradient(QPointF(C.x(), C.y() + S(40)), R + S(40))
    sh.setColorAt(0.0, QColor(8, 12, 26, 90)); sh.setColorAt(0.72, QColor(8, 12, 26, 70))
    sh.setColorAt(1.0, QColor(8, 12, 26, 0))
    p.setPen(Qt.NoPen); p.setBrush(QBrush(sh))
    p.drawEllipse(QPointF(C.x(), C.y() + S(46)), R + S(34), R + S(30))

    # ---- coin ----
    coin = QRadialGradient(QPointF(C.x() - S(70), C.y() - S(90)), R * 1.7)
    coin.setColorAt(0.0, QColor(GOLD_HI)); coin.setColorAt(0.55, QColor(GOLD_MID))
    coin.setColorAt(1.0, QColor(GOLD_LO))
    p.setBrush(QBrush(coin)); p.setPen(QPen(QColor(GOLD_RIM), S(12)))
    p.drawEllipse(C, R, R)
    # inner highlight ring
    p.setBrush(Qt.NoBrush); p.setPen(QPen(QColor(255, 255, 255, 70), S(6)))
    p.drawEllipse(C, R - S(26), R - S(26))

    # ---- rupee glyph (drawn before the bite so the bite can eat into it) ----
    f = QFont("Segoe UI"); f.setPixelSize(int(S(452))); f.setBold(True)
    p.setFont(f); p.setPen(QColor(INK))
    p.drawText(QRectF(C.x() - S(258), C.y() - S(300), S(500), S(560)),
               Qt.AlignCenter, "₹")

    # ---- the BITE: union of circles at the top-right, filled with the tile so it
    #      looks like a chunk (and part of the ₹) was eaten ----
    bite = QPainterPath()
    for cx, cy, r in [(742, 322, 178), (596, 300, 74), (788, 476, 78), (700, 214, 60)]:
        c = QPainterPath(); c.addEllipse(QPointF(S(cx), S(cy)), S(r), S(r)); bite += c
    p.setClipPath(bite)
    p.fillPath(tile, QBrush(tile_gradient(s)))        # reveal the tile through the bite
    gloss2 = QRadialGradient(QPointF(S(330), S(250)), S(620))
    gloss2.setColorAt(0.0, QColor(255, 255, 255, 40)); gloss2.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.fillRect(QRectF(0, 0, s, s), QBrush(gloss2))
    # a soft inner shadow where the coin was bitten (gives the bite some depth)
    p.setBrush(Qt.NoBrush); p.setPen(QPen(QColor(120, 74, 14, 120), S(20)))
    p.drawEllipse(C, R, R)
    p.setClipping(False)

    # ---- crumbs near the bite ----
    p.setPen(QPen(QColor(GOLD_RIM), S(3)))
    for cx, cy, r in [(846, 292, 17), (884, 372, 12), (792, 196, 13), (858, 214, 9)]:
        p.setBrush(QColor(GOLD_MID)); p.drawEllipse(QPointF(S(cx), S(cy)), S(r), S(r))

    p.end()
    return img


master = draw(1024)
os.makedirs(os.path.join(ROOT, "docs"), exist_ok=True)
master.save(os.path.join(ROOT, "docs", "icon.png"))
master.scaled(256, 256, Qt.KeepAspectRatio, Qt.SmoothTransformation).save(
    os.path.join(ROOT, "docs", "icon-256.png"))
# also drop a copy next to app.py so the running app can load it for its icon
master.scaled(256, 256, Qt.KeepAspectRatio, Qt.SmoothTransformation).save(
    os.path.join(ROOT, "app_icon.png"))
print("rendered docs/icon.png (1024), docs/icon-256.png, app_icon.png")

# ---- build .ico and .icns from the master via Pillow ----
from PIL import Image
png = os.path.join(ROOT, "docs", "icon.png")
im = Image.open(png).convert("RGBA")
im.save(os.path.join(ROOT, "icon.ico"),
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("wrote icon.ico")
try:
    im.resize((1024, 1024)).save(os.path.join(ROOT, "icon.icns"))
    print("wrote icon.icns")
except Exception as e:
    print("icns skipped:", e)
