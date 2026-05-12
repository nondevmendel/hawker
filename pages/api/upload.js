import { uploadScreenshot, setMetaEntry } from '../../lib/storage'

export const config = { api: { bodyParser: { sizeLimit: '10mb' } } }

export default async function handler(req, res) {
  if (req.method !== 'POST') return res.status(405).end()

  const apiKey = req.headers['x-api-key']
  if (apiKey !== process.env.HAWKER_API_KEY) return res.status(401).json({ error: 'unauthorized' })

  const { stem, domain, imageBase64 } = req.body
  if (!stem || !imageBase64) return res.status(400).json({ error: 'missing stem or imageBase64' })

  const buffer = Buffer.from(imageBase64, 'base64')
  const url = await uploadScreenshot(stem, buffer)
  await setMetaEntry(stem, { domain: domain || null })

  res.json({ ok: true, url })
}
