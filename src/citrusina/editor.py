"""The tool editor: a glass card with a live preview on the left and the tool's settings on
the right. It's built from the tool's params, so adding a tool needs no code here.
Hold the mouse on the preview to see the original."""
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFontMetrics, QImage, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import (QAbstractButton, QButtonGroup, QGridLayout, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QSlider, QVBoxLayout, QWidget)

from citrusina import convert, formats, glass, tools

MARGIN = 28         # room for the shadow around the card
RADIUS = 24
PREVIEW = QSize(460, 380)
SIDE = 290


def to_qimage(img):
    img = img.convert("RGBA")
    data = img.tobytes("raw", "RGBA")
    return QImage(data, img.width, img.height, 4 * img.width, QImage.Format_RGBA8888).copy()


def _rgba(c):
    return f"rgba({c.red()}, {c.green()}, {c.blue()}, {c.alpha()})"


def qss(dark):
    pal = glass.palette(dark)
    text, muted, well = pal.text.name(), _rgba(pal.muted), _rgba(pal.well)
    hover = "rgba(255, 140, 70, 60)"
    accent = (f"qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {glass.ACCENT_TOP.name()}, "
              f"stop:1 {glass.ACCENT_BOTTOM.name()})")
    return f"""
    QLabel {{ color: {text}; background: transparent; }}
    QLabel#title {{ font-size: 21px; font-weight: 700; }}
    QLabel#file, QLabel#value {{ color: {muted}; font-size: 12px; }}
    QLabel#param {{ font-size: 12px; font-weight: 600; }}
    QSlider {{ min-height: 22px; background: transparent; }}
    QSlider::groove:horizontal {{ height: 6px; border-radius: 3px; background: {well}; }}
    QSlider::sub-page:horizontal {{ height: 6px; border-radius: 3px; background: {accent}; }}
    QSlider::handle:horizontal {{ background: white; border: 1px solid rgba(0, 0, 0, 40);
        width: 18px; height: 18px; margin: -7px 0; border-radius: 10px; }}
    QPushButton {{ font-size: 12px; font-weight: 600; color: {text}; border: none; }}
    QPushButton#chip {{ background: {well}; border-radius: 13px; padding: 6px 8px; }}
    QPushButton#chip:hover {{ background: {hover}; }}
    QPushButton#chip:checked {{ background: {accent}; color: white; }}
    QPushButton#apply {{ background: {accent}; color: white; border-radius: 19px;
        padding: 10px 28px; font-size: 13px; font-weight: 700; }}
    QPushButton#apply:hover {{ background: {glass.ACCENT_BOTTOM.name()}; }}
    QPushButton#ghost {{ background: {well}; border-radius: 19px; padding: 10px 20px; font-size: 13px; }}
    QPushButton#ghost:hover {{ background: {hover}; }}
    QPushButton#close {{ background: {well}; border-radius: 14px; color: {muted};
        font-size: 15px; min-width: 28px; max-width: 28px; min-height: 28px; max-height: 28px; }}
    QPushButton#close:hover {{ background: {glass.ERROR.name()}; color: white; }}
    QLineEdit {{ background: {well}; color: {text}; border: 1px solid transparent;
        border-radius: 10px; padding: 7px 10px; font-size: 13px;
        selection-background-color: {glass.ACCENT_BOTTOM.name()}; }}
    QLineEdit:focus {{ border: 1px solid {glass.ACCENT_BOTTOM.name()}; }}
    """


def _pretty(key, choice):
    if key == "rotate":
        return f"{choice}°"
    if key == "speed":
        return f"{choice}×"
    return choice.title() if choice[:1].isalpha() else choice


# choices that read better as colours than as words
def _swatch_colors(tool, key):
    if tool.key == "add bg" and key == "background":
        return tools.BACKGROUNDS
    if tool.key == "annotate" and key == "color":
        return {k: (v, v) for k, v in tools.TEXT_COLORS.items()}
    return None


class Swatch(QAbstractButton):
    def __init__(self, name, colors):
        super().__init__()
        self.colors = colors
        self.setCheckable(True)
        self.setToolTip(name.title())
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(34, 34)

    def paintEvent(self, _e):
        p = QPainter(self)
        glass.hint(p)
        r = QRectF(self.rect()).adjusted(5, 5, -5, -5)
        g = QLinearGradient(r.topLeft(), r.bottomRight())
        g.setColorAt(0, QColor(*self.colors[0]))
        g.setColorAt(1, QColor(*self.colors[1]))
        p.setBrush(g)
        p.setPen(QPen(QColor(0, 0, 0, 40), 1))
        p.drawEllipse(r)
        if self.isChecked() or self.underMouse():
            p.setBrush(Qt.NoBrush)
            ring = QColor(glass.ACCENT_BOTTOM)
            ring.setAlpha(255 if self.isChecked() else 110)
            p.setPen(QPen(ring, 2.2))
            p.drawEllipse(QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5))

    def enterEvent(self, _e):
        self.update()

    def leaveEvent(self, _e):
        self.update()


class Preview(QWidget):
    def __init__(self, pal):
        super().__init__()
        self.pal = pal
        self.image = None
        self.original = None
        self.holding = False
        self.setFixedSize(PREVIEW)
        self.setToolTip("Hold to compare with the original")

    def paintEvent(self, _e):
        p = QPainter(self)
        glass.hint(p)
        rect = QRectF(self.rect())
        clip = glass.rounded(rect, 16)
        p.fillPath(clip, self.pal.well)
        img = self.original if self.holding else self.image
        if img is None:
            return
        size = img.size().scaled(self.size(), Qt.KeepAspectRatio)
        target = QRectF(QPointF(0, 0), size.toSizeF())
        target.moveCenter(rect.center())
        p.setClipPath(clip)
        # a checkerboard shows where the result is transparent
        tile = 10
        light, dark = QColor(255, 255, 255, 140), QColor(200, 196, 210, 140)
        y = target.top()
        row = 0
        while y < target.bottom():
            x = target.left()
            col = row % 2
            while x < target.right():
                p.fillRect(QRectF(x, y, tile, tile).intersected(target), light if col % 2 else dark)
                x += tile
                col += 1
            y += tile
            row += 1
        p.drawImage(target, img)
        if self.holding:
            p.setClipping(False)
            badge = QRectF(rect.left() + 12, rect.top() + 12, 78, 24)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(0, 0, 0, 120))
            p.drawRoundedRect(badge, 12, 12)
            p.setPen(Qt.white)
            p.drawText(badge, Qt.AlignCenter, "Original")

    def mousePressEvent(self, _e):
        self.holding = True
        self.update()

    def mouseReleaseEvent(self, _e):
        self.holding = False
        self.update()


class Tile(QWidget):
    """Stands in for the preview on video and audio, which we can't preview live."""

    def __init__(self, pal, path):
        super().__init__()
        self.pal = pal
        self.ext = formats.ext_of(path).upper()
        self.setFixedSize(220, PREVIEW.height())

    def paintEvent(self, _e):
        p = QPainter(self)
        glass.hint(p)
        rect = QRectF(self.rect())
        p.fillPath(glass.rounded(rect, 16), self.pal.well)
        f = self.font()
        f.setPixelSize(34)
        f.setBold(True)
        p.setFont(f)
        p.setPen(glass.ACCENT_BOTTOM)
        p.drawText(rect, Qt.AlignCenter, self.ext)


class Editor(QWidget):
    applied = Signal(str, object, dict)     # path, tool, values
    gone = Signal()

    def __init__(self, path, tool, dark):
        super().__init__(None, Qt.Window | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setWindowTitle(f"{tool.label} · citrusina")
        self.setStyleSheet(qss(dark))
        self.path, self.tool = path, tool
        self.pal = glass.palette(dark)
        self.getters, self.setters = {}, {}
        self.thumb = None
        self.debounce = QTimer(self, singleShot=True, interval=40, timeout=self._render)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(MARGIN + 22, MARGIN + 22, MARGIN + 22, MARGIN + 22)
        outer.setSpacing(24)

        if tool.kind == "image":
            self.preview = Preview(self.pal)
            outer.addWidget(self.preview)
            self._load_thumb()
        else:
            self.preview = None
            outer.addWidget(Tile(self.pal, path))

        side = QVBoxLayout()
        side.setSpacing(14)
        holder = QWidget()
        holder.setFixedWidth(SIDE)
        holder.setLayout(side)
        outer.addWidget(holder)

        head = QHBoxLayout()
        title = QLabel(tool.label, objectName="title")
        close = QPushButton("×", objectName="close", cursor=Qt.PointingHandCursor)
        close.clicked.connect(self.close)
        head.addWidget(title)
        head.addStretch()
        head.addWidget(close)
        side.addLayout(head)
        name = QLabel(objectName="file")
        name.setText(QFontMetrics(name.font()).elidedText(Path(path).name, Qt.ElideMiddle, SIDE))
        side.addWidget(name)
        side.addSpacing(6)

        for param in tool.params:
            side.addLayout(self._row(param))
        side.addStretch()

        foot = QHBoxLayout()
        foot.setSpacing(10)
        reset = QPushButton("Reset", objectName="ghost", cursor=Qt.PointingHandCursor)
        reset.clicked.connect(self._reset)
        apply = QPushButton("Save copy", objectName="apply", cursor=Qt.PointingHandCursor)
        apply.clicked.connect(self._apply)
        apply.setDefault(True)
        foot.addWidget(reset)
        foot.addStretch()
        foot.addWidget(apply)
        side.addLayout(foot)
        self._render()

    def _load_thumb(self):
        try:
            img = convert.load_image(self.path).convert("RGBA")
        except Exception:
            return
        # twice the preview size so it stays sharp on hi-dpi screens
        img.thumbnail((PREVIEW.width() * 2, PREVIEW.height() * 2))
        self.thumb = img
        self.preview.original = to_qimage(img)

    def _row(self, param):
        box = QVBoxLayout()
        box.setSpacing(7)
        head = QHBoxLayout()
        head.addWidget(QLabel(param.label, objectName="param"))
        head.addStretch()
        box.addLayout(head)

        if param.kind == "int":
            value = QLabel(str(param.default), objectName="value")
            head.addWidget(value)
            slider = QSlider(Qt.Horizontal, cursor=Qt.PointingHandCursor)
            slider.setRange(param.lo, param.hi)
            slider.setValue(param.default)
            slider.valueChanged.connect(lambda v, lab=value: (lab.setText(str(v)), self._changed()))
            self.getters[param.key] = slider.value
            self.setters[param.key] = slider.setValue
            box.addWidget(slider)
        elif param.kind == "choice":
            colors = _swatch_colors(self.tool, param.key)
            group = QButtonGroup(self)
            grid = QGridLayout()
            grid.setSpacing(6)
            cols = 6 if colors else (4 if len(param.choices) <= 4 else 3)
            buttons = {}
            for i, choice in enumerate(param.choices):
                if colors:
                    b = Swatch(choice, colors[choice])
                else:
                    b = QPushButton(_pretty(param.key, choice), objectName="chip",
                                    cursor=Qt.PointingHandCursor, checkable=True)
                b.setChecked(choice == param.default)
                group.addButton(b)
                buttons[choice] = b
                grid.addWidget(b, i // cols, i % cols)
            group.buttonToggled.connect(lambda *_: self._changed())
            self.getters[param.key] = lambda bs=buttons: next(c for c, b in bs.items() if b.isChecked())
            self.setters[param.key] = lambda v, bs=buttons: bs[v].setChecked(True)
            box.addLayout(grid)
        else:
            entry = QLineEdit(param.default or "")
            entry.textChanged.connect(lambda _t: self._changed())
            entry.returnPressed.connect(self._apply)
            self.getters[param.key] = entry.text
            self.setters[param.key] = lambda v, e=entry: e.setText(v or "")
            box.addWidget(entry)
        return box

    def values(self):
        return {k: get() for k, get in self.getters.items()}

    def _changed(self):
        self.debounce.start()

    def _render(self):
        if self.thumb is None:
            return
        try:
            img = tools.preview(self.tool, self.thumb, self.values())
        except Exception:
            # half-typed values are normal while editing, keep the last good preview
            return
        self.preview.image = to_qimage(img)
        self.preview.update()

    def _reset(self):
        for param in self.tool.params:
            self.setters[param.key](param.default)

    def _apply(self):
        self.applied.emit(self.path, self.tool, self.values())
        self.close()

    def closeEvent(self, e):
        self.gone.emit()
        super().closeEvent(e)

    def paintEvent(self, _e):
        p = QPainter(self)
        glass.hint(p)
        glass.card(p, QRectF(self.rect()).adjusted(MARGIN, MARGIN, -MARGIN, -MARGIN), RADIUS, self.pal)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and self.windowHandle():
            self.windowHandle().startSystemMove()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.close()
        elif e.key() in (Qt.Key_Return, Qt.Key_Enter):
            self._apply()
        else:
            super().keyPressEvent(e)
