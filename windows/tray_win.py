#!/usr/bin/env python3
"""
Hawker system tray app — Windows version.
Replaces macOS rumps/AppKit/launchctl with pystray + winreg.

Run: pythonw tray_win.py   (pythonw suppresses the console window)
     python  tray_win.py   (shows a console window — useful for debugging)
"""

import base64
import json
import os
import random
import subprocess
import sys
import threading
import time
import urllib.request
import urllib.error
import webbrowser
import winreg
from pathlib import Path

try:
    import pystray
    from PIL import Image, ImageDraw
except ImportError:
    subprocess.run([sys.executable, "-m", "pip", "install", "pystray", "pillow"], check=True)
    import pystray
    from PIL import Image, ImageDraw

# daemon_win.py must be in the same directory
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
import daemon_win as _d

_REG_PATH  = r"Software\Microsoft\Windows\CurrentVersion\Run"
_REG_VALUE = "Hawker"
_ENV_FILE  = _d.REPO_DIR / "hawker.env"


# ── Hawker API ───────────────────────────────────────────────────────────────

def _load_hawker_env():
    cfg = {}
    if _ENV_FILE.exists():
        for line in _ENV_FILE.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                cfg[k.strip()] = v.strip()
    cfg.setdefault("HAWKER_API_URL", os.environ.get("HAWKER_API_URL", ""))
    cfg.setdefault("HAWKER_API_KEY", os.environ.get("HAWKER_API_KEY", ""))
    return cfg


def _hawker_upload(stem, jpg_path, domain):
    cfg = _load_hawker_env()
    url  = cfg.get("HAWKER_API_URL", "").rstrip("/")
    key  = cfg.get("HAWKER_API_KEY", "")
    if not url or not key:
        _d.log("Hawker upload skipped — HAWKER_API_URL/KEY not configured")
        return False
    try:
        img_b64 = base64.b64encode(Path(jpg_path).read_bytes()).decode()
        payload = json.dumps({
            "stem":        stem,
            "domain":      domain,
            "imageBase64": img_b64,
        }).encode()
        req = urllib.request.Request(
            url + "/api/upload",
            data=payload,
            headers={"Content-Type": "application/json", "x-api-key": key},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read())
            if body.get("ok"):
                _d.log(f"Uploaded to Hawker: {body.get('url', '')[:60]}")
                return True
            _d.log(f"Hawker upload error: {body}")
            return False
    except Exception as exc:
        _d.log(f"Hawker upload failed: {exc}")
        return False


# ── Windows startup (Registry) ───────────────────────────────────────────────

def _startup_cmd():
    exe = Path(sys.executable)
    script = Path(__file__).resolve()
    # Use pythonw.exe so no console window appears at login
    pythonw = exe.parent / "pythonw.exe"
    runner  = pythonw if pythonw.exists() else exe
    return f'"{runner}" "{script}"'


def is_startup_enabled():
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REG_PATH, 0, winreg.KEY_READ)
        try:
            winreg.QueryValueEx(key, _REG_VALUE)
            return True
        except FileNotFoundError:
            return False
        finally:
            key.Close()
    except Exception:
        return False


def _enable_startup():
    key = winreg.OpenKey(
        winreg.HKEY_CURRENT_USER, _REG_PATH, 0, winreg.KEY_SET_VALUE
    )
    winreg.SetValueEx(key, _REG_VALUE, 0, winreg.REG_SZ, _startup_cmd())
    key.Close()


def _disable_startup():
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _REG_PATH, 0, winreg.KEY_SET_VALUE
        )
        winreg.DeleteValue(key, _REG_VALUE)
        key.Close()
    except Exception:
        pass


# ── Singleton (named mutex) ──────────────────────────────────────────────────

def _acquire_singleton():
    try:
        import ctypes
        import ctypes.wintypes
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        h = kernel32.CreateMutexW(None, True, "HawkerAppMutex")
        if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
            print("Hawker is already running.")
            sys.exit(0)
        return h  # keep reference so the mutex stays alive
    except Exception:
        pass
    return None


# ── Icon images ──────────────────────────────────────────────────────────────

def _make_icon(recording: bool) -> Image.Image:
    size = 64
    img  = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d    = ImageDraw.Draw(img)
    color = (34, 197, 94) if recording else (239, 68, 68)
    # Body circle
    d.ellipse([4, 4, size - 4, size - 4], fill=color)
    # Eyes
    for ex in (14, 38):
        d.ellipse([ex, 20, ex + 12, 32], fill="white")
    for ex in (17, 41):
        d.ellipse([ex, 23, ex + 6, 29], fill="black")
    # Beak
    d.polygon([(28, 34), (36, 34), (32, 40)], fill=(255, 200, 0))
    return img


# ════════════════════════════════════════════════════════════════════════════
# Tray app

class HawkerTray:

    def __init__(self):
        self._recording  = True
        self._stop_evt   = threading.Event()
        self._thread     = None
        self._icon       = None
        self._mutex_ref  = _acquire_singleton()

        self._icon = pystray.Icon(
            "hawker",
            _make_icon(True),
            "Hawker — Recording",
            menu=self._build_menu(),
        )

    # ── menu ────────────────────────────────────────────────────────────────

    def _build_menu(self):
        return pystray.Menu(
            pystray.MenuItem(
                lambda item: "● Recording" if self._recording else "○ Paused",
                None,
                enabled=False,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                lambda item: "Pause Recording" if self._recording else "Resume Recording",
                self._on_toggle,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Open Dashboard", self._on_dashboard),
            pystray.MenuItem("Open Log File",  self._on_logfile),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Launch at Startup",
                self._on_startup,
                checked=lambda item: is_startup_enabled(),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit Hawker", self._on_quit),
        )

    # ── daemon loop ──────────────────────────────────────────────────────────

    def _start_loop(self):
        self._stop_evt.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def _run_loop(self):
        last_shot_time = 0.0
        next_shot_gap  = random.randint(_d.MIN_SHOT_GAP, _d.MAX_SHOT_GAP)
        last_domain    = None

        while not self._stop_evt.is_set():
            try:
                ignored = _d.load_ignored_urls()
                url     = _d.get_active_browser_url()

                if url:
                    on_social     = _d.is_social_media(url)
                    ignored_match = _d.is_ignored(url, ignored)
                    sensitive     = _d.title_looks_sensitive(url)
                    domain        = _d.extract_domain(url) if on_social else None
                    now           = time.time()

                    if on_social and not ignored_match and not sensitive:
                        if domain != last_domain:
                            _d.record_visit(domain)
                        last_domain = domain
                    else:
                        last_domain = None

                    if (on_social and not ignored_match and not sensitive
                            and domain == last_domain):
                        _d.add_domain_time(domain, _d.POLL_INTERVAL)

                    if (on_social and not ignored_match and not sensitive
                            and (now - last_shot_time) >= next_shot_gap):
                        _d.log(f"On social media: {url[:80]}")
                        result = _d.take_screenshot(url, domain)
                        if result:
                            file_path, stem = result
                            _d.cleanup_old()
                            _hawker_upload(stem, file_path, domain)
                            last_shot_time = time.time()
                            next_shot_gap  = random.randint(_d.MIN_SHOT_GAP, _d.MAX_SHOT_GAP)
                            _d.log(f"Next shot in {next_shot_gap // 60}m {next_shot_gap % 60}s")
                else:
                    last_domain = None

            except Exception as exc:
                _d.log(f"tray loop error: {exc}")

            self._stop_evt.wait(_d.POLL_INTERVAL)

    # ── callbacks ────────────────────────────────────────────────────────────

    def _on_toggle(self, icon, item):
        if self._recording:
            self._recording = False
            self._stop_evt.set()
            icon.icon  = _make_icon(False)
            icon.title = "Hawker — Paused"
        else:
            self._recording = True
            icon.icon  = _make_icon(True)
            icon.title = "Hawker — Recording"
            self._start_loop()
        icon.update_menu()

    def _on_dashboard(self, icon, item):
        cfg = _load_hawker_env()
        url = cfg.get("HAWKER_API_URL", "").rstrip("/") or "https://hawker-flax.vercel.app"
        webbrowser.open(url + "/app.html")

    def _on_logfile(self, icon, item):
        if _d.LOG_FILE.exists():
            os.startfile(str(_d.LOG_FILE))
        else:
            os.startfile(str(_d.REPO_DIR))

    def _on_startup(self, icon, item):
        if is_startup_enabled():
            _disable_startup()
        else:
            _enable_startup()
        icon.update_menu()

    def _on_quit(self, icon, item):
        self._stop_evt.set()
        icon.stop()

    # ── run ──────────────────────────────────────────────────────────────────

    def run(self):
        _d.REPO_DIR.mkdir(parents=True, exist_ok=True)
        _d.SHOTS_DIR.mkdir(parents=True, exist_ok=True)
        _d.log("Hawker tray app started (Windows)")
        self._start_loop()
        self._icon.run()


if __name__ == "__main__":
    HawkerTray().run()
