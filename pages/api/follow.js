import { followUser, unfollowUser, getFollowing, isFollowing, getProfile } from '../../lib/storage'
import { getAuthContext } from '../../lib/auth'

export default async function handler(req, res) {
  const ctx = await getAuthContext(req, res)
  if (!ctx) return res.status(401).json({ error: 'unauthorized' })

  // GET /api/follow — list who I follow with their profiles
  if (req.method === 'GET') {
    const uids = await getFollowing(ctx.uid)
    const profiles = await Promise.all(
      uids.map(async uid => {
        const p = await getProfile(uid)
        const following = await isFollowing(ctx.uid, uid)
        return p ? { uid, ...p, following } : null
      })
    )
    return res.json({ following: profiles.filter(Boolean) })
  }

  // POST /api/follow — { uid, action: 'follow'|'unfollow' }
  if (req.method === 'POST') {
    const { uid: targetUid, action } = req.body
    if (!targetUid || !action) return res.status(400).json({ error: 'missing uid or action' })
    if (targetUid === ctx.uid) return res.status(400).json({ error: 'cannot follow yourself' })
    if (action === 'follow') await followUser(ctx.uid, targetUid)
    else await unfollowUser(ctx.uid, targetUid)
    return res.json({ ok: true })
  }

  res.status(405).end()
}
