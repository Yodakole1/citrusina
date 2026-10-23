"""The settings window: what each ring shows and in what order, per kind of file, plus the
general switches. Changes save as they happen, there's no Apply."""
from pathlib import Path

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QIcon, QPainter
from PySide6.QtWidgets import (QAbstractItemView, QButtonGroup, QHBoxLayout, QLabel, QListWidget,
                               QListWidgetItem, QPushButton, QStackedWidget, QVBoxLayout, QWidget)

from citrusina import editor, formats, glass, platform_linux, settings, tools, wheel

MARGIN = editor.MARGIN
RADIUS = editor.RADIUS
ASSETS = Path(__file__).parent / "assets"

KIND_NAMES = {"image": "Images", "video": "Video", "audio": "Audio", "text": "Text",
              "document": "Documents", "subtitle": "Subtitles", "archive": "Archives"}
TOOL_NAMES = {t.label.lower(): t.label for ts in tools.TOOLS.values() for t in ts}


def items_for(ring, kind):
    if ring == "convert":
        return list(formats.KINDS[kind]["out"])
    return [t.label.lower() for t in tools.TOOLS.get(kind, [])]


def qss(dark):
    pal = glass.palette(dark)
    text, well, muted = pal.text.name(), editor._rgba(pal.well), editor._rgba(pal.muted)
    return editor.qss(dark) + f"""
    QLabel#hint {{ color: {muted}; font-size: 12px; }}
    QListWidget {{ background: transparent; border: none; outline: none; }}
    QListWidget::item {{ color: {text}; background: {well}; border-radius: 10px; margin: 3px 2px;
        padding: 9px 10px; font-size: 13px; font-weight: 600; }}
    QListWidget::item:hover {{ background: rgba(255, 140, 70, 45); }}
    QListWidget::item:selected {{ background: rgba(255, 140, 70, 70); color: {text}; }}
    QListWidget::indicator {{ width: 18px; height: 18px; border-radius: 6px;
        border: 1.5px solid rgba(128, 120, 140, 150); background: transparent; }}
    QListWidget::indicator:checked {{ border: none; image: url({ASSETS / 'check.svg'});
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {glass.ACCENT_TOP.name()},
        stop:1 {glass.ACCENT_BOTTOM.name()}); }}
    QPushButton#side {{ text-align: left; padding: 9px 14px; border-radius: 12px; font-size: 13px;
        background: transparent; }}
    QPushButton#side:hover {{ background: {well}; }}
    QPushButton#side:checked {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 {glass.ACCENT_TOP.name()}, stop:1 {glass.ACCENT_BOTTOM.name()}); color: white; }}
    """


class RingList(QListWidget):
    """Tick what shows, drag to reorder."""
    changed = Signal()

    def __init__(self):
        super().__init__()
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setCursor(Qt.OpenHandCursor)
        self.loading = False
        self.itemChanged.connect(lambda _i: None if self.loading else self.changed.emit())
        self.model().rowsMoved.connect(lambda *_: self.changed.emit())

    def fill(self, rows, label):
        self.loading = True
        self.clear()
        for item, shown in rows:
            it = QListWidgetItem(QIcon(str(ASSETS / "grip.svg")), label(item))
            it.setData(Qt.UserRole, item)
            it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsUserCheckable
                        | Qt.ItemIsDragEnabled)
            it.setCheckState(Qt.Checked if shown else Qt.Unchecked)
            it.setSizeHint(QSize(0, 40))
            self.addItem(it)
        self.loading = False

    def state(self):
        order, hidden = [], []
        for i in range(self.count()):
            it = self.item(i)
            order.append(it.data(Qt.UserRole))
            if it.checkState() != Qt.Checked:
                hidden.append(it.data(Qt.UserRole))
        return order, hidden


class RingPage(QWidget):
    """Kinds of file down the side, that kind's formats or tools on the right."""

    def __init__(self, prefs, ring, kinds):
        super().__init__()
        self.prefs, self.ring = prefs, ring
        self.kind = kinds[0]
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(18)

        side = QVBoxLayout()
        side.setSpacing(4)
        group = QButtonGroup(self)
        for kind in kinds:
            b = QPushButton(KIND_NAMES[kind], objectName="side", checkable=True,
                            cursor=Qt.PointingHandCursor)
            b.setChecked(kind == self.kind)
            b.clicked.connect(lambda _c=False, k=kind: self.show_kind(k))
            group.addButton(b)
            side.addWidget(b)
        side.addStretch()
        holder = QWidget()
        holder.setFixedWidth(150)
        holder.setLayout(side)
        row.addWidget(holder)

        right = QVBoxLayout()
        right.setSpacing(8)
        self.hint = QLabel(objectName="hint")
        self.hint.setWordWrap(True)
        right.addWidget(self.hint)
        self.list = RingList()
        self.list.changed.connect(self.save)
        right.addWidget(self.list, 1)
        foot = QHBoxLayout()
        foot.addStretch()
        reset = QPushButton("Reset this list", objectName="ghost", cursor=Qt.PointingHandCursor)
        reset.clicked.connect(self.reset)
        foot.addWidget(reset)
        right.addLayout(foot)
        row.addLayout(right, 1)
        self.show_kind(self.kind)

    def label(self, item):
        return item.upper() if self.ring == "convert" else TOOL_NAMES.get(item, item.title())

    def show_kind(self, kind):
        self.kind = kind
        what = "formats" if self.ring == "convert" else "tools"
        self.hint.setText(f"Tick the {what} {KIND_NAMES[kind].lower()} should offer and drag them "
                          f"into order. The first {wheel.MAX_PETALS} fit on the wheel, "
                          "type on the wheel to find the rest.")
        self.list.fill(settings.layout(self.prefs, self.ring, kind, items_for(self.ring, kind)),
                       self.label)

    def save(self):
        order, hidden = self.list.state()
        settings.remember(self.prefs, self.ring, self.kind, order, hidden)
        settings.save(self.prefs)

    def reset(self):
        settings.forget(self.prefs, self.ring, self.kind)
        settings.save(self.prefs)
        self.show_kind(self.kind)


class Switch(QPushButton):
    def __init__(self, on, toggled):
        super().__init__(objectName="side", checkable=True, cursor=Qt.PointingHandCursor)
        self.setFixedWidth(90)
        self.setChecked(on)
        self.setText("On" if on else "Off")
        self.toggled.connect(lambda v: self.setText("On" if v else "Off"))
        self.toggled.connect(toggled)


class GeneralPage(QWidget):
    def __init__(self, app):
        super().__init__()
        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(10)
        col.addWidget(QLabel("Show the drop tab on the screen edge", objectName="param"))
        col.addWidget(Switch(app.prefs["bubble"], app._toggle_bubble))
        col.addWidget(QLabel("Start citrusina when you log in", objectName="param"))
        col.addWidget(Switch(platform_linux.autostart_file().exists(), platform_linux.set_autostart))
        if platform_linux.global_input():
            col.addWidget(QLabel("Key to hold while dragging a file", objectName="param"))
            keys = QHBoxLayout()
            group = QButtonGroup(self)
            for key in settings.TRIGGERS:
                b = QPushButton(key.title(), objectName="chip", checkable=True,
                                cursor=Qt.PointingHandCursor)
                b.setChecked(key == app.prefs["trigger"])
                b.clicked.connect(lambda _c=False, k=key: app._set_trigger(k))
                group.addButton(b)
                keys.addWidget(b)
            col.addLayout(keys)
        else:
            col.addWidget(QLabel("Shift+drag needs an X11 session. On Wayland, drag files onto the "
                                 "tab instead.", objectName="hint", wordWrap=True))
        col.addStretch()


class Preferences(QWidget):
    gone = Signal()

    def __init__(self, app, dark):
        super().__init__(None, Qt.Window | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setWindowTitle("citrusina settings")
        self.setStyleSheet(qss(dark))
        self.pal = glass.palette(dark)
        self.resize(820 + 2 * MARGIN, 600 + 2 * MARGIN)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(MARGIN + 24, MARGIN + 20, MARGIN + 24, MARGIN + 22)
        outer.setSpacing(16)

        head = QHBoxLayout()
        head.addWidget(QLabel("Settings", objectName="title"))
        head.addSpacing(18)
        pages = QStackedWidget()
        tabs = QButtonGroup(self)
        names = ("Formats", "Tools", "General")
        for i, name in enumerate(names):
            b = QPushButton(name, objectName="chip", checkable=True, cursor=Qt.PointingHandCursor)
            b.setMinimumWidth(84)
            b.setChecked(i == 0)
            b.clicked.connect(lambda _c=False, n=i: pages.setCurrentIndex(n))
            tabs.addButton(b)
            head.addWidget(b)
        head.addStretch()
        close = QPushButton("×", objectName="close", cursor=Qt.PointingHandCursor)
        close.clicked.connect(self.close)
        head.addWidget(close)
        outer.addLayout(head)

        pages.addWidget(RingPage(app.prefs, "convert", list(formats.KINDS)))
        pages.addWidget(RingPage(app.prefs, "tools", list(tools.TOOLS)))
        pages.addWidget(GeneralPage(app))
        outer.addWidget(pages, 1)

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

    def closeEvent(self, e):
        self.gone.emit()
        super().closeEvent(e)
