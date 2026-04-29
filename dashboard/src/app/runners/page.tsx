'use client'
import { useEffect, useState, useCallback } from 'react'

const API = 'https://api.beast-trader.com'

function getSession(): { label: string; color: string } {
  const now = new Date()
  const h = now.getHours(), m = now.getMinutes()
  const t = h * 60 + m
  if (t < 570) return { label: 'PRE-MARKET', color: 'text-yellow-400 bg-yellow-400/10' }
  if (t < 960) return { label: 'MARKET OPEN', color: 'text-green-400 bg-green-400/10' }
  if (t < 1200) return { label: 'AFTER-HOURS', color: 'text-blue-400 bg-blue-400/10' }
  return { label: 'CLOSED', color: 'text-slate-400 bg-slate-400/10' }
}

export default function RunnersPage() {
  const [runners, setRunners] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [lastUpdate, setLastUpdate] = useState('')

  const fetchData = useCallback(() => {
    fetch(`${API}/api/runners`)
      .then(r => r.json())
      .then(data => {
        setRunners(Array.isArray(data) ? data : data.runners || [])
        setLastUpdate(new Date().toLocaleTimeString())
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [])

  useEffect(() => {
    fetchData()
    const interval = setInterval(fetchData, 30000)
    return () => clearInterval(interval)
  }, [fetchData])

  const session = getSession()

  if (loading) return (
    <div className="space-y-4">
      <div className="h-8 bg-slate-800 rounded animate-pulse w-48" />
      {[...Array(5)].map((_, i) => <div key={i} className="h-16 bg-slate-800 rounded-xl animate-pulse" />)}
    </div>
  )

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">🏃 Runner Tracker</h1>
        <div className="flex items-center gap-3">
          <span className={`text-xs font-bold px-3 py-1 rounded-full ${session.color}`}>{session.label}</span>
          <span className="text-xs text-slate-500">Updated {lastUpdate}</span>
        </div>
      </div>

      <div className="bg-slate-800 rounded-xl border border-slate-700 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-700 text-slate-400 text-xs uppercase">
              <th className="text-left px-4 py-3">Symbol</th>
              <th className="text-right px-4 py-3">Price</th>
              <th className="text-right px-4 py-3">Change %</th>
              <th className="text-right px-4 py-3">Prev Close</th>
            </tr>
          </thead>
          <tbody>
            {runners.map((r: any) => {
              const positive = (r.change_pct ?? r.change_percent ?? 0) >= 0
              return (
                <tr key={r.symbol} className="border-b border-slate-700/50 hover:bg-slate-700/30 transition-colors">
                  <td className="px-4 py-3 font-mono font-bold text-white">{r.symbol}</td>
                  <td className="px-4 py-3 text-right font-mono">${(r.price ?? r.current_price ?? 0).toFixed(2)}</td>
                  <td className={`px-4 py-3 text-right font-mono font-bold ${positive ? 'text-green-400' : 'text-red-400'}`}>
                    {positive ? '+' : ''}{(r.change_pct ?? r.change_percent ?? 0).toFixed(2)}%
                  </td>
                  <td className="px-4 py-3 text-right font-mono text-slate-400">${(r.prev_close ?? 0).toFixed(2)}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
        {runners.length === 0 && (
          <p className="text-center text-slate-500 py-8">No active runners</p>
        )}
      </div>
      <p className="text-xs text-slate-600 text-center">Auto-refreshes every 30s</p>
    </div>
  )
}
