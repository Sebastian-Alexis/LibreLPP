#!/usr/bin/env python3
"""
LPP Client - Client library for communicating with lpp_daemon.
"""

import json
import os
import socket
from pathlib import Path
from typing import Any


# Socket path in XDG runtime directory
SOCKET_PATH = Path(os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}')) / 'lpp.sock'


class LPPClient:
    """Client for communicating with the LPP daemon."""

    def __init__(self, socket_path: Path | str | None = None):
        self.socket_path = Path(socket_path) if socket_path else SOCKET_PATH
        self.sock: socket.socket | None = None

    def connect(self) -> bool:
        """Connect to the daemon socket."""
        if self.sock:
            return True
        try:
            self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.sock.connect(str(self.socket_path))
            self.sock.settimeout(5.0)
            return True
        except (socket.error, FileNotFoundError) as e:
            self.sock = None
            return False

    def disconnect(self):
        """Disconnect from the daemon."""
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None

    def _send_request(self, request: dict) -> dict:
        """Send a request and receive response."""
        if not self.sock:
            return {"ok": False, "error": "Not connected to daemon"}

        try:
            msg = json.dumps(request) + '\n'
            self.sock.sendall(msg.encode())

            response = b''
            while True:
                chunk = self.sock.recv(4096)
                if not chunk:
                    raise ConnectionError("Daemon closed connection")
                response += chunk
                if b'\n' in response:
                    break

            return json.loads(response.decode().strip())
        except (socket.error, json.JSONDecodeError, ConnectionError) as e:
            self.disconnect()
            return {"ok": False, "error": str(e)}

    def get_status(self) -> dict:
        """Get current status from daemon."""
        return self._send_request({"cmd": "status"})

    def set_fan(self, speed: int) -> dict:
        """Set fan speed (0-100)."""
        return self._send_request({"cmd": "fan", "value": speed})

    def set_pump(self, mode: int) -> dict:
        """Set pump mode (0=High, 1=Max, 2=Low, 3=Medium)."""
        return self._send_request({"cmd": "pump", "value": mode})

    def reconnect_ble(self) -> dict:
        """Request daemon to reconnect to BLE device."""
        return self._send_request({"cmd": "reconnect"})

    @property
    def is_connected(self) -> bool:
        """Check if connected to daemon."""
        return self.sock is not None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()


def daemon_running() -> bool:
    """Check if the daemon is running."""
    with LPPClient() as client:
        if not client.is_connected:
            return False
        result = client.get_status()
        return result.get("ok", False)
