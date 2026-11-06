#!/usr/bin/env python3
"""
Hawker menu bar app — screenshots of social sites + the time tracker
(formerly the separate "Rick Rubin" app), in ONE app with ONE poll loop.

Each 20s poll: idle check (no subprocess), front app name (AppKit, no
osascript), and — only when a browser is in front — one osascript call for
its URL. Both features share that reading and the same screenshot.

Run:  launchctl kickstart -k gui/$(id -u)/com.mendelrosenberg.screenlog
"""

import atexit
import base64
import json
import os
import random
import signal
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

import objc
import AppKit
import Foundation
import rumps
try:
    import WebKit
    _HAS_WEBKIT = True
except ImportError:
    _HAS_WEBKIT = False

_HERE   = Path(__file__).resolve().parent
_SCRIPT = Path(__file__).resolve()
_HOME   = Path.home()

sys.path.insert(0, str(_HERE))
import daemon as _d
import tracker as _t

_PLIST_LABEL = "com.mendelrosenberg.screenlog"
_PLIST_PATH  = _HOME / "Library" / "LaunchAgents" / f"{_PLIST_LABEL}.plist"
_PIDFILE     = _HERE / "menubar.pid"

POLL_INTERVAL = _d.POLL_INTERVAL
_GREEN = (34, 197, 94)
_RED   = (239, 68, 68)


# ── Hawker API ──────────────────────────────────────────────────────────────

def _load_hawker_env():
    env_file = _HERE / "hawker.env"
    cfg = {}
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                cfg[k.strip()] = v.strip()
    cfg.setdefault("HAWKER_API_URL", os.environ.get("HAWKER_API_URL", ""))
    cfg.setdefault("HAWKER_API_KEY", os.environ.get("HAWKER_API_KEY", ""))
    return cfg


def _hawker_upload(stem, jpg_path, domain):
    cfg = _load_hawker_env()
    url = cfg.get("HAWKER_API_URL", "").rstrip("/")
    key = cfg.get("HAWKER_API_KEY", "")
    if not url or not key:
        _d.log("Hawker upload skipped — HAWKER_API_URL/KEY not configured")
        return False
    try:
        payload = json.dumps({
            "stem": stem, "domain": domain,
            "imageBase64": base64.b64encode(Path(jpg_path).read_bytes()).decode(),
        }).encode()
        req = urllib.request.Request(url + "/api/upload", data=payload, method="POST",
                                     headers={"Content-Type": "application/json", "x-api-key": key})
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read())
            if body.get("ok"):
                _d.log(f"Uploaded to Hawker: {body.get('url','')[:60]}")
                return True
            _d.log(f"Hawker upload error: {body}")
    except Exception as exc:
        _d.log(f"Hawker upload failed: {exc}")
    return False


# ── AppKit helpers ──────────────────────────────────────────────────────────

def _attr_parts(parts, font_name=None):
    """Attributed string from [(text, rgb_or_None), ...]."""
    try:
        font = ((AppKit.NSFont.fontWithName_size_(font_name, 13) if font_name else None)
                or AppKit.NSFont.boldSystemFontOfSize_(13))
        result = AppKit.NSMutableAttributedString.alloc().init()
        for text, rgb in parts:
            attrs = {AppKit.NSFontAttributeName: font}
            if rgb:
                r, g, b = rgb
                attrs[AppKit.NSForegroundColorAttributeName] = \
                    AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(r/255, g/255, b/255, 1.0)
            result.appendAttributedString_(
                Foundation.NSAttributedString.alloc().initWithString_attributes_(text, attrs))
        return result
    except Exception:
        return None


class _AddSiteDelegate(AppKit.NSObject):
    """NSTextField delegate — fires callback when Return is pressed."""

    def init(self):
        self = objc.super(_AddSiteDelegate, self).init()
        self._callback = None
        return self

    def controlTextDidEndEditing_(self, notification):
        info = notification.userInfo()
        if not info:
            return
        try:
            if int(info["NSTextMovement"]) != 16:   # NSReturnTextMovement
                return
        except (KeyError, TypeError, ValueError):
            return
        field = notification.object()
        text = field.stringValue().strip()
        field.setStringValue_("")
        if text and self._callback:
            self._callback(text)


# ── singleton + login item ──────────────────────────────────────────────────

def _acquire_singleton():
    """PID-file singleton. Doesn't touch the LaunchAgent (unloading our own plist
    from inside makes launchd stop managing us)."""
    my_pid = os.getpid()
    if _PIDFILE.exists():
        try:
            old = int(_PIDFILE.read_text().strip())
            if old != my_pid:
                try: os.kill(old, signal.SIGTERM)
                except ProcessLookupError: pass
                time.sleep(0.5)
        except Exception:
            pass
    _PIDFILE.write_text(str(my_pid))
    atexit.register(lambda: _PIDFILE.unlink(missing_ok=True))


# ── app ─────────────────────────────────────────────────────────────────────

class HawkerApp(rumps.App):

    def __init__(self):
        super().__init__("(o,o)", quit_button=None)

        self._recording  = True          # Hawker screenshots + social logging
        self._stop_evt   = threading.Event()
        self._shot_lock  = threading.Lock()
        self._face_dirty = True

        # Hawker state
        self._last_shot_time = 0.0
        self._next_shot_gap  = random.randint(_d.MIN_SHOT_GAP, _d.MAX_SHOT_GAP)
        self._last_domain    = None

        # Tracker state
        self._social_start    = 0.0      # start of the current brain-drain stretch
        self._social_url      = ""
        self._social_upload   = False    # may the alert's shots go to the Hawker gallery
        self._alerted_session = 0.0
        self._alerts_sent     = 0
        self._session_cat     = None
        self._session_app     = ""
        self._session_secs    = 0
        self._stacker_gif_date = ""
        self._stats_checked   = ""
        self._snap = _t.snapshot()       # cached DB read; refreshed after writes
        self._current_date = self._snap["date"]

        self._sales = {}
        for cat, name, _ in SALES_LINES:
            resume_ts = _t.sales_resume_ts(cat)
            st = {"running": bool(resume_ts), "start_ts": resume_ts or 0.0,
                  "accumulated": self._snap["today"].get(cat, 0.0)}
            if resume_ts:
                st["accumulated"] -= time.time() - resume_ts
                _t.log(f"{name} sales call resumed after restart")
            self._sales[cat] = st

        self._add_delegate = _AddSiteDelegate.alloc().init()
        self._add_delegate._callback = self._on_site_added

        self.label_item     = rumps.MenuItem("TRACKER")
        self.countdown_item = rumps.MenuItem("computing…")
        self.delta_item     = rumps.MenuItem("— no change yet today")
        self.sales_items = {cat: rumps.MenuItem(f"🟢 Start sales for {name}",
                                                callback=self._make_sales_toggle(cat))
                            for cat, name, _ in SALES_LINES}
        self.sales_stat_items = {cat: rumps.MenuItem(f"  {name} Sales: 0m  +",
                                                     callback=self._make_add_sales(cat))
                                 for cat, name, _ in SALES_LINES}
        self.opt_item     = rumps.MenuItem("  Optimization: 0m  +", callback=self.on_add_optimization)
        self.corp_item    = rumps.MenuItem("  Corporate:   0m")
        self.drain_item   = rumps.MenuItem("  Brain Drain: 0m  +", callback=self.on_add_drain)
        self.ignored_menu = rumps.MenuItem("Ignored Sites (work, not brain drain)")
        self.toggle_item  = rumps.MenuItem("Pause Screenshots", callback=self.on_toggle)
        self.login_item   = rumps.MenuItem("Launch at Login", callback=self.on_login)
        self.login_item.state = _PLIST_PATH.exists()

        self.menu = [
            self.label_item,
            self.countdown_item,
            self.delta_item,
            None,
            *self.sales_items.values(),
            None,
            self.opt_item,
            self.corp_item,
            *self.sales_stat_items.values(),
            self.drain_item,
            None,
            self.ignored_menu,
            None,
            self.toggle_item,
            rumps.MenuItem("Open Dashboard",    callback=self.on_dashboard),
            rumps.MenuItem("Open Screenshot Log", callback=self.on_logfile),
            rumps.MenuItem("Open Activity Log", callback=self.on_view_log),
            None,
            self.login_item,
            rumps.MenuItem("Restart", callback=self.on_restart),
            rumps.MenuItem("Quit Hawker", callback=self.on_quit),
        ]
        self._rebuild_ignored_menu()

        # Live sales / brain-drain timer gets its own status item, created before
        # rumps makes the face item so macOS puts it to the right.
        self._timer_item = None
        try:
            bar = AppKit.NSStatusBar.systemStatusBar()
            self._timer_item = bar.statusItemWithLength_(AppKit.NSVariableStatusItemLength)
            self._timer_item.setAutosaveName_("hawker.timer")
            self._timer_item.setMenu_(self._menu._menu)
            self._timer_item.setVisible_(False)
        except Exception as e:
            _t.log(f"timer status item error: {e}")

        threading.Thread(target=self._loop, daemon=True).start()

    # ── the one poll loop ───────────────────────────────────────────────────

    def _loop(self):
        while not self._stop_evt.is_set():
            # Background threads get no autorelease pool; drain one per poll
            # (without it the app reached 11.5 GB after 6 days).
            with objc.autorelease_pool():
                try:
                    self._poll()
                except Exception as exc:
                    _d.log(f"loop error: {exc}")
            self._stop_evt.wait(POLL_INTERVAL)

    def _poll(self):
        # Shabbat / Yom Tov: no computer use, so count nothing at all.
        if _t.is_shabbat():
            self._social_start = 0.0
            self._last_domain = None
            self._flush_session()
            return

        live = self._running_sales()

        # Sales call running: count it; Hawker tracks nothing during sales.
        if live:
            _t.add_time(live, POLL_INTERVAL)
            self._social_start = 0.0
            self._last_domain = None
            if self._session_cat != live:
                self._flush_session()
                self._session_cat = live
                self._session_app = f"{self._sales_name(live)} Sales Call"
            self._session_secs += POLL_INTERVAL
            self._snap = _t.snapshot()
            return

        # Away from the Mac: count nothing, end any social stretch.
        if _d.idle_seconds() >= _t.IDLE_CUTOFF_SECS:
            self._social_start = 0.0
            self._last_domain = None
            self._flush_session()
            return

        app = _d.front_app()
        url = _d.get_browser_url(app) if app in _t.BROWSER_APPS else None
        work = _t.is_work_url(url)

        # ── tracker ──
        if url and _t.is_social(url) and not work:
            if self._social_start == 0.0:
                self._social_start = time.time()
            self._social_url = url
        else:
            self._social_start = 0.0
        category = _t.categorize(app, url)
        if category:
            _t.add_time(category, POLL_INTERVAL)
            if category != self._session_cat or app != self._session_app:
                self._flush_session()
                self._session_cat = category
                self._session_app = app
            self._session_secs += POLL_INTERVAL
            self._snap = _t.snapshot()
        else:
            self._flush_session()

        # ── Hawker ──
        hawk = bool(self._recording and url and _d.is_social_media(url)
                    and not work and not _d.is_ignored(url, _d.load_ignored_urls())
                    and not _d.title_looks_sensitive(url))
        self._social_upload = hawk
        if not hawk:
            self._last_domain = None
            return
        domain = _d.extract_domain(url)
        if domain != self._last_domain:
            _d.record_visit(domain)
            self._last_domain = domain
        _d.add_domain_time(domain, POLL_INTERVAL)
        if time.time() - self._last_shot_time >= self._next_shot_gap:
            _d.log(f"On social media: {url[:80]}")
            self._capture(url, domain, upload=True)

    def _capture(self, url, domain, upload):
        """One browser-window screenshot (address bar blurred, sensitive text
        redacted) shared by the Hawker gallery and the brain-drain alert."""
        with self._shot_lock:
            result = _d.take_screenshot(url, domain)
            if not result:
                return None
            path, stem = result
            _d.cleanup_old()
            if upload:
                _hawker_upload(stem, path, domain)
                self._last_shot_time = time.time()
                self._next_shot_gap = random.randint(_d.MIN_SHOT_GAP, _d.MAX_SHOT_GAP)
                _d.log(f"Next shot in {self._next_shot_gap // 60}m {self._next_shot_gap % 60}s")
            return path

    def _flush_session(self):
        if self._session_cat and self._session_secs >= POLL_INTERVAL:
            m = self._session_secs // 60
            h, mn = m // 60, m % 60
            dur = f"{h}h {mn:02d}m" if h else f"{mn}m"
            _t.log(f"{dur} {self._session_cat} — {self._session_app or self._session_cat}")
        self._session_cat, self._session_app, self._session_secs = None, "", 0

    def _drain_alert(self, session_start):
        """Two shots 30s apart (second only if the stretch is still going), then
        send to the group. Goes out even if no shot could be taken."""
        try:
            url = self._social_url
            domain = _t.domain(url) or "social site"
            shots = []
            for i in (1, 2):
                if i == 2:
                    self._stop_evt.wait(_t.DRAIN_SHOT_GAP)
                    if self._social_start != session_start:
                        break
                    url = self._social_url
                path = self._capture(url, _t.domain(url), upload=self._social_upload)
                if path:
                    shots.append(path)
            mins = int(time.time() - session_start) // 60
            if _t.send_to_group(f"Mendel · {mins} min of brain drain on {domain}", shots):
                _t.log(f"drain alert sent: {domain}, {len(shots)} screenshot(s)")
        except Exception as e:
            _t.log(f"drain alert error: {e}")

    # ── display (main thread) ───────────────────────────────────────────────

    @rumps.timer(60)
    def on_minute(self, _):
        today = time.strftime("%Y-%m-%d")
        if self._stats_checked != today:
            self._stats_checked = today
            threading.Thread(target=_t.send_daily_stats_if_due, daemon=True).start()

    @rumps.timer(1)
    def on_tick(self, _):
        today = time.strftime("%Y-%m-%d")
        if today != self._current_date:
            self._current_date = today
            for st in self._sales.values():
                st["accumulated"] = 0.0
            self._snap = _t.snapshot()
        if self._face_dirty:
            self._apply_face()
        self._update_display()

    def _apply_face(self):
        face, rgb = ("(o,o)", _GREEN) if self._recording else ("(x,x)", _RED)
        try:
            attr = _attr_parts([(face, rgb)], font_name="Menlo-Bold")
            self._nsapp.nsstatusitem.button().setAttributedTitle_(attr)
            self._face_dirty = False
        except Exception:
            self.title = face

    def _update_display(self):
        snap = self._snap
        days = _t.compute_days(snap["totals"])
        prefix, _ = _t.status_label(snap["today"])
        if prefix == "$TACKER" and self._stacker_gif_date != self._current_date:
            self._stacker_gif_date = self._current_date
            self._show_stacker_gif()

        timers = []
        for cat, name, rgb in SALES_LINES:
            st = self._sales[cat]
            if st["running"]:
                e = int(st["accumulated"] + time.time() - st["start_ts"])
                clock = f"{e // 3600}:{(e % 3600) // 60:02d}:{e % 60:02d}"
                timers.append((clock, rgb))
                self.sales_items[cat].title = f"🔴 {clock} — stop {name} sales call"
            else:
                self.sales_items[cat].title = f"🟢 Start sales for {name}"

        if self._social_start > 0 and not self._running_sales():
            elapsed = int(time.time() - self._social_start)
            if self._alerted_session != self._social_start:
                self._alerted_session = self._social_start
                self._alerts_sent = 0
            if elapsed // _t.DRAIN_ALERT_SECS > self._alerts_sent:
                self._alerts_sent = elapsed // _t.DRAIN_ALERT_SECS
                threading.Thread(target=self._drain_alert,
                                 args=(self._social_start,), daemon=True).start()
            timers.append((f"{elapsed // 3600}:{(elapsed % 3600) // 60:02d}:{elapsed % 60:02d}", _RED))
        self._set_timer(timers)

        self.label_item.title     = f"{prefix} — {_t.fmt_countdown(days)} → Full Rubin"
        self.countdown_item.title = f"  Status: {self._status_hint(prefix)}"
        self.delta_item.title     = "  " + _t.fmt_delta(snap["baseline"] - days)
        t = snap["today"]
        self.opt_item.title  = f"  Optimization: {_t.fmt_hours(t.get('optimization', 0))}  +"
        self.corp_item.title = f"  Corporate:   {_t.fmt_hours(t.get('corporate', 0))}"
        for cat, name, _ in SALES_LINES:
            self.sales_stat_items[cat].title = f"  {name} Sales: {_t.fmt_hours(t.get(cat, 0))}  +"
        self.drain_item.title = f"  Brain Drain: {_t.fmt_hours(t.get('brain_drain', 0))}  +"

    @staticmethod
    def _status_hint(prefix):
        return {"$TACKER": "3h of sales done today",
                "SLACKER": "behind on sales (1h by 11, 2h by 2, 3h by 5)",
                }.get(prefix, "on pace for 3h of sales")

    def _set_timer(self, timers):
        if self._timer_item is None:
            return
        try:
            if not timers:
                self._timer_item.setVisible_(False)
                return
            parts = [(("  " if i else "") + text, rgb) for i, (text, rgb) in enumerate(timers)]
            attr = _attr_parts(parts)
            button = self._timer_item.button()
            if attr:
                button.setAttributedTitle_(attr)
            else:
                button.setTitle_("".join(t for t, _ in parts))
            self._timer_item.setVisible_(True)
        except Exception as e:
            _t.log(f"timer item error: {e}")

    def _show_stacker_gif(self):
        if not _HAS_WEBKIT:
            return

        def _fetch_and_show():
            candidates = [
                "https://media.giphy.com/media/JpG2A9P3dPHXaTYrwu/giphy.gif",
                "https://media.giphy.com/media/fTy7Lm1uaAsTaTKDBJ/giphy.gif",
                "https://media.giphy.com/media/l41lZccR1oUigYeNa/giphy.gif",
            ]
            gif_b64 = None
            for u in candidates:
                try:
                    req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
                    with urllib.request.urlopen(req, timeout=8) as r:
                        gif_b64 = base64.b64encode(r.read()).decode()
                    break
                except Exception:
                    continue

            def _show():
                try:
                    W, H = 560, 500
                    screen = AppKit.NSScreen.mainScreen().visibleFrame()
                    x = screen.origin.x + (screen.size.width - W) / 2
                    y = screen.origin.y + (screen.size.height - H) / 2
                    panel = AppKit.NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
                        Foundation.NSMakeRect(x, y, W, H),
                        AppKit.NSWindowStyleMaskTitled | AppKit.NSWindowStyleMaskClosable,
                        AppKit.NSBackingStoreBuffered, False)
                    panel.setTitle_("💰  $TACKER STATUS UNLOCKED  💰")
                    panel.setLevel_(AppKit.NSFloatingWindowLevel)
                    img = (f'<img src="data:image/gif;base64,{gif_b64}" style="max-width:100%;'
                           f'max-height:340px;border-radius:10px;border:3px solid #22c55e;display:block;">'
                           if gif_b64 else
                           '<div style="color:#22c55e;font-size:60px;text-align:center;">💸💸💸</div>')
                    html = f"""<!DOCTYPE html><html><body style="margin:0;padding:16px 16px 12px;
background:#0a0a0a;display:flex;flex-direction:column;justify-content:center;align-items:center;
height:calc(100vh - 28px);box-sizing:border-box;font-family:Arial,sans-serif;">
<div style="color:#22c55e;font-size:26px;font-weight:900;text-align:center;letter-spacing:3px;
margin-bottom:14px;text-shadow:0 0 20px #22c55e;">💰&nbsp; YOU STACKED IT &nbsp;💰</div>{img}
<div style="color:#555;font-size:13px;margin-top:12px;text-align:center;">
3 hours on the clock. Rick Rubin would say something profound here.<br>
<span style="color:#333;font-size:11px;">(click ✕ to close, or wait 10s)</span></div></body></html>"""
                    wv = WebKit.WKWebView.alloc().initWithFrame_(Foundation.NSMakeRect(0, 0, W, H))
                    wv.loadHTMLString_baseURL_(html, None)
                    panel.setContentView_(wv)
                    panel.makeKeyAndOrderFront_(None)
                    AppKit.NSApp.activateIgnoringOtherApps_(True)

                    def _auto_close():
                        time.sleep(10)
                        AppKit.NSOperationQueue.mainQueue().addOperationWithBlock_(panel.close)
                    threading.Thread(target=_auto_close, daemon=True).start()
                except Exception as exc:
                    _t.log(f"stacker GIF show error: {exc}")

            AppKit.NSOperationQueue.mainQueue().addOperationWithBlock_(_show)

        threading.Thread(target=_fetch_and_show, daemon=True).start()

    # ── sales lines ─────────────────────────────────────────────────────────

    def _running_sales(self):
        return next((cat for cat, st in self._sales.items() if st["running"]), None)

    def _sales_name(self, category):
        return next(name for cat, name, _ in SALES_LINES if cat == category)

    def _stop_sales(self, category):
        st = self._sales[category]
        elapsed = time.time() - st["start_ts"]
        st["accumulated"] += elapsed
        st["running"] = False
        _t.meta_set(f"{category}_active_since", None)
        _t.log(f"{self._sales_name(category)} sales call ended: {elapsed/3600:.2f}h")

    def _make_sales_toggle(self, category):
        def cb(_):
            st = self._sales[category]
            if not st["running"]:
                other = self._running_sales()   # one call at a time
                if other:
                    self._stop_sales(other)
                st["running"] = True
                st["start_ts"] = time.time()
                self._social_start = 0.0
                _t.meta_set(f"{category}_active_since", st["start_ts"])
                _t.log(f"{self._sales_name(category)} sales call started")
            else:
                self._stop_sales(category)
            self._update_display()
        return cb

    def _make_add_sales(self, category):
        return lambda _: self._show_add_dialog(category, f"{self._sales_name(category)} Sales")

    def _show_add_dialog(self, category, display_name):
        resp = rumps.Window(
            message=(f'Time to add to {display_name} (e.g. 30m  1h  1h 30m  1:30)\n'
                     'Prefix with - to subtract (e.g. -45m)\n'
                     'Prefix with = to set a specific total (e.g. =2h 15m)'),
            title=f'Log {display_name} Time', default_text='', ok='Add', cancel='Cancel',
            dimensions=(260, 24)).run()
        if not resp.clicked:
            return
        text = resp.text.strip()
        set_mode, sub_mode = text.startswith('='), text.startswith('-')
        if set_mode or sub_mode:
            text = text[1:].strip()
        seconds = _t.parse_time_input(text)
        if not seconds or seconds <= 0:
            return
        if sub_mode:
            seconds = min(seconds, int(_t.today_seconds(category)))   # never below zero
            if seconds <= 0:
                return
        m = seconds // 60
        dur = f"{m // 60}h {m % 60:02d}m" if m >= 60 else f"{m}m"
        if set_mode:
            _t.set_today_time(category, seconds)
            _t.log(f"manual set {display_name} → {dur}")
        elif sub_mode:
            _t.add_time(category, -seconds)
            _t.log(f"manual -{dur} {display_name}")
        else:
            _t.add_time(category, seconds)
            _t.log(f"manual +{dur} {display_name}")
        self._snap = _t.snapshot()
        if category in self._sales:
            st = self._sales[category]
            st["accumulated"] = self._snap["today"].get(category, 0.0)
            if st["running"]:
                st["accumulated"] -= time.time() - st["start_ts"]

    def on_add_optimization(self, _):
        self._show_add_dialog("optimization", "Optimization")

    def on_add_drain(self, _):
        self._show_add_dialog("brain_drain", "Brain Drain")

    # ── ignored sites submenu ───────────────────────────────────────────────

    def _on_site_added(self, text):
        _t.add_ignored_pattern(text)
        AppKit.NSOperationQueue.mainQueue().addOperationWithBlock_(self._rebuild_ignored_menu)

    def _rebuild_ignored_menu(self):
        for key in list(self.ignored_menu.keys()):
            del self.ignored_menu[key]
        submenu = self.ignored_menu._menuitem.submenu()
        if submenu is None:
            submenu = AppKit.NSMenu.alloc().init()
            self.ignored_menu._menuitem.setSubmenu_(submenu)
        else:
            while submenu.numberOfItems() > 0:
                submenu.removeItemAtIndex_(0)
        for d in _t.ignored_patterns():
            self.ignored_menu[d] = rumps.MenuItem(f"  ✕  {d}", callback=self._make_remove_cb(d))
        submenu = self.ignored_menu._menuitem.submenu()
        if submenu is None:
            submenu = AppKit.NSMenu.alloc().init()
            self.ignored_menu._menuitem.setSubmenu_(submenu)
        view = AppKit.NSView.alloc().initWithFrame_(Foundation.NSMakeRect(0, 0, 268, 30))
        field = AppKit.NSTextField.alloc().initWithFrame_(Foundation.NSMakeRect(14, 4, 240, 22))
        field.setPlaceholderString_("domain or url/path  ↩ to add")
        field.setBezeled_(True)
        field.setEditable_(True)
        field.setFont_(AppKit.NSFont.systemFontOfSize_(13))
        field.setDelegate_(self._add_delegate)
        view.addSubview_(field)
        ns_item = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("", None, "")
        ns_item.setView_(view)
        submenu.insertItem_atIndex_(ns_item, 0)
        submenu.insertItem_atIndex_(AppKit.NSMenuItem.separatorItem(), 1)

    def _make_remove_cb(self, pat):
        def cb(_):
            _t.remove_ignored_pattern(pat)
            self._rebuild_ignored_menu()
        return cb

    # ── other menu callbacks ────────────────────────────────────────────────

    def on_toggle(self, _):
        """Pauses Hawker screenshots + social logging. Time tracking keeps running."""
        self._recording = not self._recording
        self.toggle_item.title = "Pause Screenshots" if self._recording else "Resume Screenshots"
        self._last_domain = None
        self._face_dirty = True
        self._apply_face()

    def on_dashboard(self, _):
        url = _load_hawker_env().get("HAWKER_API_URL", "").rstrip("/") or "https://hawker-flax.vercel.app"
        subprocess.run(["open", url + "/gallery.html"])

    def on_logfile(self, _):
        subprocess.run(["open", str(_d.LOG_FILE)])

    def on_view_log(self, _):
        subprocess.Popen(["open", str(_t.LOG_FILE)])

    def on_login(self, _):
        """Turning this off removes the LaunchAgent; turning it on needs the
        installer (mac/install.command), which writes the plist with the Python
        binary that holds the Screen Recording permission."""
        if _PLIST_PATH.exists():
            subprocess.run(["launchctl", "unload", str(_PLIST_PATH)], capture_output=True)
            _PLIST_PATH.unlink(missing_ok=True)
            self.login_item.state = 0
        else:
            rumps.alert("Launch at Login", "Run mac/install.command from the hawker repo to turn this back on.")

    def on_restart(self, _):
        self._stop_evt.set()
        subprocess.Popen(["/bin/launchctl", "kickstart", "-k", f"gui/{os.getuid()}/{_PLIST_LABEL}"],
                         close_fds=True, start_new_session=True)
        rumps.quit_application()

    def on_quit(self, _):
        _PIDFILE.unlink(missing_ok=True)
        self._stop_evt.set()
        # KeepAlive=true would respawn us; bootout removes the service for this
        # session (the plist stays, so next login starts us again).
        subprocess.Popen(["launchctl", "bootout", f"gui/{os.getuid()}/{_PLIST_LABEL}"],
                         start_new_session=True)
        rumps.quit_application()


SALES_LINES = _t.SALES_LINES


if __name__ == "__main__":
    _acquire_singleton()
    _app = HawkerApp()
    try:
        objc.lookUpClass("NSApplication").sharedApplication().setActivationPolicy_(1)  # no Dock icon
    except Exception as _e:
        _t.log(f"setActivationPolicy error: {_e}")
    _app.run()
