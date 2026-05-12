import { getServerSession } from 'next-auth'
import { authOptions } from '../pages/api/auth/[...nextauth]'

export async function isAuthorized(req, res) {
  if (req.headers['x-api-key'] === process.env.HAWKER_API_KEY) return true
  const session = await getServerSession(req, res, authOptions)
  return !!session
}
