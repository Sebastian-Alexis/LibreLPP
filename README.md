# LPP Control for Linux

A Linux control panel for the Eluktronics LPP (Liquid Propulsion Package) cooling system.

![LPP Control TUI](https://img.shields.io/badge/TUI-Textual-blue)
![Python 3.10+](https://img.shields.io/badge/Python-3.10+-green)
![License](https://img.shields.io/badge/License-MIT-yellow)

## Features

- Control fan speed (0-100%)
- Control pump modes (Low, Medium, High, Max)
- Persistent background daemon maintains BLE connection
- Auto-reconnect if device disconnects
- Remembers last settings across reboots
- Modern terminal UI with keyboard shortcuts

## Requirements

- Linux with Bluetooth LE support
- Python 3.10+
- Eluktronics laptop with LPP cooling system

## Installation

```bash
git clone https://github.com/yourusername/LPP_linux.git
cd LPP_linux
./install.sh
```

The installer will:
1. Create a Python virtual environment
2. Install dependencies
3. Set up a systemd user service
4. Create a desktop entry for your app menu

## Usage

### Start the Daemon

```bash
# Start now
systemctl --user start lpp-daemon

# Enable at boot
systemctl --user enable lpp-daemon
loginctl enable-linger $USER
```

### Run the Control Panel

```bash
lpp-control
```

Or launch "LPP Control" from your application menu.

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Up/Down` | Adjust fan speed |
| `1` | Pump Low |
| `2` | Pump Medium |
| `3` | Pump High |
| `4` | Pump Max |
| `r` | Reconnect BLE |
| `q` | Quit |

## Configuration

### MAC Address

The daemon can find your LPP device by name ("CoolingSystem") or by MAC address.

To specify a MAC address, set the `LPP_MAC_ADDRESS` environment variable in your systemd service:

```bash
# Edit the service
systemctl --user edit lpp-daemon

# Add:
[Service]
Environment=LPP_MAC_ADDRESS=XX:XX:XX:XX:XX:XX
```

Find your device MAC with:
```bash
bluetoothctl devices
```

### State File

Fan/pump settings are saved to `~/.config/lpp/state.json` and restored on daemon restart.

## Troubleshooting

### Daemon won't connect

1. Make sure Bluetooth is enabled: `bluetoothctl power on`
2. Check daemon logs: `journalctl --user -u lpp-daemon -f`
3. Verify the LPP is powered on (yellow flashing light = waiting for connection)

### TUI shows "Daemon Offline"

Start the daemon: `systemctl --user start lpp-daemon`

### TUI shows "BLE Disconnected"

The daemon is running but can't reach the device. Press `r` to retry or check Bluetooth.

## Architecture

```
┌─────────────────┐     Unix Socket      ┌──────────────┐
│   lpp_tui.py    │◄───────────────────►│  lpp_daemon  │
│  (Control Panel)│   JSON messages      │  (Background)│
└─────────────────┘                      └──────┬───────┘
                                                │ BLE
                                         ┌──────▼───────┐
                                         │  LPP Device  │
                                         └──────────────┘
```

The daemon maintains a persistent Bluetooth LE connection and exposes a Unix socket for the TUI (or other clients) to send commands.

## License

MIT License - see [LICENSE](LICENSE) file.

## Acknowledgments

- Reverse engineered from the Windows Eluktronics Control Center
- Built with [Textual](https://textual.textualize.io/) and [Bleak](https://bleak.readthedocs.io/)
