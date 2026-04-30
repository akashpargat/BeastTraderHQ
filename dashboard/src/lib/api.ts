const API = 'https://api.beast-trader.com'

export async function authFetch(path: string, options: RequestInit = {}) {
  const token = typeof window !== 'undefined' ? localStorage.getItem('beast_token') : ''
  const headers = {
    ...options.headers as Record<string, string>,
    'Authorization': `Bearer ${token}`,
  }
  const res = await fetch(`${API}${path}`, { ...options, headers })
  if (res.status === 401) {
    if (typeof window !== 'undefined') {
      localStorage.removeItem('beast_token')
      window.location.reload()
    }
  }
  return res
}
