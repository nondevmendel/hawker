import { getServerSession } from 'next-auth'
import { authOptions } from '../pages/api/auth/[...nextauth]'
import { resolveApiKey } from './storage'

// Returns { uid, session } or null if not authorized.
// Accepts either a Google session cookie or x-api-key header.
export async function getAuthContext(req, res) {
  const apiKey = req.headers['x-api-key']
  if (apiKey) {
    const uid = await resolveApiKey(apiKey)
    if (uid) return { uid, session: null }
    return null
  }
  const session = await getServerSession(req, res, authOptions)
  if (session?.user?.uid) return { uid: session.user.uid, session }
  return null
}

export async function isAuthorized(req, res) {
  return !!(await getAuthContext(req, res))
}
