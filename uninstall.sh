#!/usr/bin/env bash
# uninstall.sh — Completely uninstall Lowen and remove system hooks

set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${GREEN}[lowen]${NC} $*"; }
warn()  { echo -e "${YELLOW}[warn]${NC}  $*"; }
error() { echo -e "${RED}[error]${NC} $*" >&2; }

echo -e "${RED}──────────────────────────────────────────${NC}"
echo -e "${RED}  Lowen Uninstaller${NC}"
echo -e "${RED}──────────────────────────────────────────${NC}"
echo "This will stop the Lowen service and remove installed launchers and icons."
read -r -p "Continue with uninstall? [y/N] " confirm
if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
    echo "Cancelled."
    exit 0
fi

# Stop and disable systemd service
if systemctl --user is-active --quiet lowen 2>/dev/null; then
    info "Stopping lowen systemd service..."
    systemctl --user stop lowen || true
fi
systemctl --user disable lowen 2>/dev/null || true
rm -f "$HOME/.config/systemd/user/lowen.service"
systemctl --user daemon-reload 2>/dev/null || true
info "Removed lowen systemd service."

# Remove desktop entry and launcher
rm -f "$HOME/.local/bin/lowen"
rm -f "$HOME/.local/share/applications/lowen.desktop"
rm -f "$HOME/.local/share/icons/hicolor/scalable/apps/lowen.svg"
info "Removed launchers and desktop entries."

# Optional configuration removal
if [ -d "$HOME/.config/lowen" ]; then
    read -r -p "Do you want to delete your configuration (~/.config/lowen)? [y/N] " del_conf
    if [[ "$del_conf" =~ ^[Yy]$ ]]; then
        rm -rf "$HOME/.config/lowen"
        info "Removed ~/.config/lowen"
    else
        info "Preserved configuration at ~/.config/lowen"
    fi
fi

info "Lowen has been uninstalled successfully."
