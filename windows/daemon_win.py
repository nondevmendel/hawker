#!/usr/bin/env python3
"""
Hawker daemon — Windows version.
Replaces macOS CoreGraphics/Vision/osascript with Windows equivalents.
"""

import json
import os
import random
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

try:
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
except ImportError:
    subprocess.run([sys.executable, "-m", "pip", "install", "pillow"], check=True)
    from PIL import Image, ImageDraw, ImageFilter, ImageFont


# ── paths ──────────────────────────────────────────────────────────────────
APPDATA   = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
REPO_DIR  = APPDATA / "Hawker"
SHOTS_DIR = REPO_DIR / "screenshots"
LOG_FILE  = REPO_DIR / "hawker.log"
META_FILE = SHOTS_DIR / "metadata.json"
VISITS_FILE = REPO_DIR / "visits.json"
CONFIG_FILE = REPO_DIR / "config.json"

# ── timing ─────────────────────────────────────────────────────────────────
POLL_INTERVAL = 20
MIN_SHOT_GAP  = 60
MAX_SHOT_GAP  = 2 * 60
MAX_AGE_HOURS = 48

# ── image settings ─────────────────────────────────────────────────────────
MAX_WIDTH           = 1920
JPEG_QUALITY        = 72
ADDRESSBAR_FRACTION = 0.10

# ── social media domains ────────────────────────────────────────────────────
SOCIAL_DOMAINS = {
    "reddit.com", "www.reddit.com", "old.reddit.com", "new.reddit.com",
    "x.com", "twitter.com", "www.twitter.com",
    "youtube.com", "www.youtube.com", "youtu.be",
    "instagram.com", "www.instagram.com",
    "facebook.com", "www.facebook.com", "fb.com",
    "tiktok.com", "www.tiktok.com",
    "linkedin.com", "www.linkedin.com",
    "twitch.tv", "www.twitch.tv",
    "discord.com", "www.discord.com",
    "tumblr.com", "www.tumblr.com",
    "pinterest.com", "www.pinterest.com",
    "mastodon.social", "bsky.app", "threads.net",
    "snapchat.com", "www.snapchat.com",
    "vimeo.com", "www.vimeo.com",
    "hackernews.com", "news.ycombinator.com",
}

SENSITIVE_TITLE_KEYWORDS = [
    "bank", "login", "sign in", "password", "credit card", "account",
    "paypal", "venmo", "cashapp", "zelle", "chase", "wells fargo",
    "bank of america", "citi", "amex", "american express",
    "tax", "turbotax", "irs", "social security", "ssn",
    "medical", "health", "patient", "insurance", "claim",
    "private", "confidential", "secure", "verify",
]

SENSITIVE_REGEXES = [
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
    r"\b4[0-9]{12}(?:[0-9]{3})?\b",
    r"\b5[1-5][0-9]{14}\b",
    r"\b3[47][0-9]{13}\b",
    r"\b(?:\d{3})-?(?:\d{2})-?(?:\d{4})\b",
    r"\b(?:\d{3}[-.\s]??\d{3}[-.\s]??\d{4}|\(\d{3}\)\s*\d{3}[-.\s]??\d{4})\b",
]


# ════════════════════════════════════════════════════════════════════════════
# Logging / metadata helpers

def log(msg: str):
    REPO_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    try:
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def load_metadata():
    try:
        return json.loads(META_FILE.read_text())
    except Exception:
        return {}


def save_metadata(data):
    SHOTS_DIR.mkdir(parents=True, exist_ok=True)
    META_FILE.write_text(json.dumps(data, indent=2))


def load_visits():
    try:
        return json.loads(VISITS_FILE.read_text())
    except Exception:
        return {}


def save_visits(data):
    VISITS_FILE.write_text(json.dumps(data, indent=2))


# ════════════════════════════════════════════════════════════════════════════
# Screen capture — uses mss (cross-platform, no special permissions on Windows)

def grab_screen():
    try:
        import mss
        with mss.mss() as sct:
            # monitors[0] is the virtual monitor covering all screens
            raw = sct.grab(sct.monitors[0])
            img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
            return img
    except ImportError:
        log("mss not installed — run: pip install mss")
        return None
    except Exception as e:
        log(f"grab_screen error: {e}")
        return None


# ════════════════════════════════════════════════════════════════════════════
# Browser URL — reads address bar via Windows UI Automation

def _chromium_url(class_name: str):
    """Read the address bar from a Chromium-based browser window."""
    try:
        import uiautomation as auto
        w = auto.WindowControl(searchDepth=1, ClassName=class_name)
        if not w.Exists(0.3):
            return None
        bar = w.EditControl(Name="Address and search bar", searchDepth=12)
        if not bar.Exists(0.3):
            bar = w.EditControl(searchDepth=12)
        if bar.Exists(0.3):
            val = bar.GetValuePattern().Value
            if val.startswith("http"):
                return val
    except Exception:
        pass
    return None


def _firefox_url():
    try:
        import uiautomation as auto
        w = auto.WindowControl(searchDepth=1, ClassName="MozillaWindowClass")
        if not w.Exists(0.3):
            return None
        for name in ("Search with Google or enter address", "Search or enter address"):
            bar = w.EditControl(Name=name, searchDepth=12)
            if bar.Exists(0.3):
                val = bar.GetValuePattern().Value
                if val.startswith("http"):
                    return val
        # Generic fallback
        combo = w.ComboBoxControl(searchDepth=8)
        if combo.Exists(0.3):
            edit = combo.EditControl()
            if edit.Exists(0.3):
                val = edit.GetValuePattern().Value
                if val.startswith("http"):
                    return val
    except Exception:
        pass
    return None


def get_active_browser_url():
    # Chromium class is shared by Chrome, Edge, and Brave
    url = _chromium_url("Chrome_WidgetWin_1")
    if url:
        return url
    url = _firefox_url()
    if url:
        return url
    return None


# ════════════════════════════════════════════════════════════════════════════
# OCR redaction — uses pytesseract (requires Tesseract installed)

def try_ocr_and_redact(img):
    try:
        import pytesseract
        data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
        pattern = re.compile("|".join(SENSITIVE_REGEXES))
        draw = ImageDraw.Draw(img)
        for i, text in enumerate(data["text"]):
            if not text.strip():
                continue
            if pattern.search(text):
                x = data["left"][i]
                y = data["top"][i]
                w = data["width"][i]
                h = data["height"][i]
                region = img.crop((x, y, x + w, y + h))
                img.paste(region.filter(ImageFilter.GaussianBlur(radius=15)), (x, y))
                log(f"  Redacted: '{text[:30]}'")
    except ImportError:
        pass  # pytesseract optional; install Tesseract + pip install pytesseract to enable
    except Exception as e:
        log(f"OCR error: {e}")
    return img


# ════════════════════════════════════════════════════════════════════════════
# Shared helpers (same logic as macOS daemon)

def extract_domain(url):
    try:
        host = urlparse(url).netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        return host
    except Exception:
        return "unknown"


def load_ignored_urls():
    try:
        with open(CONFIG_FILE) as f:
            data = json.load(f)
        return [s.lower() for s in data.get("ignored_urls", [])]
    except Exception:
        return []


def is_social_media(url):
    try:
        host = urlparse(url).netloc.lower().lstrip("www.")
        return host in SOCIAL_DOMAINS or any(
            host.endswith("." + d) or host == d for d in SOCIAL_DOMAINS
        )
    except Exception:
        return False


def is_ignored(url, ignored):
    url_lower = url.lower()
    return any(pattern in url_lower for pattern in ignored)


def title_looks_sensitive(url):
    url_lower = url.lower()
    return any(kw in url_lower for kw in SENSITIVE_TITLE_KEYWORDS)


def _today():
    return datetime.now().strftime("%Y-%m-%d")


def _week():
    from datetime import date
    d = date.today()
    return f"{d.isocalendar()[0]}-W{d.isocalendar()[1]:02d}"


def record_visit(domain):
    visits = load_visits()
    entry = visits.get(domain, {
        "total_visits": 0, "total_time_seconds": 0,
        "last_visit": None, "daily": {}, "weekly": {},
    })
    today, week = _today(), _week()
    entry["total_visits"] += 1
    entry["last_visit"] = datetime.now().isoformat()
    entry.setdefault("daily", {})[today] = {
        "visits": entry["daily"].get(today, {}).get("visits", 0) + 1,
        "time_seconds": entry["daily"].get(today, {}).get("time_seconds", 0),
    }
    entry.setdefault("weekly", {})[week] = {
        "visits": entry["weekly"].get(week, {}).get("visits", 0) + 1,
        "time_seconds": entry["weekly"].get(week, {}).get("time_seconds", 0),
    }
    visits[domain] = entry
    save_visits(visits)
    log(f"Visit #{entry['total_visits']} to {domain}")


def add_domain_time(domain, seconds):
    visits = load_visits()
    entry = visits.get(domain, {
        "total_visits": 0, "total_time_seconds": 0,
        "last_visit": None, "daily": {}, "weekly": {},
    })
    today, week = _today(), _week()
    entry["total_time_seconds"] = entry.get("total_time_seconds", 0) + seconds
    day = entry.setdefault("daily", {}).setdefault(today, {"visits": 0, "time_seconds": 0})
    day["time_seconds"] += seconds
    wk = entry.setdefault("weekly", {}).setdefault(week, {"visits": 0, "time_seconds": 0})
    wk["time_seconds"] += seconds
    visits[domain] = entry
    save_visits(visits)


def blur_addressbar(img):
    h = int(img.height * ADDRESSBAR_FRACTION)
    if h < 1:
        return img
    strip = img.crop((0, 0, img.width, h))
    img.paste(strip.filter(ImageFilter.GaussianBlur(radius=20)), (0, 0))
    return img


def cleanup_old():
    cutoff = time.time() - MAX_AGE_HOURS * 3600
    removed = []
    for f in SHOTS_DIR.glob("*.jpg"):
        if f.stat().st_mtime < cutoff:
            f.unlink()
            removed.append(f.stem)
    if removed:
        log(f"Removed {len(removed)} old screenshots")


def take_screenshot(url, domain):
    now = datetime.now()
    stem = now.strftime("%Y%m%d_%H%M%S")
    final_path = SHOTS_DIR / f"{stem}.jpg"

    try:
        img = grab_screen()
        if img is None:
            return None
        if img.width > MAX_WIDTH:
            ratio = MAX_WIDTH / img.width
            img = img.resize((MAX_WIDTH, int(img.height * ratio)), Image.LANCZOS)

        img = blur_addressbar(img)
        img = try_ocr_and_redact(img)

        draw = ImageDraw.Draw(img)
        font = ImageFont.load_default()
        ts_text = now.strftime("%Y-%m-%d  %H:%M:%S")
        margin, pad = 12, 5
        bbox = draw.textbbox((0, 0), ts_text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        bx, by = margin, img.height - th - pad * 2 - margin
        draw.rectangle([bx - pad, by - pad, bx + tw + pad, by + th + pad], fill=(0, 0, 0, 180))
        draw.text((bx, by), ts_text, font=font, fill=(220, 220, 220))

        SHOTS_DIR.mkdir(parents=True, exist_ok=True)
        img.save(str(final_path), "JPEG", quality=JPEG_QUALITY, optimize=True)

        meta = load_metadata()
        meta[stem] = {"domain": domain}
        save_metadata(meta)

        log(f"Saved: {final_path.name}  ({final_path.stat().st_size // 1024}KB)  [{url[:60]}]")
        return final_path, stem

    except Exception as e:
        log(f"Screenshot error: {e}")
        return None


def main():
    REPO_DIR.mkdir(parents=True, exist_ok=True)
    SHOTS_DIR.mkdir(parents=True, exist_ok=True)

    log("=" * 60)
    log("Hawker daemon starting (Windows)")
    log(f"Data dir: {REPO_DIR}")
    log(f"Poll every {POLL_INTERVAL}s | Screenshot gap {MIN_SHOT_GAP//60}-{MAX_SHOT_GAP//60}m")
    log("=" * 60)

    last_shot_time = 0.0
    next_shot_gap  = random.randint(MIN_SHOT_GAP, MAX_SHOT_GAP)
    last_domain    = None

    while True:
        ignored = load_ignored_urls()
        url     = get_active_browser_url()

        if url:
            on_social     = is_social_media(url)
            ignored_match = is_ignored(url, ignored)
            sensitive     = title_looks_sensitive(url)
            domain        = extract_domain(url) if on_social else None
            now           = time.time()

            if on_social and not ignored_match and not sensitive:
                if domain != last_domain:
                    record_visit(domain)
                last_domain = domain
            else:
                last_domain = None

            if on_social and not ignored_match and not sensitive and domain == last_domain:
                add_domain_time(domain, POLL_INTERVAL)

            if (on_social and not ignored_match and not sensitive
                    and (now - last_shot_time) >= next_shot_gap):
                log(f"On social media: {url[:80]}")
                result = take_screenshot(url, domain)
                if result:
                    cleanup_old()
                    last_shot_time = time.time()
                    next_shot_gap  = random.randint(MIN_SHOT_GAP, MAX_SHOT_GAP)
                    log(f"Next shot in {next_shot_gap // 60}m {next_shot_gap % 60}s")
        else:
            last_domain = None

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
