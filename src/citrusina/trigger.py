"""Shift+drag on X11: hold the trigger key while dragging a file and the wheel opens under it.

There's no hook, it just asks X where the pointer is and what's held every 15 ms. That needs
nothing but libX11 and no permissions. Wayland doesn't let an app see input outside its own
windows, so there this stays off and the drop bubble does the job instead.
"""
import ctypes
import ctypes.util
import math

from PySide6.QtCore import QObject, QPoint, QTimer, Signal

MASKS = {"shift": 1 << 0, "ctrl": 1 << 2, "alt": 1 << 3}
BUTTON1 = 1 << 8
DRAG_THRESHOLD = 10


class _X11:
    def __init__(self):
        name = ctypes.util.find_library("X11")
        if not name:
            raise OSError("libX11 not found")
        self.lib = ctypes.cdll.LoadLibrary(name)
        self.lib.XOpenDisplay.restype = ctypes.c_void_p
        self.lib.XOpenDisplay.argtypes = [ctypes.c_char_p]
        self.lib.XDefaultRootWindow.restype = ctypes.c_ulong
        self.lib.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
        u, i = ctypes.c_ulong, ctypes.c_int
        self.lib.XQueryPointer.argtypes = [ctypes.c_void_p, u] + [ctypes.POINTER(u)] * 2 + \
            [ctypes.POINTER(i)] * 4 + [ctypes.POINTER(ctypes.c_uint)]
        self.display = self.lib.XOpenDisplay(None)
        if not self.display:
            raise OSError("can't open the X display")
        self.root = self.lib.XDefaultRootWindow(self.display)

    def pointer(self):
        root, child = ctypes.c_ulong(), ctypes.c_ulong()
        rx, ry, wx, wy = (ctypes.c_int() for _ in range(4))
        mask = ctypes.c_uint()
        self.lib.XQueryPointer(self.display, self.root, ctypes.byref(root), ctypes.byref(child),
                               ctypes.byref(rx), ctypes.byref(ry), ctypes.byref(wx),
                               ctypes.byref(wy), ctypes.byref(mask))
        return rx.value, ry.value, mask.value


class Trigger(QObject):
    fired = Signal(QPoint)

    def __init__(self, key="shift", parent=None):
        super().__init__(parent)
        self.key = key
        self.x = _X11()
        self.origin = None
        self.done = False
        self.timer = QTimer(self, interval=15, timeout=self._poll)
        self.timer.start()

    def _poll(self):
        x, y, mask = self.x.pointer()
        if not mask & BUTTON1:
            self.origin = None
            self.done = False
            return
        if self.origin is None:
            self.origin = (x, y)
        # once per press, and only after a real drag so a shift+click stays a shift+click
        if (not self.done and mask & MASKS[self.key]
                and math.dist(self.origin, (x, y)) > DRAG_THRESHOLD):
            self.done = True
            self.fired.emit(QPoint(x, y))
