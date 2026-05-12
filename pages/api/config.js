import { loadConfig, saveConfig } from '../../lib/storage'
import { isAuthorized } from '../../lib/auth'

export default async function handler(req, res) {
  if (!await isAuthorized(req, res)) return res.status(401).json({ error: 'unauthorized' })

  if (req.method === 'GET') {
    return res.json(await loadConfig())
  }

  if (req.method === 'POST') {
    await saveConfig(req.body)
    return res.json({ ok: true })
  }

  res.status(405).end()
}
