'use client'
import { useEffect, useState, useCallback } from 'react'
import { authFetch } from '../../lib/api'

export default function SystemPage() {
  const [data, setData] = useState<any>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  const fetchData = useCallback(async () => {
    try {
      const res = await authFetch('/api/system')
      if (res.ok) { setData(await res.json()); setError('') }
      else setError(`API error: ${res.status}`)
    } catch (e: any) { setError(e.message || 'Connection failed') }
    setLoading(false)
  }, [])

  useEffect(() => {
    fetchData()
    const i = setInterval(fetchData, 10000)
    return () => clearInterval(i)
  }, [fetchData])

  if (loading) return <div className="flex items-center justify-center min-h-[50vh]"><div className="text-4xl animate-bounce">🦍</div></div>
  if (error) return <div className="glass p-6 text-center text-red-400">{error}</div>

  const services = [
    { name: 'AI Brain', key: 'ai_brain', icon: '🧠' },
    { name: 'TradingView', key: 'tradingview', icon: '📈' },
    { name: 'Discord', key: 'discord', icon: '💬' },
    { name: 'Dashboard API', key: 'dashboard_api', icon: '🖥️' },
    { name: 'PostgreSQL', key: 'postgresql', icon: '🗄️' },
  ]

  return (
    <div className="fade-in">
      <h1 className="text-2xl font-bold mb-6">⚙️ System Status</h1>
      <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
        {services.map((s, i) => {
          const status = data?.[s.key]?.status ?? data?.services?.[s.key]?.status ?? data?.[s.key] ?? 'unknown'
          const isUp = typeof status === 'string' ? status.toLowerCase().includes('up') || status.toLowerCase().includes('ok') || status.toLowerCase().includes('online') || status.toLowerCase() === 'true' : !!status
          const details = data?.[s.key]?.details ?? data?.services?.[s.key]?.details ?? ''
          return (
            <div key={i} className="glass p-5">
              <div className="flex items-center gap-3 mb-2">
                <span className="text-2xl">{s.icon}</span>
                <span className="font-semibold">{s.name}</span>
                <div className={`ml-auto w-3 h-3 rounded-full ${isUp ? 'bg-[#00ff88]' : 'bg-[#ff4444]'}`} />
              </div>
              <div className="text-sm text-gray-400">{typeof status === 'string' ? status : isUp ? 'Online' : 'Offline'}</div>
              {details && <div className="text-xs text-gray-500 mt-1">{details}</div>}
            </div>
          )
        })}
      </div>
    </div>
  )
}
