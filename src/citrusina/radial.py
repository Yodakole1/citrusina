"""The wheel: a ring of glass petals around the pointer.

It's a transparent window over the whole screen with the wheel painted where the pointer is.
A small window would be nicer, but on Wayland we can't ask where the pointer is, only notice it
when it crosses one of our windows, and a full-screen one is guaranteed to be under it.
That also makes the window a drop target everywhere, which is what dragging a file onto the
wheel needs.
"""
from PySide6.QtCore import QEasingCurve, QPointF, QRectF, Qt, QTimer, QVariantAnimation, Signal
from PySide6.QtGui import (QColor, QCursor, QFont, QGuiApplication, QPainter, QPainterPath,
                           QPainterPathStroker, QPen, QRadialGradient)
from PySide6.QtWidgets import QWidget

from citrusina import formats, glass, wheel
from citrusina.log import log
from citrusina.wheel import CORNER, GAP, HUB, R_HUB, R_IN, R_OUT

RINGS = ("convert", "tools")


def _arc_rect(r):
    return QRectF(-r, -r, 2 * r, 2 * r)


def _sector(r0, r1, a0_in, a1_in, a0_out, a1_out):
    # Qt measures angles counterclockwise from 3 o'clock, ours run clockwise from 12
    path = QPainterPath()
    path.moveTo(*wheel.point(a0_out, r1))
    path.arcTo(_arc_rect(r1), 90 - a0_out, -(a1_out - a0_out))
    path.lineTo(*wheel.point(a1_in, r0))
    path.arcTo(_arc_rect(r0), 90 - a1_in, a1_in - a0_in)
    path.closeSubpath()
    return path


def petal_paths(n):
    if n == 1:
        path = QPainterPath()
        path.setFillRule(Qt.OddEvenFill)
        path.addEllipse(QPointF(0, 0), R_OUT, R_OUT)
        path.addEllipse(QPointF(0, 0), R_IN, R_IN)
        return [path]
    paths = []
    r0, r1 = R_IN + CORNER, R_OUT - CORNER
    # shrink by the corner radius, then grow back with a round stroke: rounded corners for free
    gi, go = wheel.half_gap(r0, GAP + 2 * CORNER), wheel.half_gap(r1, GAP + 2 * CORNER)
    stroker = QPainterPathStroker()
    stroker.setWidth(2 * CORNER)
    stroker.setJoinStyle(Qt.RoundJoin)
    for i in range(n):
        a0, a1 = wheel.span(i, n)
        core = _sector(r0, r1, a0 + gi, a1 - gi, a0 + go, a1 - go)
        paths.append(core.united(stroker.createStroke(core)).simplified())
    return paths


def _mix(a, b, t):
    return QColor(*(round(x + (y - x) * t) for x, y in
                    zip(a.getRgb(), b.getRgb())))


class Radial(QWidget):
    picked = Signal(list, str, str)     # paths, ring, item
    closed = Signal()

    def __init__(self, rings_for):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.setAcceptDrops(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setWindowTitle("citrusina")
        self.rings_for = rings_for
        self.pal = glass.palette(False)
        self.petals = {}
        self.paths = []
        self.rings = {r: [] for r in RINGS}
        self.ring = "convert"
        self.query = ""
        self.shown = []
        self.hover = None
        self.springs = []
        self.hub_spring = 0.0
        self.anchor = None
        self.dragging = False
        self.drag_seen = False
        self.was_active = False
        self.shift_tap = False
        self.closing = False
        self.state = "idle"
        self.status = ""
        self.spin = 0.0
        self.caret = True

        self.pop = self._anim(260)
        self.swap = self._anim(240, QEasingCurve.OutCubic)
        self.fade = self._anim(140, QEasingCurve.InCubic)
        self.fade.finished.connect(self._hidden)

        self.ticker = QTimer(self, interval=16, timeout=self._tick)
        self.blink = QTimer(self, interval=530, timeout=self._blink)
        self.pointer_wait = QTimer(self, singleShot=True, interval=180,
                                   timeout=lambda: self._anchor_at(QCursor.pos()))
        self.no_drag = QTimer(self, singleShot=True, interval=900, timeout=self._drag_check)
        # a drag can brush past the edge of the window and come straight back
        self.left = QTimer(self, singleShot=True, interval=250, timeout=self._drag_gone)

    def _anim(self, ms, curve=QEasingCurve.Linear):
        a = QVariantAnimation(self, duration=ms, startValue=0.0, endValue=1.0)
        a.setEasingCurve(curve)
        a.valueChanged.connect(self.update)
        return a

    # ---- showing and hiding ----

    def popup(self, paths, pos=None, dragging=False, dark=False):
        self.pal = glass.palette(dark)
        self.fade.stop()
        self.closing = False
        self.state = "idle"
        self.dragging = dragging
        self.drag_seen = False
        self.was_active = False
        self._set_paths(paths)

        screen = QGuiApplication.screenAt(pos if pos else QCursor.pos()) or QGuiApplication.primaryScreen()
        self.setGeometry(screen.geometry())
        self.anchor = None
        self.show()
        self.raise_()
        self.activateWindow()
        if pos is not None:
            self._anchor_at(pos)
        else:
            self.pointer_wait.start()
        if dragging:
            self.no_drag.start()

    def close_menu(self):
        if self.closing or not self.isVisible():
            return
        self.closing = True
        self.blink.stop()
        self.fade.setDirection(QVariantAnimation.Forward)
        self.fade.start()

    def _hidden(self):
        self.hide()
        self.ticker.stop()
        self.anchor = None
        self.closed.emit()

    def _anchor_at(self, global_pos):
        if self.anchor is not None:
            return
        self.pointer_wait.stop()
        self.anchor = QPointF(global_pos)
        self.pop.stop()
        self.pop.start()
        self.blink.start()
        self.ticker.start()

    def _drag_check(self):
        # shown for a shift+drag that turned out not to be a file (moving a window, say)
        if self.dragging and not self.drag_seen and self.state == "idle":
            self.close_menu()

    # ---- what's on the wheel ----

    def _set_paths(self, paths):
        self.paths = list(paths)
        self.rings = self.rings_for(self.paths)
        self.ring = "convert" if self.rings["convert"] or not self.rings["tools"] else "tools"
        self._set_query("")

    def _set_query(self, query):
        self.query = query
        self.shown = formats.search(query, self.rings[self.ring])[:wheel.MAX_PETALS]
        self.springs = [0.0] * len(self.shown)
        self.hover = None
        self.update()

    def switch_ring(self):
        other = RINGS[1 - RINGS.index(self.ring)]
        if not self.rings[other] or self.state != "idle":
            return
        self.ring = other
        self._set_query("")
        self.swap.stop()
        self.swap.start()

    def _pick(self, i):
        if self.state == "idle" and 0 <= i < len(self.shown):
            self.picked.emit(self.paths, self.ring, self.shown[i])

    # the app reports back on the job it started from a pick

    def set_busy(self, item, done=0, total=1):
        self.state = "busy"
        self.status = item if total == 1 else f"{done}/{total}"
        self.ticker.start()
        self.update()

    def set_done(self):
        self.state = "done"
        self.update()
        QTimer.singleShot(520, self.close_menu)

    def set_failed(self):
        self.state = "failed"
        self.update()
        QTimer.singleShot(1300, self.close_menu)

    # ---- geometry ----

    def center(self):
        local = self.mapFromGlobal(self.anchor.toPoint()) if self.anchor else self.rect().center()
        x, y = wheel.place(local.x(), local.y(), 0, 0, self.width(), self.height())
        return QPointF(x, y)

    def _hit(self, pos):
        if self.anchor is None:
            return None
        c = self.center()
        return wheel.hit(pos.x() - c.x(), pos.y() - c.y(), len(self.shown))

    def _hover(self, pos):
        h = self._hit(pos)
        if h != self.hover:
            self.hover = h
            self.ticker.start()

    # ---- animation ----

    def _tick(self):
        moving = self.state == "busy"
        for i, s in enumerate(self.springs):
            target = 1.0 if self.hover == i and self.state == "idle" else 0.0
            self.springs[i] = s + (target - s) * 0.32
            moving |= abs(target - self.springs[i]) > 0.003
        target = 1.0 if self.hover == HUB else 0.0
        self.hub_spring += (target - self.hub_spring) * 0.3
        moving |= abs(target - self.hub_spring) > 0.003
        if self.state == "busy":
            self.spin = (self.spin + 7) % 360
        self.update()
        if not moving:
            self.ticker.stop()

    def _blink(self):
        self.caret = not self.caret
        if self.query:
            self.update()

    # ---- painting ----

    def _font(self, size, weight=QFont.Bold, spacing=1.2):
        f = QFont(self.font())
        f.setPixelSize(size)
        f.setWeight(weight)
        f.setLetterSpacing(QFont.AbsoluteSpacing, spacing)
        return f

    def _text(self, p, text, x, y, size, color, weight=QFont.Bold, spacing=1.2):
        p.setFont(self._font(size, weight, spacing))
        p.setPen(color)
        rect = QRectF(x - 120, y - size, 240, 2 * size)
        p.drawText(rect, Qt.AlignCenter, text)

    def paintEvent(self, _event):
        if self.anchor is None:
            return
        p = QPainter(self)
        glass.hint(p)
        fade = 1.0 - self.fade.currentValue() if self.closing else 1.0
        t = self.pop.currentValue() if self.pop.state() == QVariantAnimation.Running else 1.0
        c = self.center()
        p.setOpacity(fade)

        dim = QRadialGradient(c, R_OUT * 2.6)
        dim.setColorAt(0, self.pal.dim)
        dim.setColorAt(1, Qt.transparent)
        p.fillRect(self.rect(), dim)

        back = QEasingCurve(QEasingCurve.OutBack)
        p.translate(c)
        grow = 0.84 + 0.16 * back.valueForProgress(t)
        if self.closing:
            grow *= 0.94 + 0.06 * fade
        p.scale(grow, grow)
        p.setOpacity(fade * min(1.0, t * 2.2))
        glass.ring_shadow(p, QPointF(0, 0), R_IN, R_OUT, self.pal)

        self._paint_petals(p, t, fade, back)
        self._paint_hub(p, fade)

    def _paint_petals(self, p, t, fade, back):
        n = len(self.shown)
        if n == 0:
            return
        if n not in self.petals:
            self.petals[n] = petal_paths(n)
        light = QRectF(-R_OUT, -R_OUT, 2 * R_OUT, 2 * R_OUT)
        swap = self.swap.currentValue() if self.swap.state() == QVariantAnimation.Running else 1.0
        rot = -22 * (1 - swap)
        mid_r = (R_IN + R_OUT) / 2
        for i, item in enumerate(self.shown):
            # petals land one after another going round, which reads as the wheel unfolding
            local = min(1.0, max(0.0, t * 1.5 - 0.5 * i / n))
            appear = back.valueForProgress(local)
            alpha = min(1.0, local * 1.6) * swap
            h = self.springs[i] if i < len(self.springs) else 0.0
            mid = i * wheel.step(n) + rot
            push = wheel.point(mid, 7 * h)
            centroid = QPointF(*wheel.point(mid, mid_r))

            p.save()
            p.translate(*push)
            p.translate(centroid)
            s = (1 + 0.06 * h) * (0.72 + 0.28 * appear)
            p.scale(s, s)
            p.translate(-centroid)
            p.rotate(rot)
            path = self.petals[n][i]
            glass.sheet(p, path, light, self.pal, alpha)
            glass.lit(p, path, light, h * alpha)
            p.restore()

            p.save()
            p.setOpacity(fade * alpha)
            text = item.upper()
            color = _mix(self.pal.text, QColor(255, 255, 255), h)
            self._text(p, text, centroid.x() + push[0], centroid.y() + push[1],
                       wheel.label_size(text, n), color)
            p.restore()

    def _paint_hub(self, p, fade):
        hub = QPainterPath()
        hub.addEllipse(QPointF(0, 0), R_HUB, R_HUB)
        light = QRectF(-R_HUB, -R_HUB, 2 * R_HUB, 2 * R_HUB)
        glass.sheet(p, hub, light, self.pal)
        if self.hub_spring > 0.01 and self.state == "idle":
            ring = QColor(glass.ACCENT_BOTTOM)
            ring.setAlphaF(0.85 * self.hub_spring)
            p.strokePath(hub, QPen(ring, 2.2))

        if self.state == "busy":
            pen = QPen(glass.accent_gradient(light), 3.5)
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            p.drawArc(light.adjusted(6, 6, -6, -6), int(-self.spin * 16), 110 * 16)
        elif self.state == "done":
            self._check(p)
            return

        title, sub = self._hub_text()
        color = glass.ERROR if self.state == "failed" else self.pal.text
        size = 20 if len(title) <= 5 else 15
        self._text(p, title, 0, -6, size, color, spacing=1.6)
        self._text(p, sub.upper(), 0, 15, 9, self.pal.muted, QFont.DemiBold, 1.4)
        if self.state == "idle" and all(self.rings.values()):
            for k, name in enumerate(RINGS):
                dot = QColor(glass.ACCENT_BOTTOM) if name == self.ring else self.pal.muted
                p.setPen(Qt.NoPen)
                p.setBrush(dot)
                p.drawEllipse(QPointF(-5 + 10 * k, 31), 2.6, 2.6)

    def _hub_text(self):
        if self.state == "busy":
            return self.status.upper(), "working"
        if self.state == "failed":
            return "!", "failed"
        if self.query:
            return self.query.upper() + ("|" if self.caret else " "), "no match" if not self.shown else "search"
        if len(self.paths) > 1:
            title = f"{len(self.paths)} files"
        else:
            title = formats.ext_of(self.paths[0]) if self.paths else ""
            title = title or "?"
        if not any(self.rings.values()):
            return title.upper(), "can't convert"
        if self.hover == HUB and all(self.rings.values()):
            other = RINGS[1 - RINGS.index(self.ring)]
            return title.upper(), f"to {other}"
        return title.upper(), self.ring

    def _check(self, p):
        path = QPainterPath()
        path.moveTo(-14, 1)
        path.lineTo(-4, 11)
        path.lineTo(15, -10)
        pen = QPen(glass.ACCENT_BOTTOM, 4.5)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        p.strokePath(path, pen)

    # ---- input ----

    def enterEvent(self, e):
        self._anchor_at(e.globalPosition())
        self._hover(e.position())

    def mouseMoveEvent(self, e):
        self._anchor_at(e.globalPosition())
        self._hover(e.position())

    def leaveEvent(self, _e):
        self.hover = None
        self.ticker.start()

    def mouseReleaseEvent(self, e):
        if self.anchor is None or self.closing:
            return
        if e.button() != Qt.LeftButton:
            self.close_menu()
            return
        h = self._hit(e.position())
        if h is None:
            if self.state != "busy":
                self.close_menu()
        elif h == HUB:
            self.switch_ring()
        else:
            self._pick(h)

    def keyPressEvent(self, e):
        key = e.key()
        self.shift_tap = key == Qt.Key_Shift
        if e.modifiers() & (Qt.ControlModifier | Qt.AltModifier) or self.state != "idle":
            if key == Qt.Key_Escape:
                self.close_menu()
            return
        n = len(self.shown)
        if key == Qt.Key_Escape:
            if self.query:
                self._set_query("")
            else:
                self.close_menu()
        elif key == Qt.Key_Tab:
            self.switch_ring()
        elif key in (Qt.Key_Return, Qt.Key_Enter) and n:
            self._pick(self.hover if isinstance(self.hover, int) else 0)
        elif key in (Qt.Key_Right, Qt.Key_Down, Qt.Key_Left, Qt.Key_Up) and n:
            forward = key in (Qt.Key_Right, Qt.Key_Down)
            i = self.hover if isinstance(self.hover, int) else (-1 if forward else 0)
            self.hover = (i + (1 if forward else -1)) % n
            self.ticker.start()
        elif key == Qt.Key_Backspace:
            self._set_query(self.query[:-1])
        elif e.text() and e.text().isprintable() and e.text().strip():
            self._set_query(self.query + e.text())
            self.caret = True

    def keyReleaseEvent(self, e):
        # a tap of shift on its own flips rings, shift held for a capital letter doesn't
        if e.key() == Qt.Key_Shift and self.shift_tap and not e.isAutoRepeat():
            self.switch_ring()
        self.shift_tap = False

    def changeEvent(self, e):
        if e.type() == e.Type.ActivationChange:
            if self.isActiveWindow():
                self.was_active = True
            elif self.was_active and self.state == "idle" and not self.dragging:
                self.close_menu()
        super().changeEvent(e)

    # ---- drag and drop ----

    @staticmethod
    def _files(e):
        md = e.mimeData()
        if not md.hasUrls():
            return []
        return [u.toLocalFile() for u in md.urls() if u.isLocalFile() and u.toLocalFile()]

    def dragEnterEvent(self, e):
        self.left.stop()
        files = self._files(e)
        if not files:
            log.info("drag with no local files, offered %s", e.mimeData().formats())
            e.ignore()
            return
        self.drag_seen = True
        if files != self.paths:
            self._set_paths(files)
        self._anchor_at(self.mapToGlobal(e.position()))
        # always a copy, so a shift+drag can never move the original away
        e.setDropAction(Qt.CopyAction)
        e.accept()

    def dragMoveEvent(self, e):
        self._hover(e.position())
        e.setDropAction(Qt.CopyAction)
        e.accept()

    def dragLeaveEvent(self, _e):
        self.left.start()

    def _drag_gone(self):
        if self.state == "idle":
            log.info("drag left the wheel, closing")
            self.close_menu()

    def dropEvent(self, e):
        e.setDropAction(Qt.CopyAction)
        e.accept()
        self.dragging = False
        h = self._hit(e.position())
        log.info("dropped %s on %s", self._files(e), self.shown[h] if isinstance(h, int) else h)
        if isinstance(h, int):
            QTimer.singleShot(0, lambda: self._pick(h))
        elif h == HUB:
            # dropped without choosing: stay open and let them click or type
            self.activateWindow()
        else:
            self.close_menu()
