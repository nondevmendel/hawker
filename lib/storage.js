import { put, del, list } from '@vercel/blob'
import { Redis } from '@upstash/redis'

let _redis = null
function redis() {
  if (!_redis) _redis = Redis.fromEnv()
  return _redis
}

// ── key helpers ──────────────────────────────────────────────────────────────
const k = {
  meta:    uid => `u:${uid}:meta`,      // hash stem→JSON
  visits:  uid => `u:${uid}:visits`,    // hash domain→JSON
  config:  uid => `u:${uid}:config`,    // string JSON
  apikey:  uid => `u:${uid}:apikey`,    // string
  profile: uid => `u:${uid}:profile`,   // string JSON {email,name,picture,username}
  follows: uid => `u:${uid}:follows`,   // set of uids
  byKey:   key => `apikey:${key}`,      // string → uid
  byEmail: em  => `email:${em}`,        // string → uid
  allUsers:    'hawker:users',           // set of all uids
}

// ── user management ──────────────────────────────────────────────────────────

export async function getOrCreateUser({ sub, email, name, picture }) {
  const r = redis()
  // Check if user exists
  let uid = await r.get(k.byEmail(email))
  if (uid) {
    // Update profile in case name/picture changed
    const profile = await getProfile(uid)
    await r.set(k.profile(uid), JSON.stringify({ ...profile, name, picture }))
    return uid
  }
  // New user
  uid = sub
  const apiKey = `hawk-${uid}-${randomHex(16)}`
  await r.set(k.profile(uid), JSON.stringify({ email, name, picture, username: emailToUsername(email) }))
  await r.set(k.apikey(uid), apiKey)
  await r.set(k.byKey(apiKey), uid)
  await r.set(k.byEmail(email), uid)
  await r.sadd(k.allUsers, uid)
  return uid
}

export async function getProfile(uid) {
  const raw = await redis().get(k.profile(uid))
  if (!raw) return null
  return typeof raw === 'string' ? JSON.parse(raw) : raw
}

export async function getUserApiKey(uid) {
  return await redis().get(k.apikey(uid))
}

export async function resolveApiKey(apiKey) {
  return await redis().get(k.byKey(apiKey))
}

export async function getAllUsers() {
  const uids = await redis().smembers(k.allUsers)
  if (!uids || !uids.length) return []
  return uids
}

// ── follow system ─────────────────────────────────────────────────────────────

export async function followUser(fromUid, toUid) {
  await redis().sadd(k.follows(fromUid), toUid)
}

export async function unfollowUser(fromUid, toUid) {
  await redis().srem(k.follows(fromUid), toUid)
}

export async function getFollowing(uid) {
  const members = await redis().smembers(k.follows(uid))
  return members || []
}

export async function isFollowing(fromUid, toUid) {
  return await redis().sismember(k.follows(fromUid), toUid)
}

// ── blob ──────────────────────────────────────────────────────────────────────

export async function uploadScreenshot(uid, stem, buffer, contentType = 'image/jpeg') {
  const blob = await put(`u/${uid}/screenshots/${stem}.jpg`, buffer, {
    access: 'public',
    contentType,
    allowOverwrite: true,
  })
  return blob.url
}

export async function deleteBlob(url) {
  try { await del(url) } catch (_) {}
}

export async function listUserBlobs(uid) {
  const { blobs } = await list({ prefix: `u/${uid}/screenshots/` })
  return blobs
}

// ── metadata ──────────────────────────────────────────────────────────────────

export async function loadMetadata(uid) {
  const raw = await redis().hgetall(k.meta(uid))
  if (!raw) return {}
  const out = {}
  for (const [key, v] of Object.entries(raw)) {
    out[key] = typeof v === 'string' ? JSON.parse(v) : v
  }
  return out
}

export async function setMetaEntry(uid, stem, entry) {
  await redis().hset(k.meta(uid), { [stem]: JSON.stringify(entry) })
}

export async function getMetaEntry(uid, stem) {
  const raw = await redis().hget(k.meta(uid), stem)
  if (!raw) return null
  return typeof raw === 'string' ? JSON.parse(raw) : raw
}

// ── visits ────────────────────────────────────────────────────────────────────

export async function loadVisits(uid) {
  const raw = await redis().hgetall(k.visits(uid))
  if (!raw) return {}
  const out = {}
  for (const [key, v] of Object.entries(raw)) {
    out[key] = typeof v === 'string' ? JSON.parse(v) : v
  }
  return out
}

export async function saveVisitEntry(uid, domain, entry) {
  await redis().hset(k.visits(uid), { [domain]: JSON.stringify(entry) })
}

// ── config ────────────────────────────────────────────────────────────────────

export async function loadConfig(uid) {
  const raw = await redis().get(k.config(uid))
  if (!raw) return { ignored_urls: [] }
  return typeof raw === 'string' ? JSON.parse(raw) : raw
}

export async function saveConfig(uid, cfg) {
  await redis().set(k.config(uid), JSON.stringify(cfg))
}

// ── index builder ─────────────────────────────────────────────────────────────

export async function buildIndex(uid) {
  const [blobs, meta] = await Promise.all([listUserBlobs(uid), loadMetadata(uid)])

  const stemToUrl = {}
  for (const b of blobs) {
    const stem = b.pathname.split('/screenshots/')[1]?.replace('.jpg', '')
    if (stem) stemToUrl[stem] = b.url
  }

  const entries = []

  for (const [stem, url] of Object.entries(stemToUrl)) {
    const dt = parseStem(stem)
    if (!dt) continue
    const m = meta[stem] || {}
    if (m.deleted) continue
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

  for (const [stem, m] of Object.entries(meta)) {
    if (m.deleted && !stemToUrl[stem]) {
      const dt = parseStem(stem)
      if (!dt) continue
      entries.push({
        stem, url: null,
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
  if (!stem) return null
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

function emailToUsername(email) {
  return email.split('@')[0].replace(/[^a-z0-9_]/gi, '_').toLowerCase()
}

function randomHex(n) {
  return Array.from({ length: n }, () => Math.floor(Math.random() * 16).toString(16)).join('')
}
