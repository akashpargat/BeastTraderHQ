'use client'
import { useEffect, useState, useCallback } from 'react'
import { authFetch } from '../../lib/api'

export default function ConfigPage() {
  const [configs, setConfigs] = useState<any[]>([])
  const [botState, setBotState] = useState<any>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState('')

  const fetchData = useCallback(async () => {
    try {
      const [cRes, sRes] = await Promise.all([
        authFetch('/api/v4/config').catch(() => null),
        authFetch('/api/v4/dashboard-state').catch(() => null),
      ])
      if (cRes?.ok) setConfigs(await cRes.json())
      if (sRes?.ok) setBotState(await sRes.json())
      setError('')
    } catch (e: any) { setError(e.message) }
    setLoading(false)
  }, [])

  useEffect(() => { fetchData() }, [fetchData])

  const updateConfig = async (key: string, value: any) => {
    setSaving(key)
    try {
      await authFetch('/api/v4/config', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ key, value })
      })
      fetchData()
    } catch (e: any) { setError(e.message) }
    setSaving('')
  }

  const toggleKillSwitch = async () => {
    const current = botState?.kill_switch ?? false
    await authFetch('/api/v4/kill-switch', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled: !current })
    })
    fetchData()
  }

  const setMode = async (mode: string) => {
    await authFetch('/api/v4/bot-mode', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode })
    })
    fetchData()
  }

  if (loading) return <div className="flex items-center justify-center min-h-[50vh]"><div className="text-4xl animate-bounce">🦍</div></div>

  const categories = [...new Set(configs.map((c: any) => c?.category || 'general'))]

  return (
    <div className="fade-in space-y-6">
      <h1 className="text-2xl font-bold">🔧 Bot Config</h1>
      {error && <div className="glass p-3 text-red-400 text-sm">{error}</div>}

      {/* Control Panel */}
      <div className="glass p-4">
        <h2 className="text-lg font-semibold mb-3">🎮 Control Panel</h2>
        <div className="flex gap-4 items-center flex-wrap">
          <button onClick={toggleKillSwitch}
            className={`px-6 py-3 rounded-lg font-bold text-lg transition ${botState?.kill_switch ? 'bg-red-600 text-white animate-pulse' : 'bg-green-600/20 text-green-400 border border-green-600'}`}>
            {botState?.kill_switch ? '🛑 KILL SWITCH ON — Click to Resume' : '✅ Bot Active — Kill Switch OFF'}
          </button>
          <div className="flex gap-2">
            {['active', 'paused', 'monitor_only'].map(mode => (
              <button key={mode} onClick={() => setMode(mode)}
                className={`px-3 py-2 rounded text-sm transition ${botState?.mode === mode ? 'bg-blue-600 text-white' : 'bg-white/5 text-gray-400 hover:bg-white/10'}`}>
                {mode.replace('_', ' ').toUpperCase()}
              </button>
            ))}
          </div>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-4 text-sm">
          <div className="text-gray-400">Cycle: <span className="text-white font-mono">{botState?.cycle_count ?? '?'}</span></div>
          <div className="text-gray-400">Trades Today: <span className="text-white font-mono">{botState?.trades_today ?? '?'}</span></div>
          <div className="text-gray-400">Errors: <span className="text-white font-mono">{botState?.errors_today ?? 0}</span></div>
          <div className="text-gray-400">Notifications: <span className="text-white font-mono">{botState?.unread_notifications ?? 0}</span></div>
        </div>
      </div>

      {/* Config by category */}
      {categories.map(cat => (
        <div key={cat} className="glass p-4">
          <h2 className="text-lg font-semibold mb-3 capitalize">{cat === 'risk' ? '⚠️' : cat === 'strategy' ? '📊' : cat === 'tv' ? '📺' : cat === 'timing' ? '⏰' : cat === 'control' ? '🎮' : '⚙️'} {cat}</h2>
          <div className="space-y-2">
            {configs.filter((c: any) => (c?.category || 'general') === cat).map((c: any) => (
              <div key={c.key} className="flex items-center justify-between py-2 border-b border-white/5">
                <div>
                  <span className="font-mono text-sm">{c.key}</span>
                  {c.description && <div className="text-xs text-gray-500">{c.description}</div>}
                </div>
                <div className="flex items-center gap-2">
                  {c.data_type === 'boolean' ? (
                    <button onClick={() => updateConfig(c.key, c.value === true || c.value === 'true' ? false : true)}
                      className={`px-3 py-1 rounded text-sm ${c.value === true || c.value === 'true' ? 'bg-green-600 text-white' : 'bg-red-600/30 text-red-400'}`}>
                      {c.value === true || c.value === 'true' ? 'ON' : 'OFF'}
                    </button>
                  ) : (
                    <input type={c.data_type === 'number' ? 'number' : 'text'}
                      defaultValue={c.value} onBlur={e => updateConfig(c.key, e.target.value)}
                      className="bg-white/5 border border-white/10 rounded px-3 py-1 text-white text-sm w-24 text-right" />
                  )}
                  {saving === c.key && <span className="text-xs text-yellow-400">saving...</span>}
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}
