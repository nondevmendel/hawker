import { getMetaEntry, setMetaEntry, deleteBlob } from '../../lib/storage'
import { isAuthorized } from '../../lib/auth'

export default async function handler(req, res) {
  if (req.method !== 'POST') return res.status(405).end()
  if (!await isAuthorized(req, res)) return res.status(401).json({ error: 'unauthorized' })

  const { stem, domain } = req.body
  if (!stem) return res.status(400).json({ error: 'missing stem' })

  const entry = await getMetaEntry(stem) || {}

  try {
    const blobUrl = `https://pihra3a3qqrnirxu.public.blob.vercel-storage.com/screenshots/${stem}.jpg`
    await deleteBlob(blobUrl)
  } catch (_) {}

  await setMetaEntry(stem, {
    ...entry,
    domain:     entry.domain || domain || null,
    deleted:    true,
    deleted_at: new Date().toISOString(),
  })

  res.json({ ok: true })
}
