// One-shot migration: uploads old screenshots → Vercel Blob, writes metadata → Redis
// Usage: node --env-file=.env.local scripts/migrate-old-data.mjs

import { readFileSync, readdirSync } from 'fs'
import { put } from '@vercel/blob'
import { Redis } from '@upstash/redis'

const SCREENSHOTS_DIR = '/Users/mendelrosenberg/.screenlog/docs/screenshots'
const METADATA_FILE   = `${SCREENSHOTS_DIR}/metadata.json`
const USER_EMAIL      = 'mmr305@gmail.com'

const r = new Redis({
  url:   process.env.KV_REST_API_URL,
  token: process.env.KV_REST_API_TOKEN,
})

const uid = await r.get(`email:${USER_EMAIL}`)
if (!uid) {
  console.error('User not found in Redis for', USER_EMAIL)
  console.error('Log in at https://hawker-flax.vercel.app first to create your account, then re-run.')
  process.exit(1)
}
console.log('Migrating for uid:', uid)

const metadata = JSON.parse(readFileSync(METADATA_FILE, 'utf8'))

const files = readdirSync(SCREENSHOTS_DIR).filter(f => f.endsWith('.jpg'))
console.log(`Found ${files.length} screenshot files`)

for (const file of files) {
  const stem = file.replace('.jpg', '')
  const meta = metadata[stem] || {}
  if (meta.deleted) {
    console.log(`  skip (deleted): ${stem}`)
    continue
  }

  const buffer = readFileSync(`${SCREENSHOTS_DIR}/${file}`)
  const blob = await put(`u/${uid}/screenshots/${stem}.jpg`, buffer, {
    access: 'public',
    contentType: 'image/jpeg',
  })
  console.log(`  uploaded: ${stem} → ${blob.url}`)

  // Write metadata entry
  const entry = { domain: meta.domain || null }
  await r.hset(`u:${uid}:meta`, { [stem]: JSON.stringify(entry) })
}

console.log('Done.')
