"""The little glass note that says a file was saved. Click it to see the file in Files."""
from PySide6.QtCore import QEasingCurve, QPoint, QPointF, QPropertyAnimation, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QCursor, QFont, QFontMetrics, QGuiApplication, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from citrusina import glass

MARGIN = 24     # room for the shadow
HEIGHT = 56
GAP = 10


class Toast(QWidget):
    clicked = Signal()
    gone = Signal()

    def __init__(self, title, detail, ok, dark):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
                         | Qt.WindowDoesNotAcceptFocus | Qt.X11BypassWindowManagerHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.title, self.detail, self.ok = title, detail, ok
        self.pal = glass.palette(dark)
        self.hovered = False
        self.title_font = self._font(13, QFont.Bold)
        self.detail_font = self._font(12, QFont.Normal)
        text_w = max(QFontMetrics(self.title_font).horizontalAdvance(title),
                     QFontMetrics(self.detail_font).horizontalAdvance(detail))
        self.setFixedSize(min(460, text_w + 78) + 2 * MARGIN, HEIGHT + 2 * MARGIN)

        self.anim = QPropertyAnimation(self, b"windowOpacity", self, duration=180)
        self.anim.setEasingCurve(QEasingCurve.OutCubic)
        self.life = QTimer(self, singleShot=True, interval=4200 if ok else 6500,
                           timeout=self.dismiss)

    def _font(self, size, weight):
        f = QFont(self.font())
        f.setPixelSize(size)
        f.setWeight(weight)
        return f

    def appear(self, pos):
        self.move(pos)
        self.setWindowOpacity(0.0)
        self.show()
        self.anim.setStartValue(0.0)
        self.anim.setEndValue(1.0)
        self.anim.start()
        self.life.start()

    def dismiss(self):
        self.life.stop()
        self.anim.stop()
        self.anim.setStartValue(self.windowOpacity())
        self.anim.setEndValue(0.0)
        self.anim.finished.connect(self._done)
        self.anim.start()

    def _done(self):
        self.hide()
        self.gone.emit()
        self.deleteLater()

    def paintEvent(self, _e):
        p = QPainter(self)
        glass.hint(p)
        card = QRectF(MARGIN, MARGIN, self.width() - 2 * MARGIN, HEIGHT)
        glass.box_shadow(p, card, HEIGHT / 2, self.pal, spread=16, drop=6)
        glass.sheet(p, glass.rounded(card, HEIGHT / 2), card, self.pal)

        dot = QRectF(card.left() + 12, card.top() + 12, HEIGHT - 24, HEIGHT - 24)
        p.setPen(Qt.NoPen)
        p.setBrush(glass.accent_gradient(dot) if self.ok else glass.ERROR)
        p.drawEllipse(dot)
        mark = QPainterPath()
        c = dot.center()
        if self.ok:
            mark.moveTo(c + QPointF(-7, 0))
            mark.lineTo(c + QPointF(-2, 5))
            mark.lineTo(c + QPointF(7, -5))
        else:
            mark.moveTo(c + QPointF(-5, -5))
            mark.lineTo(c + QPointF(5, 5))
            mark.moveTo(c + QPointF(5, -5))
            mark.lineTo(c + QPointF(-5, 5))
        pen = QPen(Qt.white, 2.6)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        p.strokePath(mark, pen)

        x = dot.right() + 12
        w = card.right() - x - 18
        p.setPen(self.pal.text)
        p.setFont(self.title_font)
        p.drawText(QRectF(x, card.top() + 9, w, 20), Qt.AlignLeft | Qt.AlignVCenter,
                   QFontMetrics(self.title_font).elidedText(self.title, Qt.ElideMiddle, int(w)))
        p.setPen(self.pal.muted)
        p.setFont(self.detail_font)
        p.drawText(QRectF(x, card.top() + 28, w, 18), Qt.AlignLeft | Qt.AlignVCenter,
                   QFontMetrics(self.detail_font).elidedText(self.detail, Qt.ElideMiddle, int(w)))

    def enterEvent(self, _e):
        self.life.stop()

    def leaveEvent(self, _e):
        self.life.start(2000)

    def mouseReleaseEvent(self, _e):
        self.clicked.emit()
        self.dismiss()


class Toasts:
    """Stacks toasts upward from the bottom of the screen the pointer is on."""

    def __init__(self):
        self.live = []

    def show(self, title, detail, ok=True, dark=False, on_click=None):
        t = Toast(title, detail, ok, dark)
        if on_click:
            t.clicked.connect(on_click)
        t.gone.connect(lambda: self._gone(t))
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        area = screen.availableGeometry()
        y = area.bottom() - t.height() + MARGIN - 40 - sum(x.height() - 2 * MARGIN + GAP for x in self.live)
        t.appear(QPoint(area.center().x() - t.width() // 2, y))
        self.live.append(t)
        return t

    def _gone(self, t):
        if t in self.live:
            self.live.remove(t)

    def busy(self):
        return bool(self.live)
