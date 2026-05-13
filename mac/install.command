#!/bin/bash
# ============================================================
#  Hawker — macOS installer
#  Double-click this file in Finder to run, or:
#    bash mac/install.command
# ============================================================

set -euo pipefail

# Always run from the repo root so relative paths work
cd "$(dirname "$0")/.."

INSTALL_DIR="$HOME/.screenlog"
PLIST_LABEL="com.mendelrosenberg.screenlog"
PLIST_PATH="$HOME/Library/LaunchAgents/$PLIST_LABEL.plist"
SOURCE_DIR="$(pwd)/log_hawk"
ENV_FILE="$INSTALL_DIR/hawker.env"

bold()  { printf '\033[1m%s\033[0m\n' "$*"; }
green() { printf '\033[32m%s\033[0m\n' "$*"; }
red()   { printf '\033[31m%s\033[0m\n' "$*"; }
ask()   { printf '\033[1m%s\033[0m ' "$*"; read -r REPLY; }

echo
bold "=============================="
bold " Hawker Installer (macOS)"
bold "=============================="
echo

# ── 1. Python check ──────────────────────────────────────────

PYTHON=""
for candidate in python3 python; do
    if command -v "$candidate" &>/dev/null; then
        ver=$("$candidate" -c 'import sys; print(sys.version_info >= (3, 9))')
        if [ "$ver" = "True" ]; then
            PYTHON="$candidate"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    red "Python 3.9+ is required but not found."
    echo "Install it from https://www.python.org/downloads/ or via Homebrew:"
    echo "  brew install python"
    exit 1
fi

PY_VER=$("$PYTHON" --version 2>&1)
green "Found $PY_VER"

# ── 2. Install Python dependencies ───────────────────────────

bold "Installing Python dependencies..."
"$PYTHON" -m pip install --quiet --upgrade \
    rumps \
    pillow \
    pyobjc-framework-Quartz \
    pyobjc-framework-Vision
green "Dependencies installed."

# ── 3. Create install directory and copy files ────────────────

bold "Installing files to $INSTALL_DIR ..."
mkdir -p "$INSTALL_DIR/docs/screenshots"

cp "$SOURCE_DIR/daemon.py"  "$INSTALL_DIR/daemon.py"
cp "$SOURCE_DIR/menubar.py" "$INSTALL_DIR/menubar.py"

# Copy default config if one doesn't already exist
if [ ! -f "$INSTALL_DIR/config.json" ]; then
    cp "$SOURCE_DIR/config.json" "$INSTALL_DIR/config.json"
fi
green "Files copied."

# ── 4. API credentials ───────────────────────────────────────

if [ -f "$ENV_FILE" ]; then
    green "hawker.env already exists — skipping credential setup."
else
    echo
    bold "Hawker API configuration"
    echo "Leave blank to use the default Hawker instance."
    echo

    ask "API URL [https://hawker-flax.vercel.app]:"
    API_URL="${REPLY:-https://hawker-flax.vercel.app}"

    ask "API Key:"
    API_KEY="$REPLY"

    cat > "$ENV_FILE" <<EOF
HAWKER_API_URL=$API_URL
HAWKER_API_KEY=$API_KEY
EOF
    green "hawker.env written."
fi

# ── 5. LaunchAgent plist ─────────────────────────────────────

bold "Setting up LaunchAgent..."
mkdir -p "$HOME/Library/LaunchAgents"

PYTHON_BIN=$(which "$PYTHON")

cat > "$PLIST_PATH" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$PLIST_LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PYTHON_BIN</string>
    <string>$INSTALL_DIR/menubar.py</string>
  </array>
  <key>WorkingDirectory</key>
  <string>$INSTALL_DIR</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>LimitLoadToSessionType</key>
  <string>Aqua</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin</string>
    <key>HOME</key>
    <string>$HOME</string>
  </dict>
</dict>
</plist>
EOF
green "Plist written to $PLIST_PATH"

# ── 6. Load LaunchAgent ──────────────────────────────────────

# Unload any previous instance first
launchctl unload "$PLIST_PATH" 2>/dev/null || true

ask "Start Hawker now and enable launch-at-login? (y/n):"
if [[ "$REPLY" =~ ^[Yy] ]]; then
    launchctl load "$PLIST_PATH"
    green "Hawker is running. Look for (o,o) in your menu bar."
else
    echo "To start manually:"
    echo "  launchctl load \"$PLIST_PATH\""
    echo "Or:"
    echo "  $PYTHON \"$INSTALL_DIR/menubar.py\""
fi

echo
bold "Installation complete!"
echo "  Install dir : $INSTALL_DIR"
echo "  Config      : $INSTALL_DIR/config.json"
echo "  Credentials : $ENV_FILE"
echo "  Log         : $INSTALL_DIR/daemon.log"
echo "  Screenshots : $INSTALL_DIR/docs/screenshots/"
echo
echo "To uninstall, run: bash mac/uninstall.sh"
echo
