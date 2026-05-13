#!/bin/bash
# ============================================================
#  Hawker — macOS uninstaller
#  Run: bash mac/uninstall.sh
# ============================================================

set -euo pipefail

INSTALL_DIR="$HOME/.screenlog"
PLIST_LABEL="com.mendelrosenberg.screenlog"
PLIST_PATH="$HOME/Library/LaunchAgents/$PLIST_LABEL.plist"

bold()  { printf '\033[1m%s\033[0m\n' "$*"; }
green() { printf '\033[32m%s\033[0m\n' "$*"; }
red()   { printf '\033[31m%s\033[0m\n' "$*"; }
ask()   { printf '\033[1m%s\033[0m ' "$*"; read -r REPLY; }

echo
bold "=============================="
bold " Hawker Uninstaller (macOS)"
bold "=============================="
echo

# Stop and remove LaunchAgent
if [ -f "$PLIST_PATH" ]; then
    bold "Stopping Hawker..."
    launchctl unload "$PLIST_PATH" 2>/dev/null || true
    rm -f "$PLIST_PATH"
    green "LaunchAgent removed."
else
    echo "LaunchAgent not found — already removed."
fi

# Kill any running process
pkill -f "$INSTALL_DIR/menubar.py" 2>/dev/null || true

# Optionally remove screenshots and data
ask "Delete all screenshots and data in $INSTALL_DIR? (y/n):"
if [[ "$REPLY" =~ ^[Yy] ]]; then
    rm -rf "$INSTALL_DIR"
    green "Data directory removed."
else
    echo "Data kept at $INSTALL_DIR"
fi

green "Hawker uninstalled."
echo
