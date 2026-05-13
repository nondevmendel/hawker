#!/bin/bash
# ============================================================
#  Hawker — macOS .app builder
#  Produces mac/dist/Hawker.app (self-contained, no Python req)
#
#  Run from the repo root:
#    bash mac/build.sh
#
#  Optional: also creates a distributable .dmg
#    bash mac/build.sh --dmg
# ============================================================

set -euo pipefail
cd "$(dirname "$0")/.."          # repo root

MAKE_DMG=false
[[ "${1:-}" == "--dmg" ]] && MAKE_DMG=true

SOURCE_DIR="log_hawk"
BUILD_DIR="mac/_build"
DIST_DIR="mac/dist"
APP_NAME="Hawker"

bold()  { printf '\033[1m%s\033[0m\n' "$*"; }
green() { printf '\033[32m%s\033[0m\n' "$*"; }

# ── 0. Python ────────────────────────────────────────────────

PYTHON=""
for c in python3 python; do
    if command -v "$c" &>/dev/null && "$c" -c 'import sys; sys.exit(sys.version_info < (3,9))' 2>/dev/null; then
        PYTHON="$c"
        break
    fi
done
[ -z "$PYTHON" ] && { echo "Python 3.9+ required."; exit 1; }
bold "Using $($PYTHON --version)"

# ── 1. Dependencies ──────────────────────────────────────────

bold "[1/4] Installing build dependencies..."
"$PYTHON" -m pip install --quiet --upgrade \
    py2app rumps pillow \
    pyobjc-framework-Quartz \
    pyobjc-framework-Vision

# ── 2. Prepare build staging directory ───────────────────────

bold "[2/4] Staging source files..."
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"

cp "$SOURCE_DIR/menubar.py" "$BUILD_DIR/menubar.py"
cp "$SOURCE_DIR/daemon.py"  "$BUILD_DIR/daemon.py"
cp "$SOURCE_DIR/config.json" "$BUILD_DIR/config.json"

# ── 3. Generate icon.icns from emoji if none supplied ─────────

ICNS="mac/icon.icns"
if [ ! -f "$ICNS" ]; then
    bold "Generating icon.icns from owl emoji..."
    "$PYTHON" - <<'PYEOF'
import subprocess, sys, tempfile, os
from pathlib import Path
try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    subprocess.run([sys.executable, "-m", "pip", "install", "pillow"], check=True)
    from PIL import Image, ImageDraw, ImageFont

sizes = [16, 32, 64, 128, 256, 512, 1024]
iconset = Path("mac/Hawker.iconset")
iconset.mkdir(exist_ok=True)

for sz in sizes:
    img = Image.new("RGBA", (sz, sz), (0, 0, 0, 0))
    d   = ImageDraw.Draw(img)
    d.ellipse([sz//16, sz//16, sz - sz//16, sz - sz//16], fill=(34, 197, 94))
    # Eyes
    ew = max(sz // 8, 4)
    for ex in (sz // 4, sz * 5 // 8):
        d.ellipse([ex, sz//3, ex + ew, sz//2], fill="white")
    for ex in (sz // 4 + ew // 4, sz * 5 // 8 + ew // 4):
        d.ellipse([ex, sz//3 + ew//4, ex + ew//2, sz//2 - ew//4], fill="black")
    # Beak
    cx = sz // 2
    bh = max(sz // 10, 2)
    d.polygon([(cx - bh, sz * 55 // 100), (cx + bh, sz * 55 // 100), (cx, sz * 65 // 100)],
              fill=(255, 200, 0))
    img.save(str(iconset / f"icon_{sz}x{sz}.png"))
    if sz <= 512:
        img2 = img.resize((sz * 2, sz * 2), Image.LANCZOS)
        img2.save(str(iconset / f"icon_{sz}x{sz}@2x.png"))

subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", "mac/icon.icns"], check=True)
iconset_path = Path("mac/Hawker.iconset")
import shutil; shutil.rmtree(str(iconset_path))
print("icon.icns created")
PYEOF
fi

# ── 4. Build .app with py2app ────────────────────────────────

bold "[3/4] Building Hawker.app with py2app..."
rm -rf "$BUILD_DIR/build" "$BUILD_DIR/dist"

cd "$BUILD_DIR"
"$PYTHON" "../../mac/setup.py" py2app --dist-dir "../../$DIST_DIR" 2>&1 | grep -v "^$"
cd - >/dev/null

green "[3/4] Hawker.app built at $DIST_DIR/$APP_NAME.app"

# ── 5. Optional: create .dmg ─────────────────────────────────

if $MAKE_DMG; then
    bold "[4/4] Creating Hawker.dmg..."
    DMG_PATH="mac/HawkerInstall.dmg"
    rm -f "$DMG_PATH"

    # Temp folder with app + symlink to /Applications for drag-install
    STAGING=$(mktemp -d)
    cp -R "$DIST_DIR/$APP_NAME.app" "$STAGING/"
    ln -s /Applications "$STAGING/Applications"

    hdiutil create \
        -volname "Hawker" \
        -srcfolder "$STAGING" \
        -ov -format UDZO \
        "$DMG_PATH"

    rm -rf "$STAGING"
    green "[4/4] Installer disk image: $DMG_PATH"
else
    bold "[4/4] Skipped .dmg (pass --dmg to create one)"
fi

echo
bold "Done."
echo "  App        : $DIST_DIR/$APP_NAME.app"
echo "  To install : cp -R $DIST_DIR/$APP_NAME.app /Applications/"
$MAKE_DMG && echo "  Installer  : mac/HawkerInstall.dmg"
echo
echo "On first launch the OS will ask for Screen Recording and Automation"
echo "permissions in System Settings → Privacy & Security."
echo
