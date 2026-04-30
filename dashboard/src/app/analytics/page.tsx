'use client'
import { useEffect, useState, useCallback } from 'react'
import { authFetch } from '../../lib/api'

export default function AnalyticsPage() {
  const [data, setData] = useState<any>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  const fetchData = useCallback(async () => {
    try {
      const res = await authFetch('/api/analytics')
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

  const totalTrades = data?.total_trades ?? 0
  if (totalTrades === 0) return (
    <div className="fade-in">
      <h1 className="text-2xl font-bold mb-6">📊 Analytics</h1>
      <div className="glass p-12 text-center text-gray-500"><div className="text-4xl mb-2">📭</div>No data yet</div>
    </div>
  )

  return (
    <div className="fade-in">
      <h1 className="text-2xl font-bold mb-6">📊 Analytics</h1>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="glass p-6 text-center">
          <div className="text-xs text-gray-400 mb-1">Total Trades</div>
          <div className="text-3xl font-bold">{totalTrades}</div>
        </div>
        <div className="glass p-6 text-center">
          <div className="text-xs text-gray-400 mb-1">Win Rate</div>
          <div className="text-3xl font-bold text-[#00ff88]">{Number(data?.win_rate ?? 0).toFixed(1)}%</div>
        </div>
        <div className="glass p-6 text-center">
          <div className="text-xs text-gray-400 mb-1">Total P&L</div>
          <div className={`text-3xl font-bold ${(data?.total_pnl ?? 0) >= 0 ? 'text-[#00ff88]' : 'text-[#ff4444]'}`}>
            ${Number(data?.total_pnl ?? 0).toFixed(2)}
          </div>
        </div>
        <div className="glass p-6 text-center">
          <div className="text-xs text-gray-400 mb-1">Best / Worst Day</div>
          <div className="text-sm">
            <span className="text-[#00ff88]">+${Number(data?.best_day ?? 0).toFixed(2)}</span>
            {' / '}
            <span className="text-[#ff4444]">${Number(data?.worst_day ?? 0).toFixed(2)}</span>
          </div>
        </div>
      </div>
    </div>
  )
}
