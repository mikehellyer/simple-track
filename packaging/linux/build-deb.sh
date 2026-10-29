#!/usr/bin/env bash
# Packages dist/Simple-Track/ (already built by PyInstaller, onedir mode)
# into a .deb that installs to /opt/simple-track and adds a proper menu
# entry + icon, so it behaves like a native app rather than a dropped
# binary. Uses dpkg-deb directly, which ships with Debian-based distros
# (Pop!_OS included) — no extra tool to install in CI.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BUNDLE="$ROOT/dist/Simple-Track"
VERSION="$(grep -o '__version__ = "[^"]*"' "$ROOT/src/simple_track/__init__.py" | cut -d'"' -f2)"
ARCH="$(dpkg --print-architecture)"
PKG_ROOT="$ROOT/dist/deb-staging"
OUT="$ROOT/dist/simple-track_${VERSION}_${ARCH}.deb"

if [ ! -d "$BUNDLE" ]; then
  echo "error: $BUNDLE not found — run PyInstaller first" >&2
  exit 1
fi

rm -rf "$PKG_ROOT" "$OUT"
mkdir -p "$PKG_ROOT/DEBIAN"
mkdir -p "$PKG_ROOT/opt/simple-track"
mkdir -p "$PKG_ROOT/usr/bin"
mkdir -p "$PKG_ROOT/usr/share/applications"

cp -R "$BUNDLE"/. "$PKG_ROOT/opt/simple-track/"
ln -s /opt/simple-track/Simple-Track "$PKG_ROOT/usr/bin/simple-track"
cp "$ROOT/packaging/linux/simple-track.desktop" "$PKG_ROOT/usr/share/applications/"

for size in 16 32 48 64 128 256 512; do
  dir="$PKG_ROOT/usr/share/icons/hicolor/${size}x${size}/apps"
  mkdir -p "$dir"
  cp "$ROOT/packaging/icons/icon_${size}.png" "$dir/simple-track.png"
done

cat > "$PKG_ROOT/DEBIAN/control" <<EOF
Package: simple-track
Version: $VERSION
Section: misc
Priority: optional
Architecture: $ARCH
Depends: libegl1, libxkbcommon0, libxcb-cursor0, libfontconfig1, libdbus-1-3
Maintainer: Mike Hellyer
Description: Model railway layout designer
 Plan model railway layouts with Peco and Hornby sectional track, in OO
 and N gauge, with a parts list of everything used.
EOF


dpkg-deb --build --root-owner-group "$PKG_ROOT" "$OUT"
rm -rf "$PKG_ROOT"

echo "wrote $OUT"
