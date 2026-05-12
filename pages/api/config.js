import { loadConfig, saveConfig } from '../../lib/storage'

export default async function handler(req, res) {
  if (req.method === 'GET') {
    const cfg = await loadConfig()
    return res.json(cfg)
  }

  if (req.method === 'POST') {
    const apiKey = req.headers['x-api-key']
    if (apiKey !== process.env.HAWKER_API_KEY) return res.status(401).json({ error: 'unauthorized' })
    await saveConfig(req.body)
    return res.json({ ok: true })
  }

  res.status(405).end()
}
