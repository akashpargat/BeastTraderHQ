'use client'
import { useEffect, useState, useCallback } from 'react'

const API = 'https://api.beast-trader.com'

const ACTION_ICONS: Record<string, string> = {
  scalp: '🎯', runner: '🏃', 'dip-buy': '📉', 'dip_buy': '📉',
  protect: '🛡️', sell: '💰', buy: '🟢', stop: '🔴', trail: '📐',
  BUY: '🟢', SELL: '💰', FILL: '✅', CANCEL: '❌',
}

const ACTION_TYPES = ['all', 'buy', 'sell', 'scalp', 'runner', 'dip-buy', 'protect', 'stop']

export default function ActivityPage() {
  const [actions, setActions] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState('all')

  const fetchData = useCallback(() => {
    fetch(`${API}/api/actions?limit=50`)
      .then(r => r.json())
      .then(data => {
        setActions(Array.isArray(data) ? data : data.actions || [])
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [])

  useEffect(() => {
    fetchData()
    const interval = setInterval(fetchData, 30000)
    return () => clearInterval(interval)
  }, [fetchData])

  const filtered = filter === 'all'
    ? actions
    : actions.filter((a: any) => {
        const t = (a.action_type ?? a.type ?? a.side ?? '').toLowerCase()
        return t.includes(filter)
      })

  if (loading) return (
    <div className="space-y-4">
      <div className="h-8 bg-slate-800 rounded animate-pulse w-48" />
      {[...Array(6)].map((_, i) => <div key={i} className="h-16 bg-slate-800 rounded-xl animate-pulse" />)}
    </div>
  )

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">📋 Bot Activity Log</h1>

      {/* Filter buttons */}
      <div className="flex gap-2 flex-wrap">
        {ACTION_TYPES.map(type => (
          <button
            key={type}
            onClick={() => setFilter(type)}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
              filter === type
                ? 'bg-blue-500/20 text-blue-400 border border-blue-500/40'
                : 'bg-slate-800 text-slate-400 border border-slate-700 hover:bg-slate-700'
            }`}
          >
            {ACTION_ICONS[type] || '📋'} {type.toUpperCase()}
          </button>
        ))}
      </div>

      {/* Timeline */}
      <div className="space-y-2">
        {filtered.map((a: any, idx: number) => {
          const type = (a.action_type ?? a.type ?? a.side ?? 'unknown').toLowerCase()
          const icon = ACTION_ICONS[type] || ACTION_ICONS[type.toUpperCase()] || '⚡'
          const time = a.timestamp ?? a.time
          const isBuy = type === 'buy'
          const isSell = type === 'sell'
          const borderCls = isBuy ? 'border-green-500/30' : isSell ? 'border-red-500/30' : 'border-slate-700'
          return (
            <div key={idx} className={`bg-slate-800 rounded-xl p-4 border ${borderCls} flex items-center gap-4`}>
              <span className="text-2xl">{icon}</span>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="font-mono font-bold text-white">{a.symbol}</span>
                  <span className={`text-xs px-2 py-0.5 rounded font-bold ${
                    isBuy ? 'bg-green-500/20 text-green-400' : isSell ? 'bg-red-500/20 text-red-400' : 'bg-slate-700 text-slate-300'
                  }`}>{type.toUpperCase()}</span>
                </div>
                <p className="text-xs text-slate-400 mt-0.5 truncate">{a.reason || a.note || '—'}</p>
              </div>
              <div className="text-right shrink-0">
                <p className="text-sm font-mono text-white">
                  {a.qty && <span>{a.qty} × </span>}
                  {a.price ? `$${Number(a.price).toFixed(2)}` : ''}
                </p>
                {time && (
                  <p className="text-xs text-slate-500">{new Date(time).toLocaleString()}</p>
                )}
              </div>
            </div>
          )
        })}
      </div>

      {filtered.length === 0 && (
        <p className="text-center text-slate-500 py-8">No activity {filter !== 'all' ? `for "${filter}"` : ''}</p>
      )}
      <p className="text-xs text-slate-600 text-center">Auto-refreshes every 30s • Showing last 50 actions</p>
    </div>
  )
}
