#!/usr/bin/env bash
# uninstall.sh — Completely uninstall Flinx and remove system hooks

set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${GREEN}[flinx]${NC} $*"; }
warn()  { echo -e "${YELLOW}[warn]${NC}  $*"; }
error() { echo -e "${RED}[error]${NC} $*" >&2; }

echo -e "${RED}──────────────────────────────────────────${NC}"
echo -e "${RED}  Flinx Uninstaller${NC}"
echo -e "${RED}──────────────────────────────────────────${NC}"
echo "This will stop the Flinx service and remove installed launchers and icons."
read -r -p "Continue with uninstall? [y/N] " confirm
if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
    echo "Cancelled."
    exit 0
fi

# Stop and disable systemd service (flinx and legacy lowen)
for s in flinx lowen; do
    if systemctl --user is-active --quiet "$s" 2>/dev/null; then
        info "Stopping $s systemd service..."
        systemctl --user stop "$s" || true
    fi
    systemctl --user disable "$s" 2>/dev/null || true
    rm -f "$HOME/.config/systemd/user/$s.service"
done
systemctl --user daemon-reload 2>/dev/null || true
info "Removed systemd services."

# Remove desktop entry and launcher
rm -f "$HOME/.local/bin/flinx" "$HOME/.local/bin/lowen"
rm -f "$HOME/.local/share/applications/flinx.desktop" "$HOME/.local/share/applications/lowen.desktop"
rm -f "$HOME/.local/share/icons/hicolor/scalable/apps/flinx.svg" "$HOME/.local/share/icons/hicolor/scalable/apps/lowen.svg"
info "Removed launchers and desktop entries."

# Optional configuration removal
for c in "$HOME/.config/flinx" "$HOME/.config/lowen"; do
    if [ -d "$c" ]; then
        read -r -p "Do you want to delete your configuration ($c)? [y/N] " del_conf
        if [[ "$del_conf" =~ ^[Yy]$ ]]; then
            rm -rf "$c"
            info "Removed $c"
        else
            info "Preserved configuration at $c"
        fi
    fi
done

info "Flinx has been uninstalled successfully."
