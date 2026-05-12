import { readFileSync } from 'fs'
import { join } from 'path'
import { isAuthorized } from '../../../lib/auth'

const ALLOWED = new Set(['menubar.py', 'daemon.py'])

export default async function handler(req, res) {
  if (!await isAuthorized(req, res)) return res.status(401).end()

  const { file } = req.query
  if (!ALLOWED.has(file)) return res.status(404).end()

  try {
    const content = readFileSync(join(process.cwd(), 'agent_files', file))
    res.setHeader('Content-Type', 'text/x-python')
    res.setHeader('Content-Disposition', `attachment; filename="${file}"`)
    res.send(content)
  } catch {
    res.status(404).end()
  }
}
