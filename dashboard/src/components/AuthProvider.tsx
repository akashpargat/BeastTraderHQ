'use client'
import { createContext, useContext, useState, useEffect, ReactNode } from 'react'

const API = 'https://api.beast-trader.com'

interface AuthContextType {
  isAuthenticated: boolean
  username: string
  token: string
  login: (username: string, password: string) => Promise<{success: boolean, error?: string}>
  logout: () => void
}

const AuthContext = createContext<AuthContextType>({
  isAuthenticated: false, username: '', token: '',
  login: async () => ({success: false}), logout: () => {}
})

export function useAuth() { return useContext(AuthContext) }

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState('')
  const [username, setUsername] = useState('')
  const [isAuthenticated, setIsAuthenticated] = useState(false)
  const [checking, setChecking] = useState(true)

  useEffect(() => {
    const saved = localStorage.getItem('beast_token')
    if (saved) {
      fetch(`${API}/api/auth-status`, {
        headers: { 'Authorization': `Bearer ${saved}` }
      })
        .then(r => r.json())
        .then(d => {
          if (d.authenticated) {
            setToken(saved)
            setUsername(localStorage.getItem('beast_user') || 'akash')
            setIsAuthenticated(true)
          } else {
            localStorage.removeItem('beast_token')
          }
        })
        .catch(() => {})
        .finally(() => setChecking(false))
    } else {
      setChecking(false)
    }
  }, [])

  const login = async (user: string, pass: string) => {
    try {
      const res = await fetch(`${API}/api/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: user, password: pass })
      })
      const data = await res.json()
      if (data.success) {
        setToken(data.token)
        setUsername(data.username)
        setIsAuthenticated(true)
        localStorage.setItem('beast_token', data.token)
        localStorage.setItem('beast_user', data.username)
        return { success: true }
      }
      return { success: false, error: data.error || 'Login failed' }
    } catch (e) {
      return { success: false, error: 'Connection failed' }
    }
  }

  const logout = () => {
    fetch(`${API}/api/logout`, {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${token}` }
    }).catch(() => {})
    setToken('')
    setUsername('')
    setIsAuthenticated(false)
    localStorage.removeItem('beast_token')
    localStorage.removeItem('beast_user')
  }

  if (checking) return (
    <div className="min-h-screen bg-[#0a0a0a] flex items-center justify-center">
      <div className="text-4xl animate-bounce">🦍</div>
    </div>
  )

  if (!isAuthenticated) return <LoginPage onLogin={login} />

  return (
    <AuthContext.Provider value={{ isAuthenticated, username, token, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

function LoginPage({ onLogin }: { onLogin: (u: string, p: string) => Promise<{success: boolean, error?: string}> }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError('')
    const result = await onLogin(username, password)
    if (!result.success) setError(result.error || 'Login failed')
    setLoading(false)
  }

  return (
    <div className="min-h-screen bg-[#0a0a0a] flex items-center justify-center">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <div className="text-6xl mb-3">🦍</div>
          <h1 className="text-2xl font-bold text-white">Beast Terminal V4</h1>
          <p className="text-slate-500 text-sm mt-1">Autonomous AI Trading Engine</p>
        </div>
        <div className="p-6 rounded-2xl" style={{
          background: 'rgba(255,255,255,0.03)',
          backdropFilter: 'blur(12px)',
          border: '1px solid rgba(255,255,255,0.08)'
        }}>
          <form onSubmit={handleSubmit}>
            <div className="mb-4">
              <label className="block text-slate-400 text-xs mb-1.5 uppercase tracking-wider">Username</label>
              <input type="text" value={username} onChange={e => setUsername(e.target.value)}
                className="w-full bg-[#141414] border border-slate-700 rounded-xl px-4 py-3 text-white focus:border-green-500 focus:outline-none transition-colors"
                placeholder="Enter username" autoFocus />
            </div>
            <div className="mb-6">
              <label className="block text-slate-400 text-xs mb-1.5 uppercase tracking-wider">Password</label>
              <input type="password" value={password} onChange={e => setPassword(e.target.value)}
                className="w-full bg-[#141414] border border-slate-700 rounded-xl px-4 py-3 text-white focus:border-green-500 focus:outline-none transition-colors"
                placeholder="Enter password" />
            </div>
            {error && (
              <div className="mb-4 p-3 rounded-xl bg-red-950/50 border border-red-800/50 text-red-400 text-sm text-center">
                {error}
              </div>
            )}
            <button type="submit" disabled={loading}
              className="w-full py-3 rounded-xl font-bold text-black bg-[#00ff88] hover:bg-[#00cc6a] disabled:opacity-50 transition-all transform hover:scale-[1.02]">
              {loading ? '🔐 Authenticating...' : '🦍 Enter Terminal'}
            </button>
          </form>
        </div>
        <p className="text-center text-slate-700 text-xs mt-6">
          🔒 Secured • Rate Limited • Session Expiry 24h
        </p>
      </div>
    </div>
  )
}
