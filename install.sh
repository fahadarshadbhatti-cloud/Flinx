#!/usr/bin/env bash
# install.sh — Lowen one-command setup script
# Supports Fedora, Arch Linux, Ubuntu/Debian, openSUSE on Wayland (KDE Plasma 6, GNOME, Sway, Hyprland)
#
# Usage:
#   bash install.sh
#   bash install.sh --api-key gsk_xxxx

set -euo pipefail

LOWEN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$HOME/.config/lowen"
VENV_DIR="$LOWEN_DIR/.venv"

# ─────────────────────────────────────────────
# Colours & Formatting
# ─────────────────────────────────────────────
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

info()    { echo -e "${GREEN}[lowen]${NC} $*"; }
warn()    { echo -e "${YELLOW}[warn]${NC}  $*"; }
error()   { echo -e "${RED}[error]${NC} $*" >&2; }
section() { echo; echo -e "${BLUE}──────────────────────────────────────────${NC}"; echo -e "${BLUE}  $*${NC}"; echo -e "${BLUE}──────────────────────────────────────────${NC}"; }

# ─────────────────────────────────────────────
# Parse flags
# ─────────────────────────────────────────────
API_KEY=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --api-key) API_KEY="$2"; shift 2 ;;
        *) error "Unknown argument: $1"; exit 1 ;;
    esac
done

# ─────────────────────────────────────────────
# 1. System packages (Multi-Distro Detection)
# ─────────────────────────────────────────────
section "Installing system packages"

if command -v dnf &>/dev/null; then
    info "Detected Fedora / RHEL package manager (dnf)"
    sudo dnf install -y ydotool wl-clipboard python3-pip python3-devel portaudio-devel
elif command -v pacman &>/dev/null; then
    info "Detected Arch Linux package manager (pacman)"
    sudo pacman -S --needed --noconfirm ydotool wl-clipboard python-pip portaudio
elif command -v apt-get &>/dev/null; then
    info "Detected Debian / Ubuntu package manager (apt)"
    sudo apt-get update
    sudo apt-get install -y ydotool wl-clipboard python3-pip python3-venv python3-dev portaudio19-dev
elif command -v zypper &>/dev/null; then
    info "Detected openSUSE package manager (zypper)"
    sudo zypper install -y ydotool wl-clipboard python3-pip python3-devel portaudio-devel
else
    warn "Could not identify standard package manager. Please ensure the following are installed:"
    warn "  - ydotool, wl-clipboard, python3, pip, portaudio development headers"
fi

info "System packages verified"

# ─────────────────────────────────────────────
# 2. Add user to input group (for evdev hotkey)
# ─────────────────────────────────────────────
section "Configuring input group permissions"
NEEDS_RELOGIN=false
if id -nG "$USER" | grep -qw input; then
    info "User is already in 'input' group"
else
    info "Adding user '$USER' to 'input' group..."
    sudo usermod -aG input "$USER"
    warn "Added you to the 'input' group."
    NEEDS_RELOGIN=true
fi

# ─────────────────────────────────────────────
# 3. udev rule for /dev/uinput (ydotool)
# ─────────────────────────────────────────────
section "Configuring udev rules for ydotool"
UDEV_RULE='KERNEL=="uinput", GROUP="input", MODE="0660", OPTIONS+="static_node=uinput"'
UDEV_FILE="/etc/udev/rules.d/80-uinput.rules"
if [ -f "$UDEV_FILE" ] && grep -qF "$UDEV_RULE" "$UDEV_FILE"; then
    info "udev rule already installed at $UDEV_FILE"
else
    info "Writing udev rule to $UDEV_FILE..."
    echo "$UDEV_RULE" | sudo tee "$UDEV_FILE" > /dev/null
    sudo udevadm control --reload-rules
    sudo udevadm trigger
    info "udev rule installed successfully"
fi

# ─────────────────────────────────────────────
# 4. ydotoold systemd user service
# ─────────────────────────────────────────────
section "Installing ydotoold systemd user service"
SYSTEMD_USER_DIR="$HOME/.config/systemd/user"
mkdir -p "$SYSTEMD_USER_DIR"

cat > "$SYSTEMD_USER_DIR/ydotoold.service" <<'EOF'
[Unit]
Description=ydotool daemon
After=graphical-session.target

[Service]
Type=simple
ExecStart=/usr/bin/ydotoold
Restart=on-failure
RestartSec=3

[Install]
WantedBy=default.target
EOF

info "Reloading systemd user daemon..."
systemctl --user daemon-reload
systemctl --user enable ydotoold
systemctl --user start ydotoold || warn "ydotoold will become active after logging out and in."
info "ydotoold service configured"

# ─────────────────────────────────────────────
# 5. Python virtual environment & dependencies
# ─────────────────────────────────────────────
section "Setting up Python virtual environment"
if [ -d "$VENV_DIR" ]; then
    info "Virtual environment found at $VENV_DIR"
else
    info "Creating virtual environment at $VENV_DIR..."
    python3 -m venv "$VENV_DIR"
fi

info "Upgrading pip..."
"$VENV_DIR/bin/pip" install --upgrade pip --quiet

info "Installing dependencies..."
"$VENV_DIR/bin/pip" install evdev-binary --quiet || true
"$VENV_DIR/bin/pip" install -r "$LOWEN_DIR/requirements.txt" --quiet

info "Python dependencies installed successfully"

# ─────────────────────────────────────────────
# 6. Config file setup & Groq Key prompt
# ─────────────────────────────────────────────
section "Setting up configuration file"
mkdir -p "$CONFIG_DIR"

if [ -f "$CONFIG_DIR/.env" ]; then
    info "Config already exists at $CONFIG_DIR/.env — keeping existing config"
else
    cp "$LOWEN_DIR/.env.example" "$CONFIG_DIR/.env"
    
    if [ -z "$API_KEY" ]; then
        echo -e "${YELLOW}Please enter your Groq API key (leave empty to configure later):${NC}"
        read -r -p "API Key: " USER_KEY
        if [ -n "$USER_KEY" ]; then
            API_KEY="$USER_KEY"
        fi
    fi

    if [ -n "$API_KEY" ]; then
        sed -i "s|GROQ_API_KEY=gsk_xxxx|GROQ_API_KEY=$API_KEY|" "$CONFIG_DIR/.env"
        info "API key saved to config"
    else
        warn "No API key entered. Remember to set GROQ_API_KEY in $CONFIG_DIR/.env before use."
    fi
    info "Config file created at $CONFIG_DIR/.env"
fi

# ─────────────────────────────────────────────
# 7. Lowen launcher script
# ─────────────────────────────────────────────
section "Creating user CLI launcher"
LAUNCHER_DIR="$HOME/.local/bin"
LAUNCHER="$LAUNCHER_DIR/lowen"
mkdir -p "$LAUNCHER_DIR"

cat > "$LAUNCHER" <<EOF
#!/usr/bin/env bash
export PYTHONPATH="$LOWEN_DIR:\${PYTHONPATH:-}"
exec "$VENV_DIR/bin/python" "$LOWEN_DIR/main.py" "\$@"
EOF
chmod +x "$LAUNCHER"
info "Launcher executable created at $LAUNCHER"

if [[ ":$PATH:" != *":$LAUNCHER_DIR:"* ]]; then
    warn "$LAUNCHER_DIR is not currently in your PATH. Consider adding it to your ~/.bashrc or ~/.zshrc:"
    echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
fi

# ─────────────────────────────────────────────
# 8. Desktop Entry and Icon Installation
# ─────────────────────────────────────────────
section "Installing desktop icon and application launcher"
ICON_DIR="$HOME/.local/share/icons/hicolor/scalable/apps"
mkdir -p "$ICON_DIR"
if [ -f "$LOWEN_DIR/resources/icon.svg" ]; then
    cp "$LOWEN_DIR/resources/icon.svg" "$ICON_DIR/lowen.svg"
    info "Icon installed to $ICON_DIR/lowen.svg"
fi

DESKTOP_DIR="$HOME/.local/share/applications"
mkdir -p "$DESKTOP_DIR"
cat > "$DESKTOP_DIR/lowen.desktop" <<EOF
[Desktop Entry]
Name=Lowen
GenericName=Voice-to-Text Dictation
Comment=Wayland voice-to-text with glassmorphic pill overlay
Exec=$LAUNCHER
Icon=lowen
Terminal=false
Type=Application
Categories=Utility;Accessibility;AudioVideo;
Keywords=voice;dictation;speech;whisper;groq;transcription;
StartupNotify=false
EOF
info "Desktop launcher created at $DESKTOP_DIR/lowen.desktop"

# ─────────────────────────────────────────────
# 9. Lowen systemd autostart service
# ─────────────────────────────────────────────
section "Installing Lowen systemd user service"
cat > "$SYSTEMD_USER_DIR/lowen.service" <<EOF
[Unit]
Description=Lowen voice-to-text daemon
After=graphical-session.target ydotoold.service
Wants=ydotoold.service

[Service]
Type=simple
ExecStart=$LAUNCHER
Restart=on-failure
RestartSec=5
Environment=PYTHONUNBUFFERED=1
Environment=WAYLAND_DISPLAY=wayland-0
Environment=XDG_RUNTIME_DIR=/run/user/%U
Environment=DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/%U/bus

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
info "Lowen systemd unit installed at $SYSTEMD_USER_DIR/lowen.service"
info "To enable autostart on login: systemctl --user enable lowen"

# ─────────────────────────────────────────────
# Setup complete!
# ─────────────────────────────────────────────
section "Setup Complete!"
echo
echo "  Verify your installation and permissions:"
echo "    lowen --check"
echo
echo "  Quick test (records 5s, transcribes, prints output):"
echo "    lowen --test"
echo
echo "  Launch the background daemon manually:"
echo "    lowen"
echo
echo "  Enable autostart on system boot/login:"
echo "    systemctl --user enable --now lowen"
echo
if [ "$NEEDS_RELOGIN" = true ]; then
    echo -e "  ${RED}⚠  IMPORTANT: You MUST log out and log back in for 'input' group permissions to take effect!${NC}"
else
    echo -e "  ${GREEN}✓ Ready to dictate! Hold Left Shift + Right Shift to speak.${NC}"
fi
echo
