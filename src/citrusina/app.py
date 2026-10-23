"""Ties the pieces together: the wheel, the drop tab, Shift+drag, the editor and toasts.

It runs in one of two ways. `citrusina --background` stays resident with the tab and a tray
icon. `citrusina FILE` from the Files menu opens the wheel, and exits once it's done, unless a
resident one is already running, in which case handoff gives it the files instead.
"""
import os
import sys
import threading
from pathlib import Path

from citrusina import __version__, platform_linux
from citrusina.log import log

platform_linux.use_xwayland()

from PySide6.QtCore import QObject, QPoint, Qt, QtMsgType, Signal, qInstallMessageHandler  # noqa: E402
from PySide6.QtGui import QAction, QActionGroup, QCursor, QIcon  # noqa: E402
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon  # noqa: E402

from citrusina import convert, formats, glass, handoff, settings, tools  # noqa: E402
from citrusina import log as logfile  # noqa: E402
from citrusina.dock import Bubble  # noqa: E402
from citrusina.editor import Editor  # noqa: E402
from citrusina.radial import Radial  # noqa: E402
from citrusina.toasts import Toasts  # noqa: E402

ICON = Path(__file__).parent / "assets" / "citrusina.svg"


def rings_for(paths, prefs=None):
    """What the wheel offers, in the order chosen in settings. Several files share the formats
    they all convert to; tools take one."""
    if not paths:
        return {"convert": [], "tools": []}
    targets = convert.targets_for(paths[0])
    for p in paths[1:]:
        others = set(convert.targets_for(p))
        targets = [t for t in targets if t in others]
    found = [t.label.lower() for t in tools.tools_for(paths[0])] if len(paths) == 1 else []
    if prefs:
        kind = formats.kind_of(paths[0])
        targets = settings.arrange(prefs, "convert", kind, targets)
        found = settings.arrange(prefs, "tools", kind, found)
    return {"convert": targets, "tools": found}


class Job(QObject):
    progress = Signal(int, int)
    finished = Signal(list)
    failed = Signal(str)

    def __init__(self, steps):
        super().__init__()
        self.steps = steps

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        made = []
        for i, step in enumerate(self.steps):
            self.progress.emit(i, len(self.steps))
            try:
                made.append(step())
            except convert.ConvertError as e:
                self.failed.emit(str(e))
                return
            except Exception as e:
                log.exception("job crashed")
                self.failed.emit(str(e) or type(e).__name__)
                return
        self.finished.emit(made)


class Citrusina(QObject):
    def __init__(self, qapp, resident):
        super().__init__()
        self.qapp = qapp
        self.resident = resident
        self.prefs = settings.load()
        self.dark = platform_linux.dark_mode()
        self.jobs = set()
        self.editors = set()
        self.toasts = Toasts()

        self.radial = Radial(lambda paths: rings_for(paths, self.prefs))
        self.radial.picked.connect(self.picked)
        self.radial.closed.connect(self._wheel_closed)

        self.server = handoff.Server(self)
        self.server.received.connect(self._handed)
        self.server.action.connect(lambda a: self.show_settings() if a == "settings" else None)
        self.prefs_window = None

        self.bubble = None
        self.tray = None
        self.trigger = None
        if resident:
            self._resident_bits()

    # ---- resident mode ----

    def _resident_bits(self):
        if self.prefs["bubble"]:
            self._show_bubble()
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QSystemTrayIcon(QIcon(str(ICON)), self)
            self.tray.setToolTip("citrusina")
            self.tray.setContextMenu(self.menu())
            self.tray.show()
        if platform_linux.global_input():
            self._start_trigger()

    def _start_trigger(self):
        from citrusina.trigger import Trigger
        try:
            self.trigger = Trigger(self.prefs["trigger"], self)
        except OSError as e:
            log.warning("no Shift+drag: %s", e)
            return
        self.trigger.fired.connect(lambda pos: self.open([], pos, dragging=True))

    def _show_bubble(self):
        pos = self.prefs["bubble_pos"]
        self.bubble = Bubble(self.dark, QPoint(*pos) if pos else None)
        self.bubble.entered.connect(lambda files, pos: self.open(files, pos, dragging=True))
        self.bubble.dropped.connect(lambda files, pos: self.open(files, pos))
        self.bubble.moved.connect(self._bubble_moved)
        self.bubble.menu.connect(lambda pos: self.menu().exec(pos))
        self.bubble.show()

    def _bubble_moved(self, pos):
        self.prefs["bubble_pos"] = [pos.x(), pos.y()]
        settings.save(self.prefs)

    def menu(self):
        m = self._glass_menu(QMenu())
        title = m.addAction("citrusina")
        title.setEnabled(False)
        m.addSeparator()
        m.addAction("Settings…").triggered.connect(self.show_settings)

        bubble = m.addAction("Show drop tab")
        bubble.setCheckable(True)
        bubble.setChecked(self.prefs["bubble"])
        bubble.toggled.connect(self._toggle_bubble)

        login = m.addAction("Start at login")
        login.setCheckable(True)
        login.setChecked(platform_linux.autostart_file().exists())
        login.toggled.connect(platform_linux.set_autostart)

        if platform_linux.global_input():
            keys = self._glass_menu(m.addMenu("Drag trigger key"))
            group = QActionGroup(keys)
            for key in settings.TRIGGERS:
                a = QAction(key.title(), keys, checkable=True, checked=key == self.prefs["trigger"])
                a.triggered.connect(lambda _c=False, k=key: self._set_trigger(k))
                group.addAction(a)
                keys.addAction(a)

        m.addAction("Open log").triggered.connect(
            lambda: os.spawnlp(os.P_NOWAIT, "xdg-open", "xdg-open", str(logfile.path())))
        m.addSeparator()
        m.addAction("Quit").triggered.connect(self.qapp.quit)
        # keep a reference, the tray only borrows it
        self._menu = m
        return m

    def show_settings(self):
        from citrusina.preferences import Preferences
        if self.prefs_window is None:
            self.dark = platform_linux.dark_mode()
            self.prefs_window = Preferences(self, self.dark)
            self.prefs_window.gone.connect(self._settings_closed)
            screen = self.qapp.screenAt(QCursor.pos()) or self.qapp.primaryScreen()
            self.prefs_window.move(screen.availableGeometry().center() - self.prefs_window.rect().center())
        self.prefs_window.show()
        self.prefs_window.raise_()
        self.prefs_window.activateWindow()

    def _settings_closed(self):
        self.prefs_window = None
        self.maybe_quit()

    def _glass_menu(self, m):
        # rounded corners need a see-through window behind them
        m.setWindowFlags(m.windowFlags() | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        m.setAttribute(Qt.WA_TranslucentBackground)
        m.setStyleSheet(glass.menu_qss(self.dark))
        return m

    def _toggle_bubble(self, on):
        self.prefs["bubble"] = on
        settings.save(self.prefs)
        if on and self.bubble is None:
            self._show_bubble()
        elif not on and self.bubble is not None:
            self.bubble.close()
            self.bubble = None

    def _set_trigger(self, key):
        self.prefs["trigger"] = key
        settings.save(self.prefs)
        if self.trigger:
            self.trigger.key = key

    # ---- the wheel ----

    def _handed(self, files):
        log.info("handed %s", files)
        self.open(files)

    def open(self, files, pos=None, dragging=False):
        missing = [f for f in files if not Path(f).is_file()]
        if missing:
            log.warning("not files, skipped: %s", missing)
        files = [f for f in files if Path(f).is_file()]
        if not files and not dragging:
            return
        log.info("wheel for %s at %s%s, offers %s", files, pos and (pos.x(), pos.y()),
                 " (dragging)" if dragging else "", rings_for(files, self.prefs))
        self.dark = platform_linux.dark_mode()
        if self.bubble:
            self.bubble.set_dark(self.dark)
            # the tab sits above the wheel, so the drag would keep landing back on it
            self.bubble.hide()
        self.radial.popup(files, pos, dragging, self.dark)

    def _wheel_closed(self):
        if self.bubble:
            self.bubble.show()
        self.maybe_quit()

    def picked(self, paths, ring, item):
        log.info("picked %s %s for %s", ring, item, paths)
        if ring == "tools":
            tool = next(t for t in tools.tools_for(paths[0]) if t.label.lower() == item)
            if tool.params:
                self.radial.close_menu()
                self.edit(paths[0], tool)
                return
            steps = [lambda: tools.run(tool, paths[0])]
        else:
            steps = [lambda p=p: convert.convert(p, item) for p in paths]
        self.radial.set_busy(item, 0, len(steps))
        job = self.run(steps)
        job.progress.connect(lambda done, total: self.radial.set_busy(item, done, total))
        job.finished.connect(lambda _made: self.radial.set_done())
        job.failed.connect(lambda _msg: self.radial.set_failed())

    def edit(self, path, tool):
        ed = Editor(path, tool, self.dark)
        ed.applied.connect(lambda p, t, values: (log.info("%s on %s with %s", t.key, p, values),
                                                 self.run([lambda: tools.run(t, p, values)])))
        ed.gone.connect(lambda: (self.editors.discard(ed), self.maybe_quit()))
        self.editors.add(ed)
        ed.adjustSize()
        screen = self.qapp.screenAt(QCursor.pos()) or self.qapp.primaryScreen()
        ed.move(screen.availableGeometry().center() - ed.rect().center())
        ed.show()
        ed.activateWindow()

    def run(self, steps):
        job = Job(steps)
        self.jobs.add(job)
        job.finished.connect(lambda made: self._finished(job, made))
        job.failed.connect(lambda msg: self._failed(job, msg))
        job.start()
        return job

    def _finished(self, job, made):
        self.jobs.discard(job)
        log.info("made %s", [str(m) for m in made])
        if made:
            title = f"Saved {made[0].name}" if len(made) == 1 else f"Saved {len(made)} files"
            t = self.toasts.show(title, "Click to show in Files", True, self.dark,
                                 lambda: platform_linux.reveal(made[0]))
            t.gone.connect(self.maybe_quit)
        self.maybe_quit()

    def _failed(self, job, message):
        self.jobs.discard(job)
        log.error("failed: %s", message)
        first_line = message.splitlines()[0] if message else "unknown error"
        t = self.toasts.show("Couldn't do that", first_line, False, self.dark)
        t.gone.connect(self.maybe_quit)

    def maybe_quit(self):
        if self.resident:
            return
        if (self.radial.isVisible() or self.editors or self.jobs or self.toasts.busy()
                or self.prefs_window is not None):
            return
        self.qapp.quit()


def _qt_message(kind, _context, message):
    # Qt is chatty, keep only what can explain a problem
    if kind in (QtMsgType.QtWarningMsg, QtMsgType.QtCriticalMsg, QtMsgType.QtFatalMsg):
        log.debug("qt: %s", message)


def main(files=(), resident=False, settings_window=False):
    qInstallMessageHandler(_qt_message)
    qapp = QApplication(sys.argv[:1])
    qapp.setApplicationName("citrusina")
    qapp.setDesktopFileName("citrusina")
    qapp.setWindowIcon(QIcon(str(ICON)))
    qapp.setStyle("Fusion")
    qapp.setQuitOnLastWindowClosed(False)
    tools_found = {n: bool(convert.which(n)) for n in ("ffmpeg", "pandoc", "soffice", "pdftotext", "7z")}
    log.info("citrusina %s starting%s, session %s via %s, tools %s", __version__,
             " in the background" if resident else "", platform_linux.session(),
             qapp.platformName(), tools_found)
    app = Citrusina(qapp, resident)
    if settings_window:
        app.show_settings()
    elif files:
        app.open(list(files))
        if not resident and not app.radial.isVisible():
            log.error("no such file: %s", list(files))
            return 1
    elif not resident:
        return 0
    return qapp.exec()
