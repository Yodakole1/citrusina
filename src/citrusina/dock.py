"""The drop tab: a slim sliver of glass on the screen edge. Drag a file onto it and the wheel
unfolds under the pointer, keep dragging onto a petal and let go. It's the Wayland stand-in
for Shift+drag, since a drop target is something Wayland does let us have.

At rest it's barely there. It slides out when the pointer or a file reaches it.
"""
import math

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from citrusina import glass
from citrusina.log import log

REST = (12, 84)         # width, height of the tab when idle
OPEN = (54, 116)
SHADOW = 16             # room for the shadow on the inner side


def paint_glyph(p, c, r, color):
    """Two arrows chasing each other round a circle: this turns into that."""
    pen = QPen(color, 2.4)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    box = QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r)
    for start in (20, 200):
        p.drawArc(box, start * 16, 130 * 16)
        # the arrowhead sits at the end of the arc, pointing along it
        a = math.radians(start + 130)
        tip = QPointF(c.x() + r * math.cos(a), c.y() - r * math.sin(a))
        along = QPointF(-math.sin(a), -math.cos(a))         # direction of travel
        out = QPointF(math.cos(a), -math.sin(a))
        head = QPainterPath()
        head.moveTo(tip - along * 5 + out * 3.5)
        head.lineTo(tip)
        head.lineTo(tip - along * 5 - out * 3.5)
        p.drawPath(head)


class Bubble(QWidget):
    entered = Signal(list, QPoint)     # files dragged onto it, and where the pointer is
    dropped = Signal(list, QPoint)
    moved = Signal(QPoint)
    menu = Signal(QPoint)

    def __init__(self, dark, pos=None):
        # bypassing the window manager keeps it off the dock and out of Alt+Tab
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
                         | Qt.WindowDoesNotAcceptFocus | Qt.X11BypassWindowManagerHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAcceptDrops(True)
        self.setToolTip("Drag a file here to convert it · right-click for settings")
        self.pal = glass.palette(dark)
        self.open = 0.0
        self.target = 0.0
        self.press = None
        self.dragged = False
        self.timer = QTimer(self, interval=16, timeout=self._tick)

        area = QGuiApplication.primaryScreen().availableGeometry()
        self.right = True
        self.y_mid = area.center().y()
        if pos is not None:
            self.right = pos.x() > area.center().x()
            self.y_mid = pos.y()
        self._fit()

    def set_dark(self, dark):
        self.pal = glass.palette(dark)
        self.update()

    def _screen_area(self):
        return QGuiApplication.primaryScreen().availableGeometry()

    def _size(self):
        t = self.open
        return REST[0] + (OPEN[0] - REST[0]) * t, REST[1] + (OPEN[1] - REST[1]) * t

    def _fit(self):
        # the window is only as big as the tab, so the empty edge stays clickable
        area = self._screen_area()
        h = OPEN[1] + 2 * SHADOW
        tw, _ = self._size()
        width = int(tw + SHADOW)
        y = int(min(max(self.y_mid - h / 2, area.top()), area.bottom() - h))
        x = area.right() + 1 - width if self.right else area.left()
        self.setGeometry(x, y, width, h)

    def _heat(self, target):
        self.target = target
        self.timer.start()

    def _tick(self):
        self.open += (self.target - self.open) * 0.28
        if abs(self.target - self.open) < 0.005:
            self.open = self.target
            self.timer.stop()
        self._fit()
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        glass.hint(p)
        tw, th = self._size()
        x = SHADOW if self.right else 0
        tab = QRectF(x, (self.height() - th) / 2, tw, th)
        # rounded on the inner side, flush with the screen edge on the other
        radius = min(16.0, tw / 2 + 2)
        bleed = radius + 2
        shape = QRectF(tab.adjusted(0, 0, bleed, 0) if self.right else tab.adjusted(-bleed, 0, 0, 0))
        path = glass.rounded(shape, radius)
        clip = QPainterPath()
        clip.addRect(tab)
        path = path.intersected(clip)

        glass.box_shadow(p, tab, radius, self.pal, spread=SHADOW * 0.7, drop=3)
        glass.sheet(p, path, tab, self.pal)

        # the accent stripe: a hint at rest, and it fades into the glyph as the tab opens
        stripe_h = 30 * (1 - self.open) + 6
        stripe = QRectF(tab.center().x() - 1.75, tab.center().y() - stripe_h / 2, 3.5, stripe_h)
        p.setOpacity(1 - self.open)
        p.setPen(Qt.NoPen)
        p.setBrush(glass.accent_gradient(stripe))
        p.drawRoundedRect(stripe, 1.75, 1.75)
        if self.open > 0.05:
            p.setOpacity(min(1.0, self.open * 1.4))
            color = QColor(glass.ACCENT_BOTTOM) if self.target > 0.9 else self.pal.text
            paint_glyph(p, tab.center(), 11 * (0.7 + 0.3 * self.open), color)

    def enterEvent(self, _e):
        self._heat(0.75)

    def leaveEvent(self, _e):
        if self.press is None:
            self._heat(0.0)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.press = e.globalPosition().toPoint()
            self.dragged = False
        elif e.button() == Qt.RightButton:
            self.menu.emit(e.globalPosition().toPoint())

    def mouseMoveEvent(self, e):
        if self.press is None:
            return
        g = e.globalPosition().toPoint()
        if not self.dragged and (g - self.press).manhattanLength() < 6:
            return
        # slides along the edge, and jumps to the other side past the middle of the screen
        self.dragged = True
        self.y_mid = g.y()
        self.right = g.x() > self._screen_area().center().x()
        self._fit()
        self.update()

    def mouseReleaseEvent(self, e):
        if self.press is not None and self.dragged:
            area = self._screen_area()
            self.moved.emit(QPoint(area.right() if self.right else area.left(), int(self.y_mid)))
        elif e.button() == Qt.LeftButton:
            self.menu.emit(e.globalPosition().toPoint())
        self.press = None
        if not self.underMouse():
            self._heat(0.0)

    def dragEnterEvent(self, e):
        files = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if not files:
            log.info("drag on the tab with no local files, offered %s", e.mimeData().formats())
            e.ignore()
            return
        e.setDropAction(Qt.CopyAction)
        e.accept()
        self._heat(1.0)
        self.entered.emit(files, self.mapToGlobal(e.position()).toPoint())

    def dragLeaveEvent(self, _e):
        self._heat(0.0)

    def dropEvent(self, e):
        # the wheel normally covers us before the drop, but if it didn't, open it here
        files = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        e.setDropAction(Qt.CopyAction)
        e.accept()
        self._heat(0.0)
        if files:
            self.dropped.emit(files, self.mapToGlobal(e.position()).toPoint())
