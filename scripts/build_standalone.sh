#!/usr/bin/env bash
# scripts/build_standalone.sh — Build standalone Flinx executable and AppImage
#
# Generates a self-contained binary distribution of Flinx with all Python dependencies,
# PyQt6 runtime, evdev, and sound assets bundled.
#
# Usage:
#   bash scripts/build_standalone.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_PYTHON="$ROOT_DIR/.venv/bin/python"
VENV_PIP="$ROOT_DIR/.venv/bin/pip"
BUILD_DIR="$ROOT_DIR/build"
DIST_DIR="$ROOT_DIR/dist"

echo "========================================================"
echo "  Flinx — Standalone Binary & Package Builder"
echo "========================================================"

# 1. Ensure PyInstaller is installed
if ! "$VENV_PYTHON" -c "import PyInstaller" &>/dev/null; then
    echo "[flinx-build] Installing PyInstaller..."
    "$VENV_PIP" install pyinstaller --quiet
fi

# 2. Clean previous build artifacts
echo "[flinx-build] Cleaning previous build artifacts..."
rm -rf "$BUILD_DIR" "$DIST_DIR" "$ROOT_DIR/flinx.spec"

# 3. Build standalone executable using PyInstaller
echo "[flinx-build] Compiling standalone Flinx binary with PyInstaller..."
"$VENV_PYTHON" -m PyInstaller \
    --name flinx \
    --onedir \
    --windowed \
    --clean \
    --noconfirm \
    --add-data "$ROOT_DIR/resources:resources" \
    --hidden-import=flinx \
    --hidden-import=flinx.config \
    --hidden-import=flinx.core \
    --hidden-import=flinx.hotkey \
    --hidden-import=flinx.recorder \
    --hidden-import=flinx.transcriber \
    --hidden-import=flinx.clipboard \
    --hidden-import=flinx.generate_sounds \
    --hidden-import=ui.control_center \
    --hidden-import=ui.pill \
    --hidden-import=ui.tray \
    --hidden-import=ui.animations \
    --hidden-import=sounddevice \
    --hidden-import=scipy.io.wavfile \
    --hidden-import=evdev \
    --hidden-import=groq \
    "$ROOT_DIR/main.py"

echo "[flinx-build] PyInstaller build complete. Output is in $DIST_DIR/flinx"

# 4. Optional: Create AppImage if appimagetool is available
if command -v appimagetool &>/dev/null; then
    echo "[flinx-build] appimagetool detected! Creating universal AppImage..."
    APPDIR="$BUILD_DIR/Flinx.AppDir"
    mkdir -p "$APPDIR/usr/bin"
    mkdir -p "$APPDIR/usr/share/icons/hicolor/scalable/apps"
    mkdir -p "$APPDIR/usr/share/applications"

    # Copy files
    cp -r "$DIST_DIR/flinx/"* "$APPDIR/usr/bin/"
    cp "$ROOT_DIR/resources/icon.svg" "$APPDIR/usr/share/icons/hicolor/scalable/apps/flinx.svg"
    cp "$ROOT_DIR/resources/icon.svg" "$APPDIR/flinx.svg"

    # AppRun
    cat > "$APPDIR/AppRun" <<'EOF'
#!/bin/sh
SELF=$(readlink -f "$0")
HERE=${SELF%/*}
export PATH="${HERE}/usr/bin:${PATH}"
export LD_LIBRARY_PATH="${HERE}/usr/bin:${LD_LIBRARY_PATH}"
exec "${HERE}/usr/bin/flinx" "$@"
EOF
    chmod +x "$APPDIR/AppRun"

    # Desktop entry
    cat > "$APPDIR/flinx.desktop" <<'EOF'
[Desktop Entry]
Name=Flinx
GenericName=Voice-to-Text Dictation
Comment=Wayland voice-to-text dictation with glassmorphic pill overlay
Exec=flinx
Icon=flinx
Terminal=false
Type=Application
Categories=Utility;Accessibility;AudioVideo;
Keywords=voice;dictation;speech;whisper;groq;transcription;flinx;
EOF
    cp "$APPDIR/flinx.desktop" "$APPDIR/usr/share/applications/flinx.desktop"

    appimagetool "$APPDIR" "$DIST_DIR/Flinx-x86_64.AppImage"
    echo "[flinx-build] AppImage created at $DIST_DIR/Flinx-x86_64.AppImage"
else
    echo "[flinx-build] Note: appimagetool not found on host. The standalone directory is ready at: $DIST_DIR/flinx"
    echo "              (To generate an AppImage, install appimagetool from https://appimage.github.io)"
fi

echo "========================================================"
echo "  Build successful! Standalone binary ready in:"
echo "  $DIST_DIR/flinx/flinx"
echo "========================================================"
