import { saveVisitEntry, loadVisits } from '../../lib/storage'
import { getAuthContext } from '../../lib/auth'

export default async function handler(req, res) {
  if (req.method !== 'POST') return res.status(405).end()

  const ctx = await getAuthContext(req, res)
  if (!ctx) return res.status(401).json({ error: 'unauthorized' })

  const { domain, entry, replace } = req.body
  if (!domain || !entry) return res.status(400).json({ error: 'missing domain or entry' })

  // replace: true writes the entry as sent. Used for corrections (e.g. removing
  // Shabbat time), which the max-merge below would otherwise ignore.
  if (replace === true) {
    await saveVisitEntry(ctx.uid, domain, entry)
    return res.json({ ok: true, replaced: true })
  }

  // Merge with existing entry so concurrent calls don't clobber each other
  const existing = await loadVisits(ctx.uid)
  const current = existing[domain] || {
    total_visits: 0, total_time_seconds: 0,
    last_visit: null, daily: {}, weekly: {},
  }

  const merged = {
    total_visits:        Math.max(current.total_visits || 0,        entry.total_visits || 0),
    total_time_seconds:  Math.max(current.total_time_seconds || 0,  entry.total_time_seconds || 0),
    last_visit:          entry.last_visit || current.last_visit,
    daily:               { ...current.daily,   ...entry.daily },
    weekly:              { ...current.weekly,  ...entry.weekly },
  }

  await saveVisitEntry(ctx.uid, domain, merged)
  res.json({ ok: true })
}
