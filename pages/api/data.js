import { buildIndex, loadVisits, loadConfig } from '../../lib/storage'

export default async function handler(req, res) {
  if (req.method !== 'GET') return res.status(405).end()

  const [entries, visits, config] = await Promise.all([
    buildIndex(),
    loadVisits(),
    loadConfig(),
  ])

  res.setHeader('Cache-Control', 'no-store')
  res.json({ entries, visits, config })
}
