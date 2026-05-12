import { getMetaEntry, setMetaEntry, deleteBlob } from '../../lib/storage'
import { getAuthContext } from '../../lib/auth'

export default async function handler(req, res) {
  if (req.method !== 'POST') return res.status(405).end()

  const ctx = await getAuthContext(req, res)
  if (!ctx) return res.status(401).json({ error: 'unauthorized' })

  const { stem, domain } = req.body
  if (!stem) return res.status(400).json({ error: 'missing stem' })

  const entry = await getMetaEntry(ctx.uid, stem) || {}

  // Delete blob (URL pattern is now per-user)
  const blobUrl = `https://pihra3a3qqrnirxu.public.blob.vercel-storage.com/u/${ctx.uid}/screenshots/${stem}.jpg`
  await deleteBlob(blobUrl)

  await setMetaEntry(ctx.uid, stem, {
    ...entry,
    domain:     entry.domain || domain || null,
    deleted:    true,
    deleted_at: new Date().toISOString(),
  })

  res.json({ ok: true })
}
