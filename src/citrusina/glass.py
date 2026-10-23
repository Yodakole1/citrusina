"""The glass look, shared by the wheel, the editor, the bubble and the toasts.

There's nothing behind the window we can sample on Wayland, so this isn't real refraction.
It fakes the parts the eye reads as glass: a sheet that's brighter where the light hits,
a thin bright rim on the lit side, a softer one on the far side, and a soft shadow underneath.
The light comes from the top left everywhere so every piece agrees.
"""
from dataclasses import dataclass, replace

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QColor, QLinearGradient, QPainter, QPainterPath, QPainterPathStroker,
                           QPen, QRadialGradient)

ACCENT_TOP = QColor(255, 178, 74)
ACCENT_BOTTOM = QColor(255, 96, 58)
ERROR = QColor(235, 72, 72)


@dataclass
class Palette:
    sheet_lit: QColor
    sheet_dim: QColor
    rim_lit: QColor
    rim_dim: QColor
    sheen: QColor
    shadow: QColor
    dim: QColor
    text: QColor
    muted: QColor
    well: QColor        # sunken things: slider grooves, input fields


def palette(dark):
    if dark:
        return Palette(QColor(70, 68, 84, 196), QColor(30, 28, 38, 178),
                       QColor(255, 255, 255, 120), QColor(255, 255, 255, 26),
                       QColor(255, 255, 255, 34), QColor(0, 0, 0, 120), QColor(0, 0, 0, 70),
                       QColor(250, 248, 255), QColor(250, 248, 255, 150), QColor(0, 0, 0, 60))
    return Palette(QColor(255, 255, 255, 190), QColor(246, 242, 250, 128),
                   QColor(255, 255, 255, 250), QColor(255, 255, 255, 90),
                   QColor(255, 255, 255, 120), QColor(40, 20, 60, 70), QColor(20, 10, 30, 34),
                   QColor(34, 26, 44), QColor(34, 26, 44, 140), QColor(40, 20, 60, 22))


def accent_gradient(rect):
    g = QLinearGradient(rect.topLeft(), rect.bottomRight())
    g.setColorAt(0, ACCENT_TOP)
    g.setColorAt(1, ACCENT_BOTTOM)
    return g


def sheet(p, path, light, pal, alpha=1.0):
    """A pane of glass in the shape of path. light is the rect the lighting is measured across,
    which for the wheel is the whole wheel, so neighbouring petals shade as one piece."""
    p.save()
    p.setOpacity(p.opacity() * alpha)
    g = QLinearGradient(light.topLeft(), light.bottomRight())
    g.setColorAt(0, pal.sheet_lit)
    g.setColorAt(1, pal.sheet_dim)
    p.fillPath(path, g)

    p.setClipPath(path)
    glow = QRadialGradient(QPointF(light.left() + light.width() * 0.28,
                                   light.top() + light.height() * 0.12), light.width() * 0.62)
    glow.setColorAt(0, pal.sheen)
    glow.setColorAt(1, Qt.transparent)
    p.fillRect(light, glow)
    p.setClipping(False)
    rim(p, path, light, pal)
    p.restore()


def rim(p, path, light, pal, width=1.2):
    g = QLinearGradient(light.topLeft(), light.bottomRight())
    g.setColorAt(0, pal.rim_lit)
    g.setColorAt(0.5, pal.rim_dim)
    # glass catches a second, weaker reflection on the far edge
    g.setColorAt(1, QColor(pal.rim_lit.red(), pal.rim_lit.green(), pal.rim_lit.blue(),
                           pal.rim_lit.alpha() // 2))
    p.strokePath(path, QPen(g, width))


def lit(p, path, light, amount=1.0):
    """The accent fill for whatever is under the pointer, with a glow around it."""
    if amount <= 0:
        return
    p.save()
    p.setOpacity(p.opacity() * amount)
    for width, a in ((22, 14), (12, 26), (5, 46)):
        glow = QColor(ACCENT_BOTTOM)
        glow.setAlpha(a)
        stroker = QPainterPathStroker()
        stroker.setWidth(width)
        stroker.setJoinStyle(Qt.RoundJoin)
        p.fillPath(stroker.createStroke(path), glow)
    p.fillPath(path, accent_gradient(path.boundingRect()))
    p.setClipPath(path)
    shine = QLinearGradient(light.topLeft(), light.center())
    shine.setColorAt(0, QColor(255, 255, 255, 90))
    shine.setColorAt(1, QColor(255, 255, 255, 0))
    p.fillRect(path.boundingRect(), shine)
    p.setClipping(False)
    p.strokePath(path, QPen(QColor(255, 255, 255, 170), 1.2))
    p.restore()


def ring_shadow(p, center, r_in, r_out, pal, drop=10):
    r = r_out + 30
    g = QRadialGradient(QPointF(center.x(), center.y() + drop), r)
    clear = QColor(pal.shadow)
    clear.setAlpha(0)
    g.setColorAt(max(0.0, (r_in - 12) / r), clear)
    g.setColorAt((r_out - 14) / r, pal.shadow)
    g.setColorAt(1, clear)
    p.setPen(Qt.NoPen)
    p.setBrush(g)
    p.drawEllipse(QPointF(center.x(), center.y() + drop), r, r)


def box_shadow(p, rect, radius, pal, spread=22, drop=10):
    """A soft shadow under a rounded rect, built from stacked faint layers."""
    p.save()
    p.setPen(Qt.NoPen)
    steps = 11
    for i in range(steps):
        grow = spread * (1 - i / steps)
        c = QColor(pal.shadow)
        c.setAlpha(max(1, pal.shadow.alpha() // steps))
        p.setBrush(c)
        r = rect.adjusted(-grow, -grow + drop, grow, grow + drop)
        p.drawRoundedRect(r, radius + grow, radius + grow)
    p.restore()


def card(p, rect, radius, pal):
    """A window-sized pane. More opaque than the wheel: it's read for longer, and text
    needs a calm backing."""
    box_shadow(p, rect, radius, pal)
    lit, dim = QColor(pal.sheet_lit), QColor(pal.sheet_dim)
    lit.setAlpha(min(255, lit.alpha() + 40))
    dim.setAlpha(min(255, dim.alpha() + 60))
    sheet(p, rounded(rect, radius), rect, replace(pal, sheet_lit=lit, sheet_dim=dim))


def rounded(rect, radius):
    path = QPainterPath()
    path.addRoundedRect(QRectF(rect), radius, radius)
    return path


def hint(p):
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.TextAntialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform)


def menu_qss(dark):
    pal = palette(dark)
    bg = "rgba(36, 34, 46, 235)" if dark else "rgba(252, 250, 255, 240)"
    line = "rgba(255,255,255,30)" if dark else "rgba(40,20,60,25)"
    return f"""
    QMenu {{ background: {bg}; border: 1px solid {line}; border-radius: 12px; padding: 6px; }}
    QMenu::item {{ color: {pal.text.name()}; padding: 7px 22px 7px 14px; border-radius: 8px; }}
    QMenu::item:selected {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 {ACCENT_TOP.name()}, stop:1 {ACCENT_BOTTOM.name()}); color: white; }}
    QMenu::item:disabled {{ color: {pal.muted.name(QColor.HexArgb)}; }}
    QMenu::separator {{ height: 1px; background: {line}; margin: 5px 8px; }}
    """
