import { loadConfig, saveConfig } from '../../lib/storage'
import { getAuthContext } from '../../lib/auth'

export default async function handler(req, res) {
  const ctx = await getAuthContext(req, res)
  if (!ctx) return res.status(401).json({ error: 'unauthorized' })

  if (req.method === 'GET') {
    return res.json(await loadConfig(ctx.uid))
  }
  if (req.method === 'POST') {
    await saveConfig(ctx.uid, req.body)
    return res.json({ ok: true })
  }
  res.status(405).end()
}
