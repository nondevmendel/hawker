# Hawker

A personal, single-user screenshot logger for social-media research. A small desktop daemon captures the screen on a schedule (or when triggered), uploads to a private gallery on Vercel, and lets you browse / annotate / delete from a web UI gated behind Google sign-in.

Previously named **Log Hawk**; renamed to Hawker in May 2026. The old GitHub Pages gallery at `nondevmendel.github.io/log_hawk/` is kept as a legacy redirect.

- **Gallery:** [hawker-flax.vercel.app/app](https://hawker-flax.vercel.app/app) (Google sign-in + password gate)
- **Install page:** [hawker-flax.vercel.app/install](https://hawker-flax.vercel.app/install) (shows the desktop daemon's API key + download links once you're signed in)

## Architecture

```
┌──────────────────┐     screenshots + metadata     ┌────────────────────┐
│ Desktop daemon   │ ─────────────────────────────▶ │ Vercel (Next.js)   │
│ (macOS / Windows)│         POST /api/upload       │   /api/* endpoints │
│ ~/.screenlog/    │         (x-api-key auth)       │   /app gallery UI  │
└──────────────────┘                                 └─────────┬──────────┘
                                                               │
                                                ┌──────────────┴──────────────┐
                                                ▼                              ▼
                                        Vercel Blob                    Upstash Redis
                                      (screenshot files)        (metadata, visits, config)
```

Web traffic to `/app` and `/api/data` is gated by `proxy.js` (Next.js 16 middleware) which redirects unauthenticated browsers to Google sign-in. Only one Google identity is whitelisted (configured in `pages/api/auth/[...nextauth].js`). The desktop daemon uses an API key instead of a session so it can upload headlessly.

## Repository layout

```
agent_files/        Canonical source for the desktop daemon (daemon.py, menubar.py, hawker.env.example)
mac/                macOS installer (install.command, uninstall.sh, build.sh, setup.py)
windows/            Windows installer (install.bat, build.bat, setup.iss, daemon_win.py, tray_win.py)
log_hawk/           Files staged for the macOS install — install.command copies from here into ~/.screenlog/
rubin/              Rick Rubin sales-call tracker (rubin.py) — standalone helper, separate from Hawker proper
pages/              Next.js routes (app.js gallery, install.js, auth-error.js, index.js)
pages/api/          API: upload, data, delete, config, follow, users, visits, download/[file], auth/[...nextauth]
public/             Static assets (gallery.html is the legacy pre-Next gallery; current UI is pages/app.js)
lib/                storage.js (Blob + Redis), auth.js (NextAuth wiring)
proxy.js            Next.js 16 middleware — gates /app and /api/data
scripts/            One-shot migrations (migrate-old-data.mjs)
```

There is also a top-level `menubar.py` and a parallel set of daemon files under `log_hawk/` — these duplicate `agent_files/`. Consolidating the daemon source into one canonical location is pending cleanup; for now, the install scripts pin which copy is authoritative (macOS uses `log_hawk/`, Windows uses `windows/`).

## Installing the desktop daemon

### macOS

```bash
git clone https://github.com/nondevmendel/hawker.git
cd hawker
bash mac/install.command   # or double-click in Finder
```

The installer:
1. Verifies Python 3.9+ and installs `rumps`, `pillow`, `pyobjc-framework-Quartz`, `pyobjc-framework-Vision`.
2. Copies daemon files from `log_hawk/` into `~/.screenlog/`.
3. Writes `~/.screenlog/hawker.env` with `HAWKER_API_URL` and `HAWKER_API_KEY` (it prompts you for the key — get it from [hawker-flax.vercel.app/install](https://hawker-flax.vercel.app/install)).
4. Registers `~/Library/LaunchAgents/com.mendelrosenberg.screenlog.plist` so the menu bar app starts at login.

**One-time permission:** macOS will block the daemon from capturing the screen until you grant Screen Recording permission. The exact binary that needs the grant is:

```
/Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.9/Resources/Python.app/Contents/MacOS/Python
```

Add it via **System Settings → Privacy & Security → Screen Recording**.

To uninstall:

```bash
bash mac/uninstall.sh
```

### Windows

Two paths:

- **Python mode** (Python 3.10+ already installed): `windows\install.bat` — copies `daemon_win.py` and `tray_win.py` into `%APPDATA%\Hawker\app\`, installs deps from `requirements.txt`, registers a startup shortcut.
- **Standalone installer** (no Python on target machine): `windows\build.bat` produces `Hawker.exe` + `HawkerSetup.exe` via PyInstaller + Inno Setup (`setup.iss`).

## Running / restarting the menu bar app

```bash
# macOS
python3 ~/.screenlog/menubar.py            # one-off
launchctl kickstart -k gui/$(id -u)/com.mendelrosenberg.screenlog   # via LaunchAgent

# Logs
tail -f ~/.screenlog/daemon.log
```

The menu bar icon shows `(o,o)` (green) when recording and `(x,x)` (red) when paused. **Open Dashboard** in the menu opens the gallery.

## Storage

| Layer            | Provider       | What                                         |
| ---------------- | -------------- | -------------------------------------------- |
| Screenshot files | Vercel Blob    | Public store, region `iad1`                  |
| Metadata         | Upstash Redis  | Hash `hawker:metadata`                       |
| Visit log        | Upstash Redis  | Hash `hawker:visits`                         |
| Config           | Upstash Redis  | String `hawker:config` (ignored URLs, etc.)  |

Both are provisioned via the Vercel Marketplace and surface as environment variables on the Vercel project.

## Auth

- **Browser sessions:** Google OAuth via NextAuth.js; the email whitelist is hardcoded in `pages/api/auth/[...nextauth].js`. The app also enforces a password gate (in addition to Google) for an extra layer of protection.
- **Daemon uploads:** A static API key (`HAWKER_API_KEY`) passed in the `x-api-key` header. The key is generated server-side and shown on the install page after sign-in.

## Environment variables (Vercel)

| Var                                  | Purpose                                                |
| ------------------------------------ | ------------------------------------------------------ |
| `NEXTAUTH_URL`                       | Must equal the canonical Vercel alias (currently `https://hawker-flax.vercel.app`) — mismatches break OAuth callbacks. |
| `NEXTAUTH_SECRET`                    | NextAuth signing secret.                               |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | Google OAuth credential.                        |
| `HAWKER_API_KEY`                     | Daemon upload key. Store without surrounding quotes.   |
| `BLOB_READ_WRITE_TOKEN`              | Auto-provisioned by Vercel Blob integration.           |
| `KV_REST_API_URL` / `KV_REST_API_TOKEN` | Auto-provisioned by Upstash Redis integration.      |

## Gotchas

- **Google OAuth redirect URI must match the Vercel alias.** The original credential was created for `https://hawker.vercel.app/api/auth/callback/google`; the actual production alias is `https://hawker-flax.vercel.app`. Add the matching callback in Google Cloud Console → Credentials → OAuth 2.0 Client IDs, or sign-in will fail with a redirect mismatch.
- **`HAWKER_API_KEY` in Vercel env vars must not have surrounding quotes.** Vercel stores the literal string; quotes will be sent verbatim and the daemon's requests will 401.
- **Screen Recording permission on macOS** is granted to the *specific* Python binary listed above. Reinstalling Python from python.org changes the binary path and silently revokes the grant.

## Related notes

- `rubin/rubin.py` — Rick Rubin sales-call tracker. Lives in this repo for convenience but is not part of Hawker proper; it has its own menubar lifecycle.
