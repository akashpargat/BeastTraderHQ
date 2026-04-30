const API = 'https://api.beast-trader.com'

export async function authFetch(path: string, options: RequestInit = {}) {
  const token = typeof window !== 'undefined' ? localStorage.getItem('beast_token') : ''
  const headers: Record<string, string> = {
    ...options.headers as Record<string, string>,
  }
  // Only add auth header if we have a valid token
  if (token && token !== 'null' && token !== 'undefined') {
    headers['Authorization'] = `Bearer ${token}`
  }
  const res = await fetch(`${API}${path}`, { ...options, headers })
  if (res.status === 401) {
    // Don't infinite loop — only clear if we had a token
    if (token && typeof window !== 'undefined') {
      localStorage.removeItem('beast_token')
      localStorage.removeItem('beast_user')
      window.location.reload()
    }
  }
  return res
}
