#!/usr/bin/env python3
"""
Time tracker (formerly the separate "Rick Rubin" app) — now part of Hawker.

Classifies the app in front as optimization / corporate / brain_drain, runs the
sales-line timers, and keeps the countdown to "Full Rubin": every productive or
sales hour shaves 1/3 day off a 5-year clock, every brain-drain hour adds it back.

No polling happens here. menubar.py runs the one loop and calls in.
Data: ~/.screenlog/tracker.db   Log: ~/.screenlog/tracker.log
"""

import re
import sqlite3
import subprocess
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

_HOME    = Path.home()
DATA_DIR = Path(__file__).resolve().parent
DB_PATH  = DATA_DIR / "tracker.db"
LOG_FILE = DATA_DIR / "tracker.log"

POLL_INTERVAL = 20
BASELINE_DAYS = 5 * 365
DAYS_PER_HOUR = 1 / 3

# Every DRAIN_ALERT_SECS straight on a social site, two browser shots
# (DRAIN_SHOT_GAP apart) go to the "Me No Waste Time" group via Beeper.
DRAIN_ALERT_SECS = 10 * 60
DRAIN_SHOT_GAP   = 30
DRAIN_CHAT_ID    = "106936"
BEEPER_SEND      = _HOME / ".claude" / "chief-of-staff" / "beeper_send.py"

# No keyboard/mouse for this long: count nothing, end any social stretch.
IDLE_CUTOFF_SECS = 5 * 60

# (category, name, timer color). Gearsupply keeps "sales_call" so history carries over.
SALES_LINES = [
    ("sales_call",        "Gearsupply", (34, 197, 94)),
    ("sales_call_2lease", "2.lease",    (59, 130, 246)),
]
SALES_CATS = [cat for cat, _, _ in SALES_LINES]

OPTIMIZATION_APPS = {
    "iTerm2", "Terminal", "Warp", "Alacritty", "Hyper",
    "Visual Studio Code", "Code", "Cursor", "Sublime Text", "Nova", "BBEdit",
    "Xcode", "PyCharm", "IntelliJ IDEA", "WebStorm", "Android Studio",
    "Notion", "Retool",
}

CORPORATE_APPS = {
    "Mail", "Microsoft Outlook", "Mimestream", "Spark", "Airmail 5",
    "Zoom", "Skype", "Webex", "Cisco Webex Meetings", "GoToMeeting", "Whereby",
    "Slack", "Microsoft Teams", "Teams", "Loom",
}

BROWSER_APPS = {
    "Google Chrome", "Safari", "Microsoft Edge", "Firefox", "Arc", "Brave Browser",
}

SOCIAL_DOMAINS = {
    "reddit.com", "x.com", "twitter.com", "youtube.com", "youtu.be",
    "instagram.com", "facebook.com", "fb.com", "tiktok.com",
    "linkedin.com", "twitch.tv", "discord.com", "tumblr.com",
    "pinterest.com", "mastodon.social", "bsky.app", "threads.net",
    "snapchat.com", "vimeo.com", "news.ycombinator.com",
}

CORPORATE_DOMAINS = {
    "mail.google.com", "outlook.live.com", "outlook.office365.com", "outlook.office.com",
    "calendar.google.com",
    "meet.google.com", "zoom.us", "teams.microsoft.com",
    "webex.com", "whereby.com", "gotomeeting.com", "bluejeans.com",
    "calendly.com", "cal.com", "savvycal.com",
    "salesforce.com", "hubspot.com", "pipedrive.com", "close.com",
    "apollo.io", "outreach.io", "salesloft.com", "gong.io",
    "lemlist.com", "instantly.ai",
    "asana.com", "monday.com", "atlassian.net", "trello.com",
    "linear.app", "clickup.com", "basecamp.com",
    "docs.google.com", "drive.google.com", "sheets.google.com",
    "slides.google.com", "docusign.com", "dropbox.com",
    "quickbooks.intuit.com", "bill.com", "expensify.com",
    "gusto.com", "rippling.com",
    "zendesk.com", "intercom.com", "freshdesk.com", "loom.com", "app.loom.com",
}


def log(msg):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(LOG_FILE, "a") as f:
            f.write(f"[{ts}] {msg}\n")
    except Exception:
        pass


# ── database ────────────────────────────────────────────────────────────────

_schema_done = False
_db_lock = threading.Lock()


def _db():
    global _schema_done
    c = sqlite3.connect(str(DB_PATH), timeout=5)
    if not _schema_done:
        c.execute("CREATE TABLE IF NOT EXISTS totals          (category TEXT PRIMARY KEY, seconds REAL DEFAULT 0)")
        c.execute("CREATE TABLE IF NOT EXISTS meta            (key TEXT PRIMARY KEY, value TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS daily           (date TEXT, category TEXT, seconds REAL DEFAULT 0, PRIMARY KEY (date, category))")
        c.execute("CREATE TABLE IF NOT EXISTS ignored_domains (domain TEXT PRIMARY KEY)")
        c.execute("INSERT OR IGNORE INTO meta VALUES ('start_ts',?)", (str(int(time.time())),))
        c.commit()
        _schema_done = True
    return c


def _today():
    return time.strftime("%Y-%m-%d")


def add_time(category, seconds):
    with _db_lock:
        c = _db()
        c.execute("""INSERT INTO totals (category, seconds) VALUES (?,?)
            ON CONFLICT(category) DO UPDATE SET seconds=seconds+excluded.seconds""",
            (category, seconds))
        c.execute("""INSERT INTO daily (date, category, seconds) VALUES (?,?,?)
            ON CONFLICT(date, category) DO UPDATE SET seconds=seconds+excluded.seconds""",
            (_today(), category, seconds))
        c.commit()
        c.close()


def set_today_time(category, new_seconds):
    """Set (not add) today's seconds for a category; totals move by the difference."""
    date = _today()
    with _db_lock:
        c = _db()
        row = c.execute("SELECT seconds FROM daily WHERE date=? AND category=?", (date, category)).fetchone()
        delta = new_seconds - (row[0] if row else 0.0)
        c.execute("""INSERT INTO daily (date, category, seconds) VALUES (?,?,?)
            ON CONFLICT(date, category) DO UPDATE SET seconds=excluded.seconds""",
            (date, category, new_seconds))
        c.execute("""INSERT INTO totals (category, seconds) VALUES (?,?)
            ON CONFLICT(category) DO UPDATE SET seconds=seconds+excluded.seconds""",
            (category, delta))
        c.commit()
        c.close()


def snapshot():
    """Everything the display needs, in one DB read:
    totals, today's totals, and today's starting countdown (stored once per day)."""
    today = _today()
    with _db_lock:
        c = _db()
        totals = dict(c.execute("SELECT category, seconds FROM totals").fetchall())
        today_t = dict(c.execute("SELECT category, seconds FROM daily WHERE date=?", (today,)).fetchall())
        key = f"day_start_{today}"
        row = c.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        if row is None:
            baseline = compute_days(totals)
            c.execute("INSERT OR IGNORE INTO meta VALUES (?,?)", (key, f"{baseline:.8f}"))
            c.commit()
        else:
            baseline = float(row[0])
        c.close()
    return {"totals": totals, "today": today_t, "baseline": baseline, "date": today}


def today_seconds(category):
    with _db_lock:
        c = _db()
        row = c.execute("SELECT seconds FROM daily WHERE date=? AND category=?",
                        (_today(), category)).fetchone()
        c.close()
    return row[0] if row else 0.0


def meta_get(key):
    with _db_lock:
        c = _db()
        row = c.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        c.close()
    return row[0] if row else None


def meta_set(key, value):
    with _db_lock:
        c = _db()
        if value is None:
            c.execute("DELETE FROM meta WHERE key=?", (key,))
        else:
            c.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (key, str(value)))
        c.commit()
        c.close()


def sales_resume_ts(category):
    """Start time of a call still running from before a restart (today only), or None."""
    v = meta_get(f"{category}_active_since")
    if not v:
        return None
    ts = float(v)
    return ts if time.strftime("%Y-%m-%d", time.localtime(ts)) == _today() else None


def day_totals(date):
    with _db_lock:
        c = _db()
        rows = dict(c.execute("SELECT category, seconds FROM daily WHERE date=?", (date,)).fetchall())
        c.close()
    return rows


# ── ignored (work) social pages ─────────────────────────────────────────────

_ignored_cache = None


def ignored_patterns():
    global _ignored_cache
    if _ignored_cache is None:
        with _db_lock:
            c = _db()
            _ignored_cache = [r[0].lower() for r in
                              c.execute("SELECT domain FROM ignored_domains ORDER BY domain")]
            c.close()
    return list(_ignored_cache)


def add_ignored_pattern(raw):
    """Store a domain ('messenger.com') or URL prefix ('facebook.com/messages/')."""
    global _ignored_cache
    pat = raw.lower().strip()
    if "/" not in pat and pat.startswith("www."):
        pat = pat[4:]
    with _db_lock:
        c = _db()
        c.execute("INSERT OR IGNORE INTO ignored_domains VALUES (?)", (pat,))
        c.commit()
        c.close()
    _ignored_cache = None


def remove_ignored_pattern(pat):
    global _ignored_cache
    with _db_lock:
        c = _db()
        c.execute("DELETE FROM ignored_domains WHERE domain=?", (pat,))
        c.commit()
        c.close()
    _ignored_cache = None


def domain(url):
    try:
        host = urlparse(url).netloc.lower()
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return ""


def is_work_url(url):
    """Social page marked as work in Ignored Sites. A pattern with "/" matches the
    host+path prefix; a bare domain matches the host or any subdomain."""
    if not url:
        return False
    d = domain(url)
    try:
        host_path = (d + urlparse(url).path).lower()
    except Exception:
        host_path = d
    for pat in ignored_patterns():
        if "/" in pat:
            if host_path.startswith(pat):
                return True
        elif d == pat or d.endswith("." + pat):
            return True
    return False


def is_social(url):
    d = domain(url)
    return any(d == s or d.endswith("." + s) for s in SOCIAL_DOMAINS)


def is_corporate_url(url):
    d = domain(url)
    return any(d == c or d.endswith("." + c) for c in CORPORATE_DOMAINS)


def categorize(app, url):
    """Category for this poll, or None if it doesn't count."""
    if app in OPTIMIZATION_APPS:
        return "optimization"
    if app in CORPORATE_APPS:
        return "corporate"
    if app in BROWSER_APPS and url:
        if is_social(url) and not is_work_url(url):
            return "brain_drain"
        if is_corporate_url(url):
            return "corporate"
    return None


# ── scoring + formatting ────────────────────────────────────────────────────

def compute_days(totals):
    productive_h = (totals.get("optimization", 0)
                    + sum(totals.get(cat, 0) for cat in SALES_CATS)) / 3600
    drain_h = totals.get("brain_drain", 0) / 3600
    return max(0.0, BASELINE_DAYS - productive_h * DAYS_PER_HOUR + drain_h * DAYS_PER_HOUR)


def fmt_countdown(days):
    if days <= 0:
        return "Full Rubin"
    total_s = days * 86400
    years = int(total_s // (365 * 86400)); total_s %= 365 * 86400
    d = int(total_s // 86400); total_s %= 86400
    h = int(total_s // 3600);  total_s %= 3600
    m = int(total_s // 60)
    s = int(total_s % 60)
    parts = []
    if years: parts.append(f"{years}y")
    if d:     parts.append(f"{d}d")
    if h:     parts.append(f"{h}h")
    if m:     parts.append(f"{m}m")
    parts.append(f"{s}s")
    return " ".join(parts)


def fmt_delta(delta_days):
    if abs(delta_days) * 86400 < 1:
        return "— no change yet today"
    total_s = abs(delta_days) * 86400
    d = int(total_s // 86400); total_s %= 86400
    h = int(total_s // 3600);  total_s %= 3600
    m = int(total_s // 60)
    s = int(total_s % 60)
    parts = []
    if d: parts.append(f"{d}d")
    if h: parts.append(f"{h}h")
    if m: parts.append(f"{m}m")
    parts.append(f"{s}s")
    amt = " ".join(parts)
    return f"↓ {amt} shaved today" if delta_days > 0 else f"↑ {amt} lost today"


def fmt_hours(seconds):
    h = int(seconds) // 3600
    m = (int(seconds) % 3600) // 60
    return f"{h}h {m:02d}m" if h else f"{m}m"


def status_label(today_totals):
    """("$TACKER" green | "SLACKER" red | "TRACKER" None) from today's sales hours."""
    sales_h = sum(today_totals.get(cat, 0) for cat in SALES_CATS) / 3600
    if sales_h >= 3:
        return "$TACKER", (34, 197, 94)
    now_min = int(time.strftime("%H")) * 60 + int(time.strftime("%M"))

    def can_reach(target_h, deadline_hour):
        return sales_h + max(0, deadline_hour * 60 - now_min) / 60 >= target_h

    if not can_reach(1, 11) or not can_reach(2, 14) or not can_reach(3, 17):
        return "SLACKER", (239, 68, 68)
    return "TRACKER", None


def parse_time_input(text):
    """'30m', '1h', '1h 30m', '1.5h', '1:30', '90' (bare = minutes) → seconds or None."""
    text = text.strip().lower()
    if not text:
        return None
    m = re.match(r'^(\d+):(\d{2})(?::(\d{2}))?$', text)
    if m:
        return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3) or 0)
    total, found = 0, False
    for val, unit in re.findall(r'(\d+(?:\.\d+)?)\s*([hm])', text):
        total += float(val) * (3600 if unit == 'h' else 60)
        found = True
    if found:
        return int(total)
    m = re.match(r'^(\d+(?:\.\d+)?)$', text)
    return int(float(m.group(1)) * 60) if m else None


# ── Beeper ──────────────────────────────────────────────────────────────────

def send_to_group(text, images):
    r = subprocess.run(["/usr/bin/python3", str(BEEPER_SEND), DRAIN_CHAT_ID, text, *map(str, images)],
                       capture_output=True, text=True, timeout=180)
    if r.returncode != 0:
        log(f"group send failed: {(r.stderr or r.stdout).strip()[:300]}")
        return False
    return True


def send_daily_stats_if_due():
    """After midnight, send yesterday's sales + brain-drain hours once (meta daily_stats_sent)."""
    yesterday = time.strftime("%Y-%m-%d", time.localtime(time.time() - 86400))
    try:
        sent = meta_get("daily_stats_sent")
        if sent is None:
            meta_set("daily_stats_sent", yesterday)
            return
        if sent >= yesterday:
            return
        rows = day_totals(yesterday)
        meta_set("daily_stats_sent", yesterday)
        sales = sum(rows.get(cat, 0) for cat in SALES_CATS)
        day = time.strftime("%a %-d %b", time.strptime(yesterday, "%Y-%m-%d"))
        text = (f"Mendel · {day}\nSales calls: {fmt_hours(sales)}\n"
                f"Brain drain: {fmt_hours(rows.get('brain_drain', 0))}")
        if send_to_group(text, []):
            log(f"daily stats sent for {yesterday}")
    except Exception as e:
        log(f"daily stats error: {e}")
