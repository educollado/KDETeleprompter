#!/usr/bin/env bash
set -e

PKG="kdeteleprompter"
VERSION="1.0.2"
ARCH="all"
BUILD_DIR="${PKG}_${VERSION}_${ARCH}"
DEB="${BUILD_DIR}.deb"

echo "Building ${DEB}..."

# Clean previous build
rm -rf "$BUILD_DIR" "$DEB"

# Directory structure
mkdir -p "$BUILD_DIR/DEBIAN"
mkdir -p "$BUILD_DIR/usr/bin"
mkdir -p "$BUILD_DIR/usr/lib/$PKG"
mkdir -p "$BUILD_DIR/usr/share/applications"

# DEBIAN/control
cat > "$BUILD_DIR/DEBIAN/control" << EOF
Package: $PKG
Version: $VERSION
Architecture: $ARCH
Maintainer: Eduardo Collado
Depends: python3 (>= 3.10), python3-pyqt6, python3-pyaudio, python3-numpy, libportaudio2
Section: utils
Priority: optional
Description: Frameless teleprompter for KDE Plasma
 A lightweight, always-on-top teleprompter for Linux / KDE Plasma.
 Built with PyQt6 — no Electron, no browser, no bloat.
 .
 Features smooth 60 fps scrolling, hover-revealed controls, drag to move,
 script editor with file-load support, voice-activated scrolling via microphone,
 and a Catppuccin Mocha colour scheme.
EOF

# Application script
cp kdeteleprompter.py "$BUILD_DIR/usr/lib/$PKG/"

# Wrapper at /usr/bin
cat > "$BUILD_DIR/usr/bin/$PKG" << 'WRAPPER'
#!/bin/sh
exec python3 /usr/lib/kdeteleprompter/kdeteleprompter.py "$@"
WRAPPER

# Desktop entry
cp kdeteleprompter.desktop "$BUILD_DIR/usr/share/applications/"

# Permissions
find "$BUILD_DIR" -type d -exec chmod 755 {} \;
find "$BUILD_DIR" -type f -exec chmod 644 {} \;
chmod 755 "$BUILD_DIR/usr/bin/$PKG"

# Build
dpkg-deb --build --root-owner-group "$BUILD_DIR"

# Clean build dir
rm -rf "$BUILD_DIR"

echo ""
echo "Done: $DEB"
echo "Install with:  sudo dpkg -i $DEB"
