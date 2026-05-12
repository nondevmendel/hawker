import { put, del, list } from '@vercel/blob'
import { Redis } from '@upstash/redis'

let _redis = null
function redis() {
  if (!_redis) _redis = Redis.fromEnv()
  return _redis
}

// ── keys ────────────────────────────────────────────────────────────────────
const METADATA_KEY = 'hawker:metadata'   // hash: stem → JSON string
const VISITS_KEY   = 'hawker:visits'     // hash: domain → JSON string
const CONFIG_KEY   = 'hawker:config'     // string: JSON {ignored_urls:[]}

// ── blob ─────────────────────────────────────────────────────────────────────

export async function uploadScreenshot(stem, buffer, contentType = 'image/jpeg') {
  const blob = await put(`screenshots/${stem}.jpg`, buffer, {
    access: 'public',
    contentType,
  })
  return blob.url
}

export async function deleteBlob(url) {
  await del(url)
}

export async function listBlobs() {
  const { blobs } = await list({ prefix: 'screenshots/' })
  return blobs
}

// ── metadata ─────────────────────────────────────────────────────────────────

export async function loadMetadata() {
  const raw = await redis().hgetall(METADATA_KEY)
  if (!raw) return {}
  const out = {}
  for (const [k, v] of Object.entries(raw)) {
    out[k] = typeof v === 'string' ? JSON.parse(v) : v
  }
  return out
}

export async function setMetaEntry(stem, entry) {
  await redis().hset(METADATA_KEY, { [stem]: JSON.stringify(entry) })
}

export async function getMetaEntry(stem) {
  const raw = await redis().hget(METADATA_KEY, stem)
  if (!raw) return null
  return typeof raw === 'string' ? JSON.parse(raw) : raw
}

// ── visits ────────────────────────────────────────────────────────────────────

export async function loadVisits() {
  const raw = await redis().hgetall(VISITS_KEY)
  if (!raw) return {}
  const out = {}
  for (const [k, v] of Object.entries(raw)) {
    out[k] = typeof v === 'string' ? JSON.parse(v) : v
  }
  return out
}

export async function saveVisitEntry(domain, entry) {
  await redis().hset(VISITS_KEY, { [domain]: JSON.stringify(entry) })
}

// ── config ────────────────────────────────────────────────────────────────────

export async function loadConfig() {
  const raw = await redis().get(CONFIG_KEY)
  if (!raw) return { ignored_urls: [] }
  return typeof raw === 'string' ? JSON.parse(raw) : raw
}

export async function saveConfig(cfg) {
  await redis().set(CONFIG_KEY, JSON.stringify(cfg))
}

// ── index builder ─────────────────────────────────────────────────────────────

export async function buildIndex() {
  const [blobs, meta] = await Promise.all([listBlobs(), loadMetadata()])

  const stemToUrl = {}
  for (const b of blobs) {
    const stem = b.pathname.replace('screenshots/', '').replace('.jpg', '')
    stemToUrl[stem] = b.url
  }

  const entries = []

  for (const [stem, url] of Object.entries(stemToUrl)) {
    const dt = parseStem(stem)
    if (!dt) continue
    const m = meta[stem] || {}
    entries.push({
      stem,
      url,
      iso:     dt.toISOString(),
      display: fmtDisplay(dt),
      date:    fmtDate(dt),
      domain:  m.domain || null,
      deleted: false,
    })
  }

  // tombstones: deleted entries with no blob
  for (const [stem, m] of Object.entries(meta)) {
    if (m.deleted && !stemToUrl[stem]) {
      const dt = parseStem(stem)
      if (!dt) continue
      entries.push({
        stem,
        url:        null,
        iso:        dt.toISOString(),
        display:    fmtDisplay(dt),
        date:       fmtDate(dt),
        domain:     m.domain || null,
        deleted:    true,
        deleted_at: m.deleted_at || null,
      })
    }
  }

  entries.sort((a, b) => b.iso.localeCompare(a.iso))
  return entries
}

// ── helpers ───────────────────────────────────────────────────────────────────

function parseStem(stem) {
  const m = stem.match(/^(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})$/)
  if (!m) return null
  return new Date(+m[1], +m[2]-1, +m[3], +m[4], +m[5], +m[6])
}

function fmtDisplay(dt) {
  return dt.toLocaleString('en-US', {
    month: 'short', day: 'numeric', year: 'numeric',
    hour: 'numeric', minute: '2-digit', second: '2-digit', hour12: true,
  })
}

function fmtDate(dt) {
  return dt.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' })
}
