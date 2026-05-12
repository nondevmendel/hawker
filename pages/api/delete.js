import { getMetaEntry, setMetaEntry, deleteBlob } from '../../lib/storage'

export default async function handler(req, res) {
  if (req.method !== 'POST') return res.status(405).end()

  const apiKey = req.headers['x-api-key']
  if (apiKey !== process.env.HAWKER_API_KEY) return res.status(401).json({ error: 'unauthorized' })

  const { stem, domain } = req.body
  if (!stem) return res.status(400).json({ error: 'missing stem' })

  const entry = await getMetaEntry(stem) || {}

  // Delete the blob
  try {
    // Reconstruct the blob URL pattern for deletion
    const blobUrl = `https://pihra3a3qqrnirxu.public.blob.vercel-storage.com/screenshots/${stem}.jpg`
    await deleteBlob(blobUrl)
  } catch (_) {
    // Blob may already be gone; still mark as deleted
  }

  await setMetaEntry(stem, {
    ...entry,
    domain:     entry.domain || domain || null,
    deleted:    true,
    deleted_at: new Date().toISOString(),
  })

  res.json({ ok: true })
}
