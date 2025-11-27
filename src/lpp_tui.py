#!/usr/bin/env python3
"""
LPP Control Panel - Textual TUI
Control Eluktronics LPP cooling system with a modern terminal interface.
Connects to lpp_daemon for persistent BLE connection.
"""

import asyncio
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal
from textual.widgets import Header, Footer, Static, Button, Label
from textual_slider import Slider
from textual.reactive import reactive
from textual.binding import Binding
from textual import on

from lpp_client import LPPClient


class FanControl(Static):
    """Fan speed control widget with slider."""

    fan_speed = reactive(60)

    def compose(self) -> ComposeResult:
        yield Label("FAN SPEED", classes="control-label")
        yield Horizontal(
            Slider(min=0, max=100, value=60, step=5, id="fan-slider"),
            Label("60%", id="fan-value"),
            classes="slider-row"
        )

    def watch_fan_speed(self, speed: int) -> None:
        try:
            self.query_one("#fan-slider", Slider).value = speed
            self.query_one("#fan-value", Label).update(f"{speed}%")
        except:
            pass


class PumpControl(Static):
    """Pump mode control widget."""

    pump_mode = reactive(0)

    def compose(self) -> ComposeResult:
        yield Label("PUMP MODE", classes="control-label")
        yield Horizontal(
            Button("Low", id="pump-2", classes="mode-btn"),
            Button("Medium", id="pump-3", classes="mode-btn"),
            Button("High", id="pump-0", classes="mode-btn selected"),
            Button("Max", id="pump-1", classes="mode-btn"),
            classes="button-row"
        )

    def set_mode(self, mode: int) -> None:
        self.pump_mode = mode
        for btn in self.query(".mode-btn"):
            btn.remove_class("selected")
        mode_map = {2: "pump-2", 3: "pump-3", 0: "pump-0", 1: "pump-1"}
        self.query_one(f"#{mode_map[mode]}").add_class("selected")


class StatusDisplay(Static):
    """Connection status display."""

    daemon_connected = reactive(False)
    ble_connected = reactive(False)

    def compose(self) -> ComposeResult:
        yield Horizontal(
            Static("●", id="status-dot"),
            Label("Disconnected", id="status-label"),
            classes="status-row"
        )

    def update_status(self, daemon: bool, ble: bool) -> None:
        self.daemon_connected = daemon
        self.ble_connected = ble
        dot = self.query_one("#status-dot", Static)
        label = self.query_one("#status-label", Label)

        if daemon and ble:
            dot.update("●")
            dot.add_class("connected")
            dot.remove_class("disconnected")
            dot.remove_class("partial")
            label.update("Connected")
        elif daemon and not ble:
            dot.update("●")
            dot.add_class("partial")
            dot.remove_class("connected")
            dot.remove_class("disconnected")
            label.update("BLE Disconnected")
        else:
            dot.update("●")
            dot.add_class("disconnected")
            dot.remove_class("connected")
            dot.remove_class("partial")
            label.update("Daemon Offline")


class LPPControlApp(App):
    """Main LPP Control Panel application."""

    CSS = """
    Screen {
        background: #0a0a0a;
    }

    Header {
        background: #1a1a1a;
        color: #ffffff;
    }

    Footer {
        background: #1a1a1a;
        color: #888888;
    }

    #main-container {
        width: 100%;
        height: 100%;
        padding: 1 2;
        background: #0a0a0a;
    }

    .control-panel {
        width: 100%;
        height: auto;
        border: solid #333333;
        padding: 1 2;
        margin-bottom: 1;
        background: #111111;
    }

    .control-label {
        text-style: bold;
        color: #ffffff;
        margin-bottom: 1;
    }

    .slider-row {
        width: 100%;
        height: 3;
        align: center middle;
    }

    #fan-slider {
        width: 80%;
    }

    Slider {
        background: #222222;
    }

    Slider > .slider-track {
        background: #333333;
    }

    Slider > .slider-track-filled {
        background: #ffffff;
    }

    Slider > .slider-thumb {
        background: #ffffff;
    }

    #fan-value {
        width: 10%;
        text-align: right;
        color: #ffffff;
        text-style: bold;
        margin-left: 2;
    }

    .button-row {
        width: 100%;
        height: auto;
        align: center middle;
    }

    Button {
        background: #222222;
        color: #aaaaaa;
        border: tall #333333;
        margin: 0 1;
    }

    Button:hover {
        background: #333333;
        color: #ffffff;
        border: tall #555555;
    }

    Button:focus {
        background: #333333;
        color: #ffffff;
        border: tall #666666;
    }

    .mode-btn {
        min-width: 10;
    }

    .mode-btn.selected {
        background: #ffffff;
        color: #000000;
        border: tall #ffffff;
        text-style: bold;
    }

    .status-row {
        width: 100%;
        height: 3;
        align: center middle;
        padding: 1;
    }

    #status-dot {
        width: 3;
        text-style: bold;
    }

    #status-dot.connected {
        color: #00ff00;
    }

    #status-dot.partial {
        color: #ffaa00;
    }

    #status-dot.disconnected {
        color: #666666;
    }

    #status-label {
        margin-left: 1;
        color: #888888;
    }

    #reconnect-btn {
        margin-top: 1;
        width: 100%;
        background: #222222;
        color: #ffffff;
        border: tall #444444;
    }

    #reconnect-btn:hover {
        background: #333333;
        border: tall #666666;
    }

    .title-box {
        width: 100%;
        height: 3;
        content-align: center middle;
        text-style: bold;
        color: #ffffff;
        border: solid #333333;
        margin-bottom: 1;
        background: #1a1a1a;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "reconnect", "Reconnect"),
        Binding("up", "fan_up", "Fan +5%"),
        Binding("down", "fan_down", "Fan -5%"),
        Binding("1", "pump_low", "Pump Low"),
        Binding("2", "pump_med", "Pump Medium"),
        Binding("3", "pump_high", "Pump High"),
        Binding("4", "pump_max", "Pump Max"),
    ]

    def __init__(self):
        super().__init__()
        self.client = LPPClient()
        self.daemon_connected = False
        self.ble_connected = False

    def compose(self) -> ComposeResult:
        yield Header()
        yield Container(
            Static("LPP CONTROL PANEL", classes="title-box"),
            StatusDisplay(id="status"),
            Button("Reconnect BLE", id="reconnect-btn"),
            FanControl(id="fan-control", classes="control-panel"),
            PumpControl(id="pump-control", classes="control-panel"),
            id="main-container"
        )
        yield Footer()

    async def on_mount(self) -> None:
        """Connect to daemon on startup."""
        await self.connect_daemon()
        # Start periodic status check
        self.set_interval(2.0, self.check_status)

    async def connect_daemon(self) -> None:
        """Connect to the LPP daemon."""
        self.daemon_connected = self.client.connect()
        if self.daemon_connected:
            await self.sync_state()
        self.update_status_display()

    async def sync_state(self) -> None:
        """Sync UI state from daemon."""
        result = self.client.get_status()
        if result.get("ok"):
            self.ble_connected = result.get("connected", False)
            fan = self.query_one("#fan-control", FanControl)
            pump = self.query_one("#pump-control", PumpControl)
            fan.fan_speed = result.get("fan", 60)
            pump.set_mode(result.get("pump", 0))
        else:
            self.daemon_connected = False

    async def check_status(self) -> None:
        """Periodic status check."""
        if not self.daemon_connected:
            await self.connect_daemon()
            return

        result = self.client.get_status()
        if result.get("ok"):
            self.ble_connected = result.get("connected", False)
        else:
            self.daemon_connected = False
            self.client.disconnect()
        self.update_status_display()

    def update_status_display(self) -> None:
        """Update the status display widget."""
        status = self.query_one("#status", StatusDisplay)
        status.update_status(self.daemon_connected, self.ble_connected)

    # Event handlers
    @on(Button.Pressed, "#reconnect-btn")
    async def on_reconnect_pressed(self) -> None:
        if not self.daemon_connected:
            await self.connect_daemon()
        else:
            result = self.client.reconnect_ble()
            if result.get("ok"):
                self.notify("Reconnection requested", severity="information")
            else:
                self.notify(result.get("error", "Failed"), severity="error")

    @on(Slider.Changed, "#fan-slider")
    async def on_fan_slider_changed(self, event: Slider.Changed) -> None:
        fan = self.query_one("#fan-control", FanControl)
        speed = int(event.value)
        fan.query_one("#fan-value", Label).update(f"{speed}%")

        if self.daemon_connected:
            result = self.client.set_fan(speed)
            if not result.get("ok"):
                self.notify(result.get("error", "Failed"), severity="error")

    @on(Button.Pressed, "#pump-0")
    async def on_pump_high(self) -> None:
        await self._set_pump(0)

    @on(Button.Pressed, "#pump-1")
    async def on_pump_max(self) -> None:
        await self._set_pump(1)

    @on(Button.Pressed, "#pump-2")
    async def on_pump_low(self) -> None:
        await self._set_pump(2)

    @on(Button.Pressed, "#pump-3")
    async def on_pump_med(self) -> None:
        await self._set_pump(3)

    async def _set_pump(self, mode: int) -> None:
        pump = self.query_one("#pump-control", PumpControl)
        pump.set_mode(mode)
        if self.daemon_connected:
            result = self.client.set_pump(mode)
            if result.get("ok"):
                labels = {0: "High", 1: "Max", 2: "Low", 3: "Medium"}
                self.notify(f"Pump: {labels.get(mode)}", severity="information")
            else:
                self.notify(result.get("error", "Failed"), severity="error")

    # Keyboard actions
    def action_reconnect(self) -> None:
        asyncio.create_task(self.on_reconnect_pressed())

    def action_fan_up(self) -> None:
        fan = self.query_one("#fan-control", FanControl)
        slider = fan.query_one("#fan-slider", Slider)
        new_val = min(100, slider.value + 5)
        slider.value = new_val

    def action_fan_down(self) -> None:
        fan = self.query_one("#fan-control", FanControl)
        slider = fan.query_one("#fan-slider", Slider)
        new_val = max(0, slider.value - 5)
        slider.value = new_val

    def action_pump_low(self) -> None:
        asyncio.create_task(self._set_pump(2))

    def action_pump_med(self) -> None:
        asyncio.create_task(self._set_pump(3))

    def action_pump_high(self) -> None:
        asyncio.create_task(self._set_pump(0))

    def action_pump_max(self) -> None:
        asyncio.create_task(self._set_pump(1))


def main():
    app = LPPControlApp()
    app.title = "LPP Control Panel"
    app.run()


if __name__ == "__main__":
    main()
