import { buildIndex, loadVisits, loadConfig, getProfile } from '../../lib/storage'
import { getAuthContext } from '../../lib/auth'

export default async function handler(req, res) {
  if (req.method !== 'GET') return res.status(405).end()

  const ctx = await getAuthContext(req, res)
  if (!ctx) return res.status(401).json({ error: 'unauthorized' })

  // ?uid= allows viewing another user's log (for following/profiles)
  const targetUid = req.query.uid || ctx.uid

  const [entries, visits, config, profile] = await Promise.all([
    buildIndex(targetUid),
    loadVisits(targetUid),
    loadConfig(targetUid),
    getProfile(targetUid),
  ])

  res.setHeader('Cache-Control', 'no-store')
  res.json({ entries, visits, config, profile, uid: targetUid, isOwner: targetUid === ctx.uid })
}
