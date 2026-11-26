"""Local socket the notch app connects to (docs/notch-design.md).

Newline-delimited JSON over a Unix domain socket. Python sends events (state,
heard, reply, ...); the app sends answers back. The socket is owner-only (the
folder 0700, the file 0600) so no other local user can listen in or answer.

Nothing here is trusted for safety: a click is only a request, and whether it
counts is decided by the confirmation logic in Python.
"""

import json
import os
import socket
import threading
from pathlib import Path
from typing import Callable

DEFAULT_PATH = Path(os.environ.get("ASH_UI_SOCKET") or Path.home() / ".ash" / "ash.sock")
SEND_TIMEOUT_SECONDS = 1.0


class UIBridge:
    def __init__(self, path: Path | str | None = None, on_answer: Callable[[str, str], None] | None = None, log=print):
        self.path = Path(path or DEFAULT_PATH)
        self.on_answer = on_answer or (lambda confirm_id, answer: None)
        self.log = log
        self._server: socket.socket | None = None
        self._client: socket.socket | None = None
        self._lock = threading.Lock()
        self._last_state: dict | None = None  # replayed to an app that connects late
        self._stopped = False

    def start(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(self.path.parent, 0o700)
        if self.path.exists():
            probe = socket.socket(socket.AF_UNIX)
            try:
                probe.connect(str(self.path))
            except OSError:
                self.path.unlink()  # stale file from a crashed run
            else:
                raise RuntimeError(f"another Ash agent is already running ({self.path})")
            finally:
                probe.close()
        server = socket.socket(socket.AF_UNIX)
        old_umask = os.umask(0o177)  # the socket file is created 0600
        try:
            server.bind(str(self.path))
        finally:
            os.umask(old_umask)
        os.chmod(self.path, 0o600)
        server.listen(1)
        self._server = server
        threading.Thread(target=self._accept_loop, daemon=True, name="ui-bridge-accept").start()

    def stop(self) -> None:
        self._stopped = True
        with self._lock:
            for sock in (self._client, self._server):
                if sock:
                    try:
                        sock.close()
                    except OSError:
                        pass
            self._client = None
        self.path.unlink(missing_ok=True)

    def emit(self, event: dict) -> None:
        """Send an event to the app if one is connected. Never raises."""
        line = (json.dumps(event, ensure_ascii=False) + "\n").encode()
        with self._lock:
            if event.get("type") == "state":
                self._last_state = event
            self._send(line)

    def _send(self, line: bytes) -> None:
        if self._client is None:
            return
        try:
            self._client.sendall(line)
        except OSError:
            self._drop_client()

    def _drop_client(self) -> None:
        if self._client:
            try:
                self._client.close()
            except OSError:
                pass
        self._client = None

    def _accept_loop(self) -> None:
        while not self._stopped:
            try:
                client, _ = self._server.accept()
            except OSError:
                return
            client.settimeout(None)
            with self._lock:
                self._drop_client()  # one app at a time: the newest wins
                self._client = client
                if self._last_state:
                    self._send((json.dumps(self._last_state) + "\n").encode())
            threading.Thread(target=self._read_loop, args=(client,), daemon=True, name="ui-bridge-read").start()

    def _read_loop(self, client: socket.socket) -> None:
        buffer = b""
        try:
            while True:
                chunk = client.recv(4096)
                if not chunk:
                    return
                buffer += chunk
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    self._handle(line)
        except OSError:
            return

    def _handle(self, line: bytes) -> None:
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            self.log(f"[ui] ignoring malformed line: {line[:80]!r}")
            return
        if isinstance(message, dict) and message.get("type") == "answer":
            confirm_id, answer = message.get("id"), message.get("answer")
            if isinstance(confirm_id, str) and answer in ("yes", "no"):
                self.on_answer(confirm_id, answer)
            return
        self.log(f"[ui] ignoring unknown message: {str(message)[:80]}")
