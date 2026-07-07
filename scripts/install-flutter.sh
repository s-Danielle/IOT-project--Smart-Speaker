#!/bin/bash
# Install Flutter SDK on Arch-based Linux (CachyOS, Manjaro, EndeavourOS, etc.)
# Installs from official git source instead of the unreliable AUR package

set -e

FLUTTER_DIR="/opt/flutter"
SHELL_RC="$HOME/.zshrc"

# Detect shell rc file
if [ -n "$BASH_VERSION" ] && [ -f "$HOME/.bashrc" ]; then
    SHELL_RC="$HOME/.bashrc"
fi

echo "=== Flutter Installer (Arch Linux) ==="
echo ""

# 1. Install system dependencies
echo "[1/4] Installing system dependencies..."
sudo pacman -S --needed --noconfirm clang cmake ninja pkg-config gtk3

# 2. Clone Flutter
echo ""
echo "[2/4] Cloning Flutter stable into $FLUTTER_DIR..."
if [ -d "$FLUTTER_DIR" ]; then
    echo "  $FLUTTER_DIR already exists — skipping clone."
    echo "  To reinstall, run: sudo rm -rf $FLUTTER_DIR and re-run this script."
else
    sudo git clone https://github.com/flutter/flutter.git -b stable "$FLUTTER_DIR"
fi

# 3. Fix ownership so flutter/pub commands don't need sudo
echo ""
echo "[3/4] Setting ownership of $FLUTTER_DIR to $USER..."
sudo chown -R "$USER":"$USER" "$FLUTTER_DIR"

# 4. Add to PATH
echo ""
echo "[4/4] Adding Flutter to PATH in $SHELL_RC..."
EXPORT_LINE='export PATH="/opt/flutter/bin:$PATH"'
if grep -qF '/opt/flutter/bin' "$SHELL_RC" 2>/dev/null; then
    echo "  PATH entry already present in $SHELL_RC — skipping."
else
    echo "" >> "$SHELL_RC"
    echo "# Flutter SDK" >> "$SHELL_RC"
    echo "$EXPORT_LINE" >> "$SHELL_RC"
    echo "  Added to $SHELL_RC."
fi

# Apply PATH for the rest of this session
export PATH="/opt/flutter/bin:$PATH"

echo ""
echo "=== Running flutter doctor ==="
echo ""
flutter doctor

echo ""
echo "=== Done! ==="
echo ""
echo "Reload your shell or run:  source $SHELL_RC"
echo "Then verify with:          flutter doctor"
echo ""
echo "To update Flutter later:   flutter upgrade"
