#!/bin/bash
# LPP Control - Installation Script

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "LPP Control Installer"
echo "====================="
echo

# Check for Python
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is required but not installed."
    exit 1
fi

# Check for Bluetooth
if ! command -v bluetoothctl &> /dev/null; then
    echo "Warning: bluetoothctl not found. Make sure Bluetooth is set up."
fi

# Create virtual environment if it doesn't exist
if [ ! -d "$SCRIPT_DIR/venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$SCRIPT_DIR/venv"
fi

# Install dependencies
echo "Installing Python dependencies..."
"$SCRIPT_DIR/venv/bin/pip" install -q -r "$SCRIPT_DIR/requirements.txt"

# Get MAC address
echo
echo "Enter your LPP device MAC address (or press Enter to auto-detect by name):"
echo "  You can find this using: bluetoothctl devices"
echo "  Example: EA:C4:6D:49:31:E4"
read -p "> " MAC_ADDRESS

# Create systemd service
echo "Installing systemd user service..."
mkdir -p ~/.config/systemd/user/

cat > ~/.config/systemd/user/lpp-daemon.service << EOF
[Unit]
Description=LPP Cooling System Daemon
After=bluetooth.target

[Service]
Type=simple
ExecStart=$SCRIPT_DIR/venv/bin/python $SCRIPT_DIR/src/lpp_daemon.py
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1
Environment=LPP_MAC_ADDRESS=$MAC_ADDRESS

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload

# Create launcher script
echo "Creating launcher script..."
cat > "$SCRIPT_DIR/lpp-control" << EOF
#!/bin/bash
cd "$SCRIPT_DIR"
source venv/bin/activate
exec python src/lpp_tui.py "\$@"
EOF
chmod +x "$SCRIPT_DIR/lpp-control"

# Symlink to ~/bin if it exists and is in PATH
if [ -d "$HOME/bin" ]; then
    ln -sf "$SCRIPT_DIR/lpp-control" "$HOME/bin/lpp-control"
    echo "Linked lpp-control to ~/bin/"
fi

# Create desktop entry
echo "Creating desktop entry..."
mkdir -p ~/.local/share/applications/

# Try to find a terminal emulator
TERMINAL=""
if command -v ghostty &> /dev/null; then
    TERMINAL="ghostty -e"
elif command -v kitty &> /dev/null; then
    TERMINAL="kitty"
elif command -v alacritty &> /dev/null; then
    TERMINAL="alacritty -e"
elif command -v gnome-terminal &> /dev/null; then
    TERMINAL="gnome-terminal --"
else
    TERMINAL="xterm -e"
fi

cat > ~/.local/share/applications/lpp-control.desktop << EOF
[Desktop Entry]
Name=LPP Control
Comment=Eluktronics LPP Cooling System Control Panel
Exec=$TERMINAL $SCRIPT_DIR/lpp-control
Icon=$SCRIPT_DIR/icon.png
Terminal=false
Type=Application
Categories=System;Settings;HardwareSettings;
Keywords=cooling;fan;pump;lpp;eluktronics;
EOF

# Download icon if not present
if [ ! -f "$SCRIPT_DIR/icon.png" ]; then
    echo "Downloading icon..."
    curl -sL "https://cdn11.bigcommerce.com/s-g9br3/product_images/Bigcommerce_Tab-logo.png" -o "$SCRIPT_DIR/icon.png" 2>/dev/null || true
fi

echo
echo "Installation complete!"
echo
echo "To start the daemon now:"
echo "  systemctl --user start lpp-daemon"
echo
echo "To enable at boot:"
echo "  systemctl --user enable lpp-daemon"
echo "  loginctl enable-linger \$USER"
echo
echo "To run the control panel:"
echo "  lpp-control"
echo
