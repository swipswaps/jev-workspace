const K = 'jev-backend-url'

export function getBackendUrl() {
  try {
    const s = localStorage.getItem(K)
    if (s) return s.replace(/\/+$/, '')
  } catch (e) {}
  if (import.meta.env.VITE_API_BASE) {
    return String(import.meta.env.VITE_API_BASE).replace(/\/+$/, '')
  }
  return 'http://localhost:8787'
}

export function setBackendUrl(u) {
  try {
    localStorage.setItem(K, String(u).replace(/\/+$/, ''))
  } catch (e) {}
}
