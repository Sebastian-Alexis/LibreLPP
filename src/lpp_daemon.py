#!/usr/bin/env python3
"""
LPP Daemon - Persistent BLE connection manager for Eluktronics LPP cooling system.
Maintains connection and exposes Unix socket for control.
"""

import asyncio
import json
import logging
import os
import signal
import sys
from pathlib import Path
from bleak import BleakClient, BleakScanner

# Configure logging for systemd journal
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s: %(message)s',
    stream=sys.stdout
)
log = logging.getLogger('lpp-daemon')

# Device info (MAC address can be set via LPP_MAC_ADDRESS env var)
DEVICE_ADDRESS = os.environ.get('LPP_MAC_ADDRESS', '')
DEVICE_NAME = "CoolingSystem"

# Nordic UART Service UUIDs
NUS_TX_CHAR_UUID = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"  # Write
NUS_RX_CHAR_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"  # Notify

# Socket path in XDG runtime directory
SOCKET_PATH = Path(os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}')) / 'lpp.sock'

# State file for persistence
STATE_PATH = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'lpp' / 'state.json'

# Reconnection settings
RECONNECT_MIN_DELAY = 1.0
RECONNECT_MAX_DELAY = 60.0


class LPPDaemon:
    def __init__(self):
        self.client: BleakClient | None = None
        self.connected = False
        self.running = True
        self.reconnect_delay = RECONNECT_MIN_DELAY
        self.reconnect_task: asyncio.Task | None = None

        # Current state - load from disk or use defaults
        self.fan_speed = 60
        self.pump_mode = 0  # High
        self._load_state()

        # Socket server
        self.server: asyncio.Server | None = None
        self.current_client: asyncio.StreamWriter | None = None

        # Keepalive task
        self.keepalive_task: asyncio.Task | None = None

    def _load_state(self):
        """Load saved state from disk."""
        try:
            if STATE_PATH.exists():
                with open(STATE_PATH) as f:
                    state = json.load(f)
                self.fan_speed = state.get('fan', 60)
                self.pump_mode = state.get('pump', 0)
                log.info(f"Loaded state: fan={self.fan_speed}%, pump={self.pump_mode}")
        except Exception as e:
            log.warning(f"Failed to load state: {e}")

    def _save_state(self):
        """Save current state to disk."""
        try:
            STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(STATE_PATH, 'w') as f:
                json.dump({'fan': self.fan_speed, 'pump': self.pump_mode}, f)
        except Exception as e:
            log.warning(f"Failed to save state: {e}")

    def notification_handler(self, sender, data: bytearray):
        """Handle notifications from the device."""
        hex_str = ' '.join(f'{b:02x}' for b in data)
        log.debug(f"Notification: {hex_str}")

    async def send_command(self, data: bytes) -> bool:
        """Send command to LPP device."""
        if not self.connected or not self.client:
            return False
        try:
            await self.client.write_gatt_char(NUS_TX_CHAR_UUID, data, response=False)
            return True
        except Exception as e:
            log.error(f"Send error: {e}")
            self.connected = False
            self._schedule_reconnect()
            return False

    async def send_fan_speed(self, speed: int, save: bool = True) -> bool:
        """Send fan speed command."""
        cmd = bytes([0xfe, 0x1b, 0x01, speed, 0x00, 0x00, 0x00, 0xef])
        if await self.send_command(cmd):
            self.fan_speed = speed
            if save:
                self._save_state()
            log.info(f"Fan set to {speed}%")
            return True
        return False

    async def send_pump_mode(self, mode: int, save: bool = True) -> bool:
        """Send pump mode command."""
        cmd = bytes([0xfe, 0x1c, 0x01, 0x3c, mode, 0x00, 0x00, 0xef])
        labels = {0: "High", 1: "Max", 2: "Low", 3: "Medium"}
        if await self.send_command(cmd):
            self.pump_mode = mode
            if save:
                self._save_state()
            log.info(f"Pump set to {labels.get(mode, mode)}")
            return True
        return False

    async def init_device(self):
        """Send initialization sequence."""
        log.info("Running device init sequence...")
        init_cmds = [
            bytes([0xfe, 0x1c, 0x01, 0x3c, 0x03, 0x00, 0x00, 0xef]),
            bytes([0xfe, 0x1b, 0x01, 0x3c, 0x00, 0x00, 0x00, 0xef]),
            bytes([0xfe, 0x1e, 0x01, 0x00, 0xb8, 0xff, 0x00, 0xef]),
            bytes([0xfe, 0x33, 0x00, 0x00, 0x00, 0x00, 0x00, 0xef]),
            b"sw",
        ]
        for cmd in init_cmds:
            await self.send_command(cmd)
            await asyncio.sleep(0.1)
        await asyncio.sleep(0.5)
        for cmd in init_cmds[:-1]:
            await self.send_command(cmd)
            await asyncio.sleep(0.1)
        log.info("Device init complete")

    async def connect_ble(self) -> bool:
        """Connect to the LPP device."""
        try:
            log.info("Scanning for LPP device...")
            devices = await BleakScanner.discover(timeout=5.0)
            address = None

            for d in devices:
                # Match by MAC address if specified
                if DEVICE_ADDRESS and DEVICE_ADDRESS.lower() == d.address.lower():
                    address = d.address
                    break
                # Otherwise match by device name
                if d.name and DEVICE_NAME.lower() in d.name.lower():
                    address = d.address
                    break

            if not address:
                log.warning("Device not found")
                return False

            log.info(f"Connecting to {address}...")
            self.client = BleakClient(address, disconnected_callback=self._on_disconnect)
            await self.client.connect()

            await self.client.start_notify(NUS_RX_CHAR_UUID, self.notification_handler)

            # Mark connected BEFORE init so commands work
            self.connected = True
            self.reconnect_delay = RECONNECT_MIN_DELAY  # Reset backoff

            await self.init_device()

            # Apply current fan/pump settings (don't re-save, just restoring)
            await asyncio.sleep(0.3)
            await self.send_fan_speed(self.fan_speed, save=False)
            await asyncio.sleep(0.1)
            await self.send_pump_mode(self.pump_mode, save=False)

            # Start keepalive to maintain connection
            self._start_keepalive()

            log.info("Connected to LPP device")
            return True

        except Exception as e:
            log.error(f"Connection failed: {e}")
            self.connected = False
            return False

    def _on_disconnect(self, client):
        """Handle unexpected disconnection."""
        log.warning("Device disconnected")
        self.connected = False
        self._stop_keepalive()
        self._schedule_reconnect()

    def _start_keepalive(self):
        """Start periodic keepalive to maintain device connection."""
        if self.keepalive_task and not self.keepalive_task.done():
            return

        async def keepalive_loop():
            while self.running and self.connected:
                await asyncio.sleep(30)  # Every 30 seconds
                if self.connected:
                    # Send sync command to keep connection active
                    log.debug("Sending keepalive")
                    await self.send_command(bytes([0xfe, 0x33, 0x00, 0x00, 0x00, 0x00, 0x00, 0xef]))

        self.keepalive_task = asyncio.create_task(keepalive_loop())

    def _stop_keepalive(self):
        """Stop the keepalive task."""
        if self.keepalive_task:
            self.keepalive_task.cancel()
            self.keepalive_task = None

    def _schedule_reconnect(self):
        """Schedule a reconnection attempt with exponential backoff."""
        if not self.running:
            return
        if self.reconnect_task and not self.reconnect_task.done():
            return  # Already scheduled

        async def reconnect():
            while self.running and not self.connected:
                log.info(f"Reconnecting in {self.reconnect_delay:.0f}s...")
                await asyncio.sleep(self.reconnect_delay)
                if await self.connect_ble():
                    break
                # Exponential backoff
                self.reconnect_delay = min(self.reconnect_delay * 2, RECONNECT_MAX_DELAY)

        self.reconnect_task = asyncio.create_task(reconnect())

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """Handle a client connection."""
        peer = writer.get_extra_info('peername')
        log.info(f"Client connected: {peer}")
        self.current_client = writer

        try:
            while self.running:
                data = await reader.readline()
                if not data:
                    break

                try:
                    request = json.loads(data.decode())
                    response = await self.process_request(request)
                except json.JSONDecodeError:
                    response = {"ok": False, "error": "Invalid JSON"}

                writer.write((json.dumps(response) + '\n').encode())
                await writer.drain()
        except ConnectionResetError:
            pass
        finally:
            log.info(f"Client disconnected: {peer}")
            self.current_client = None
            writer.close()
            await writer.wait_closed()

    async def process_request(self, request: dict) -> dict:
        """Process a client request and return response."""
        cmd = request.get('cmd', '')

        if cmd == 'status':
            return {
                "ok": True,
                "connected": self.connected,
                "fan": self.fan_speed,
                "pump": self.pump_mode
            }

        elif cmd == 'fan':
            value = request.get('value')
            if not isinstance(value, int) or not 0 <= value <= 100:
                return {"ok": False, "error": "Fan value must be 0-100"}
            if not self.connected:
                return {"ok": False, "error": "Not connected to device"}
            success = await self.send_fan_speed(value)
            return {
                "ok": success,
                "connected": self.connected,
                "fan": self.fan_speed,
                "pump": self.pump_mode
            }

        elif cmd == 'pump':
            value = request.get('value')
            if not isinstance(value, int) or not 0 <= value <= 3:
                return {"ok": False, "error": "Pump mode must be 0-3"}
            if not self.connected:
                return {"ok": False, "error": "Not connected to device"}
            success = await self.send_pump_mode(value)
            return {
                "ok": success,
                "connected": self.connected,
                "fan": self.fan_speed,
                "pump": self.pump_mode
            }

        elif cmd == 'reconnect':
            if self.connected:
                return {"ok": True, "connected": True, "fan": self.fan_speed, "pump": self.pump_mode}
            self._schedule_reconnect()
            return {"ok": True, "connected": False, "message": "Reconnection scheduled"}

        else:
            return {"ok": False, "error": f"Unknown command: {cmd}"}

    async def run(self):
        """Main daemon loop."""
        # Remove stale socket
        if SOCKET_PATH.exists():
            SOCKET_PATH.unlink()

        # Start Unix socket server
        self.server = await asyncio.start_unix_server(
            self.handle_client,
            path=str(SOCKET_PATH)
        )
        SOCKET_PATH.chmod(0o600)  # Owner only
        log.info(f"Listening on {SOCKET_PATH}")

        # Initial connection attempt
        if not await self.connect_ble():
            self._schedule_reconnect()

        # Run until shutdown
        async with self.server:
            await self.server.serve_forever()

    async def shutdown(self):
        """Clean shutdown."""
        log.info("Shutting down...")
        self.running = False

        self._stop_keepalive()

        if self.reconnect_task:
            self.reconnect_task.cancel()

        if self.current_client:
            self.current_client.close()

        if self.server:
            self.server.close()
            await self.server.wait_closed()

        if self.client and self.connected:
            try:
                await self.client.disconnect()
            except Exception:
                pass

        if SOCKET_PATH.exists():
            SOCKET_PATH.unlink()

        log.info("Shutdown complete")


async def main():
    daemon = LPPDaemon()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(daemon.shutdown()))

    try:
        await daemon.run()
    except asyncio.CancelledError:
        pass


if __name__ == "__main__":
    asyncio.run(main())
