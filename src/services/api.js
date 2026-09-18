import { getBackendUrl } from '../config.js'

async function req(p, o) {
  const opts = o || {}
  const r = await fetch(getBackendUrl() + p, {
    ...opts,
    headers: { Accept: 'application/json', ...(opts.headers || {}) },
  })
  if (!r.ok) {
    let d = ''
    try { d = await r.text() } catch (e) {}
    const tail = d ? ': ' + d.slice(0, 200) : ''
    throw new Error(r.status + ' ' + r.statusText + tail)
  }
  const ct = r.headers.get('content-type') || ''
  return ct.includes('json') ? r.json() : r.text()
}

export const api = {
  health: () => req('/health'),
  conversations: () => req('/conversations'),
  turns: (id) => req('/turns/' + encodeURIComponent(id)),
  search: (q) => req('/search?q=' + encodeURIComponent(q)),
  jevJudge: (payload) => req('/jev/judge', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }),
  jevCalls: () => req('/jev/calls'),
  auditRuns: () => req('/audit/runs'),
  auditLatest: () => req('/audit/latest'),
}
