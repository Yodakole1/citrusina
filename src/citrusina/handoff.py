"""One citrusina at a time. A second launch, from the Files menu say, passes its files to the
one already running and exits, so the wheel opens instantly and settings stay in one place."""
import json
import os

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

NAME = f"citrusina-{os.getuid()}"


def try_handoff(paths, action=None):
    sock = QLocalSocket()
    sock.connectToServer(NAME)
    if not sock.waitForConnected(300):
        return False
    message = {"files": [os.path.abspath(p) for p in paths], "action": action}
    sock.write(json.dumps(message).encode() + b"\n")
    sock.waitForBytesWritten(1000)
    sock.disconnectFromServer()
    return True


class Server(QObject):
    received = Signal(list)
    action = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.server = QLocalServer(self)
        # nobody answered try_handoff, so a leftover socket is from a crash
        QLocalServer.removeServer(NAME)
        self.server.listen(NAME)
        self.server.newConnection.connect(self._accept)

    def _accept(self):
        while self.server.hasPendingConnections():
            sock = self.server.nextPendingConnection()
            sock.readyRead.connect(lambda s=sock: self._read(s))

    def _read(self, sock):
        if not sock.canReadLine():
            return
        try:
            message = json.loads(bytes(sock.readLine()).decode())
            files, action = message.get("files", []), message.get("action")
        except (ValueError, AttributeError):
            files, action = [], None
        sock.disconnectFromServer()
        if isinstance(action, str):
            self.action.emit(action)
        if isinstance(files, list) and files:
            self.received.emit([f for f in files if isinstance(f, str)])
