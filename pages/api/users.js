import { getAllUsers, getProfile, buildIndex, isFollowing } from '../../lib/storage'
import { getAuthContext } from '../../lib/auth'

export default async function handler(req, res) {
  if (req.method !== 'GET') return res.status(405).end()

  const ctx = await getAuthContext(req, res)
  if (!ctx) return res.status(401).json({ error: 'unauthorized' })

  const uids = await getAllUsers()

  const users = await Promise.all(
    uids.map(async uid => {
      const profile = await getProfile(uid)
      if (!profile) return null
      const entries = await buildIndex(uid)
      const live = entries.filter(e => !e.deleted)
      const following = await isFollowing(ctx.uid, uid)
      return {
        uid,
        name:       profile.name,
        picture:    profile.picture,
        username:   profile.username,
        isMe:       uid === ctx.uid,
        following,
        shotCount:  live.length,
        lastShotAt: live[0]?.iso || null,
      }
    })
  )

  res.setHeader('Cache-Control', 'no-store')
  res.json({ users: users.filter(Boolean) })
}
