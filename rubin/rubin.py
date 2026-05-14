#!/usr/bin/env python3
"""
Rick Rubin Tracker — menu bar countdown to becoming Rick Rubin.

Run:  python3 rubin/rubin.py
      (from the hawker project root, or any directory)

Two trajectories:
  ⚡ Exponential  — creative work compounds; 5-year base
  📈 Hockey stick — corporate work (email/sales) builds toward a $100M exit; 17-year base
  🧠 Brain drain  — social media / YouTube burns time proportionally from both buckets
"""

import json
import math
import os
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import rumps

_HERE      = Path(__file__).resolve().parent
_DATA_FILE = _HERE / "rubin_data.json"

POLL_INTERVAL = 30   # seconds between activity checks
IDLE_THRESHOLD = 120  # seconds; if idle longer than this, don't count

# ── App categories ────────────────────────────────────────────────────────────

CORPORATE_APPS = {
    "Mail", "Microsoft Outlook", "Outlook", "Spark", "Airmail", "Mimestream",
    "Zoom", "zoom.us", "Loom",
    "Dialpad", "RingCentral", "Gong", "Otter",
    "Microsoft Teams",
}

CREATIVE_APPS = {
    "Xcode", "Simulator",
    "Visual Studio Code", "Code", "Cursor", "Zed", "Nova",
    "Terminal", "iTerm2", "iTerm", "Warp", "Hyper",
    "Figma", "Sketch", "Adobe XD", "Illustrator", "Photoshop",
    "Affinity Designer", "Affinity Photo",
    "Logic Pro", "GarageBand",
    "Final Cut Pro", "DaVinci Resolve",
    "Instruments", "Android Studio",
    "BBEdit", "Sublime Text", "TextMate",
    "Blender",
    "Processing",
}

CORPORATE_DOMAINS = {
    "mail.google.com", "outlook.live.com", "outlook.office.com",
    "app.hubspot.com", "salesforce.com", "crm.salesforce.com",
    "app.apollo.io", "app.salesloft.com", "app.outreach.io",
    "calendar.google.com", "meet.google.com",
}

BRAIN_DRAIN_DOMAINS = {
    "reddit.com", "old.reddit.com",
    "x.com", "twitter.com",
    "youtube.com", "youtu.be",
    "instagram.com",
    "facebook.com", "fb.com",
    "tiktok.com",
    "linkedin.com",
    "twitch.tv",
    "tumblr.com", "pinterest.com",
    "bsky.app", "threads.net",
    "snapchat.com",
    "news.ycombinator.com",
}

# ── Data persistence ──────────────────────────────────────────────────────────

def _load_data():
    try:
        return json.loads(_DATA_FILE.read_text())
    except Exception:
        return {
            "creative_seconds": 0,
            "corporate_seconds": 0,
            "brain_drain_seconds": 0,
            "last_updated": None,
        }


def _save_data(data):
    data["last_updated"] = datetime.now().isoformat()
    _DATA_FILE.write_text(json.dumps(data, indent=2))


# ── Activity detection ────────────────────────────────────────────────────────

def get_idle_seconds():
    try:
        result = subprocess.run(
            ["ioreg", "-c", "IOHIDSystem"],
            capture_output=True, text=True, timeout=5,
        )
        for line in result.stdout.splitlines():
            if "HIDIdleTime" in line:
                ns = int(line.split("=")[-1].strip())
                return ns / 1_000_000_000
    except Exception:
        pass
    return 0.0


def get_frontmost_app():
    try:
        result = subprocess.run(
            ["osascript", "-e",
             "tell application \"System Events\" to get name of first process where frontmost is true"],
            capture_output=True, text=True, timeout=3,
        )
        return result.stdout.strip()
    except Exception:
        return None


def get_active_browser_url():
    scripts = {
        "Google Chrome": (
            'if application "Google Chrome" is running then\n'
            'tell application "Google Chrome" to return URL of active tab of front window\n'
            'end if\nreturn ""'
        ),
        "Safari": (
            'if application "Safari" is running then\n'
            'tell application "Safari" to return URL of current tab of front window\n'
            'end if\nreturn ""'
        ),
        "Microsoft Edge": (
            'if application "Microsoft Edge" is running then\n'
            'tell application "Microsoft Edge" to return URL of active tab of front window\n'
            'end if\nreturn ""'
        ),
    }
    for script in scripts.values():
        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True, text=True, timeout=5,
            )
            url = result.stdout.strip()
            if url.startswith("http"):
                return url
        except Exception:
            pass
    return None


def _host(url):
    h = urlparse(url).netloc.lower()
    return h[4:] if h.startswith("www.") else h


def classify_activity(app_name, browser_url):
    """Returns 'corporate', 'creative', 'brain_drain', or 'neutral'."""
    if browser_url:
        h = _host(browser_url)
        for d in BRAIN_DRAIN_DOMAINS:
            if h == d or h.endswith("." + d):
                return "brain_drain"
        for d in CORPORATE_DOMAINS:
            if h == d or h.endswith("." + d):
                return "corporate"

    if app_name:
        if app_name in CORPORATE_APPS:
            return "corporate"
        if app_name in CREATIVE_APPS:
            return "creative"

    return "neutral"


# ── Rick Rubin score ──────────────────────────────────────────────────────────

def compute_rubin_score(creative_secs, corporate_secs, brain_drain_secs):
    """
    Returns (years_remaining: float, trajectory: str).

    Brain drain eats proportionally from whichever buckets have been filled.
    Creative path: exponential decay — 5-year base, halves every 2000 effective hours.
    Corporate path: hockey stick — 17-year base (15yr grind + $100M exit + 2yr Rubin).
                    Progress is slow until ~4000h then accelerates sharply.
    """
    c_hrs  = creative_secs   / 3600
    co_hrs = corporate_secs  / 3600
    bd_hrs = brain_drain_secs / 3600

    total = c_hrs + co_hrs
    if total > 0:
        r = c_hrs / total
        eff_creative  = max(0.0, c_hrs  - bd_hrs * r)
        eff_corporate = max(0.0, co_hrs - bd_hrs * (1.0 - r))
    else:
        eff_creative = eff_corporate = 0.0

    if eff_creative >= eff_corporate:
        trajectory    = "exponential"
        years_left    = 5.0 * math.exp(-eff_creative / 2000.0)
    else:
        trajectory    = "hockey_stick"
        threshold     = 4000.0
        progress      = (eff_corporate ** 2) / (eff_corporate ** 2 + threshold ** 2)
        years_left    = 17.0 * (1.0 - progress)

    return max(0.0, years_left), trajectory


def format_countdown(years):
    if years <= 0:
        return "NOW"
    days = int(years * 365.25)
    y, rem = divmod(days, 365)
    m = rem // 30
    if y == 0:
        return f"{m}m"
    if m == 0:
        return f"{y}y"
    return f"{y}y {m}m"


def fmt_hours(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    if h == 0:
        return f"{m}m"
    return f"{h}h {m}m"


# ── Menu bar app ──────────────────────────────────────────────────────────────

class RubinApp(rumps.App):

    def __init__(self):
        super().__init__("Rubin", quit_button=None)
        self._lock  = threading.Lock()
        self._data  = _load_data()
        self._stop  = threading.Event()

        self.score_item    = rumps.MenuItem("🎸  — to full Rubin")
        self.traj_item     = rumps.MenuItem("Trajectory: —")
        self.sep1          = None
        self.creative_item = rumps.MenuItem("⚡ Creative:   0m")
        self.corp_item     = rumps.MenuItem("📈 Corporate:  0m")
        self.drain_item    = rumps.MenuItem("🧠 Brain drain: 0m")

        self.menu = [
            self.score_item,
            None,
            self.traj_item,
            self.creative_item,
            self.corp_item,
            self.drain_item,
            None,
            rumps.MenuItem("Reset All Data", callback=self.on_reset),
            None,
            rumps.MenuItem("Quit Rubin Tracker", callback=self.on_quit),
        ]

        self._refresh_display()
        threading.Thread(target=self._loop, daemon=True).start()

    # ── background loop ───────────────────────────────────────────────────────

    def _loop(self):
        while not self._stop.is_set():
            if get_idle_seconds() < IDLE_THRESHOLD:
                app_name = get_frontmost_app()
                url      = get_active_browser_url()
                category = classify_activity(app_name, url)

                with self._lock:
                    if category != "neutral":
                        self._data[f"{category}_seconds"] += POLL_INTERVAL
                    _save_data(self._data)
                    data = dict(self._data)

                self._refresh_display(data)

            self._stop.wait(POLL_INTERVAL)

    # ── display ───────────────────────────────────────────────────────────────

    def _refresh_display(self, data=None):
        if data is None:
            with self._lock:
                data = dict(self._data)

        years, traj = compute_rubin_score(
            data["creative_seconds"],
            data["corporate_seconds"],
            data["brain_drain_seconds"],
        )
        label = format_countdown(years)

        icon = "⚡" if traj == "exponential" else "📈"
        self.title = f"{icon} {label} → Rubin"

        traj_label = "Exponential (5yr base)" if traj == "exponential" else "Hockey stick (17yr base)"
        self.score_item.title    = f"🎸  {label} to full Rubin"
        self.traj_item.title     = f"Trajectory: {traj_label}"
        self.creative_item.title = f"⚡ Creative:    {fmt_hours(data['creative_seconds'])}"
        self.corp_item.title     = f"📈 Corporate:   {fmt_hours(data['corporate_seconds'])}"
        self.drain_item.title    = f"🧠 Brain drain: {fmt_hours(data['brain_drain_seconds'])}"

    # ── callbacks ─────────────────────────────────────────────────────────────

    def on_reset(self, _):
        if rumps.alert("Reset Rubin Tracker",
                       "Clear all time data and start from scratch?",
                       ok="Reset", cancel="Cancel"):
            with self._lock:
                self._data = {
                    "creative_seconds": 0,
                    "corporate_seconds": 0,
                    "brain_drain_seconds": 0,
                    "last_updated": None,
                }
                _save_data(self._data)
            self._refresh_display()

    def on_quit(self, _):
        self._stop.set()
        rumps.quit_application()


if __name__ == "__main__":
    RubinApp().run()
