'use client'
import { useEffect, useState, useCallback } from 'react'

const API = 'https://api.beast-trader.com'

const STRATEGY_COLORS: Record<string, string> = {
  scalp: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
  runner: 'bg-green-500/20 text-green-400 border-green-500/30',
  dip: 'bg-orange-500/20 text-orange-400 border-orange-500/30',
  protect: 'bg-purple-500/20 text-purple-400 border-purple-500/30',
  earnings: 'bg-amber-500/20 text-amber-400 border-amber-500/30',
  manual: 'bg-slate-500/20 text-slate-400 border-slate-500/30',
}

const FILTERS = ['ALL', 'SCALP', 'RUNNER', 'DIP', 'PROTECT', 'EARNINGS']

function getStrategyStyle(name: string) {
  const n = (name || '').toLowerCase()
  for (const key of Object.keys(STRATEGY_COLORS)) {
    if (n.includes(key)) return STRATEGY_COLORS[key]
  }
  return STRATEGY_COLORS.manual
}

function extractStrategyName(d: any): string {
  if (d.strategy) return d.strategy
  const cid = d.client_order_id || d.reason || ''
  if (cid.includes('scalp')) return 'Scalp'
  if (cid.includes('runner')) return 'Runner'
  if (cid.includes('dip')) return 'Dip'
  if (cid.includes('protect')) return 'Protect'
  if (cid.includes('earn')) return 'Earnings'
  return cid.split('-')[0] || 'Manual'
}

export default function DecisionsPage() {
  const [decisions, setDecisions] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState('ALL')

  const fetchData = useCallback(() => {
    fetch(`${API}/api/decision-log`)
      .then(r => r.json())
      .then(data => {
        setDecisions(data.decisions || data.log || [])
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [])

  useEffect(() => {
    fetchData()
    const interval = setInterval(fetchData, 30000)
    return () => clearInterval(interval)
  }, [fetchData])

  const filtered = filter === 'ALL'
    ? decisions
    : decisions.filter((d: any) => extractStrategyName(d).toLowerCase().includes(filter.toLowerCase()))

  if (loading) return (
    <div className="space-y-4">
      <div className="h-8 bg-slate-800 rounded animate-pulse w-48" />
      {[...Array(8)].map((_, i) => <div key={i} className="h-16 bg-slate-800 rounded-xl animate-pulse" />)}
    </div>
  )

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">🎯 Decision History</h1>
        <span className="text-xs text-slate-500">{decisions.length} decisions</span>
      </div>

      {/* Filter tabs */}
      <div className="flex gap-2 flex-wrap">
        {FILTERS.map(f => (
          <button key={f} onClick={() => setFilter(f)}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
              filter === f
                ? 'bg-blue-500/20 text-blue-400 border border-blue-500/40'
                : 'bg-slate-800 text-slate-400 border border-slate-700 hover:bg-slate-700'
            }`}>
            {f}
          </button>
        ))}
      </div>

      {/* Timeline */}
      <div className="space-y-2">
        {filtered.map((d: any, idx: number) => {
          const side = (d.side || d.type || '').toLowerCase()
          const isBuy = side === 'buy'
          const strategy = extractStrategyName(d)
          const stratStyle = getStrategyStyle(strategy)
          const time = d.time || d.timestamp || d.filled_at || ''

          return (
            <div key={idx} className="bg-slate-800 rounded-xl p-4 border border-slate-700 flex items-start gap-4">
              {/* Timeline dot */}
              <div className="flex flex-col items-center pt-1">
                <div className={`w-3 h-3 rounded-full ${isBuy ? 'bg-green-400' : 'bg-red-400'}`} />
                {idx < filtered.length - 1 && <div className="w-0.5 h-full bg-slate-700 mt-1" />}
              </div>

              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-mono font-bold text-white text-lg">{d.symbol}</span>
                  <span className={`text-xs font-bold px-2 py-0.5 rounded ${
                    isBuy ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'
                  }`}>
                    {isBuy ? '🟢 BUY' : '🔴 SELL'}
                  </span>
                  <span className={`text-xs px-2 py-0.5 rounded border ${stratStyle}`}>{strategy}</span>
                  {d.order_type && (
                    <span className="text-xs text-slate-500 bg-slate-700/50 px-2 py-0.5 rounded">{d.order_type}</span>
                  )}
                </div>
                <div className="flex gap-4 mt-1 text-xs text-slate-400">
                  <span>{d.qty} shares</span>
                  <span>@ ${Number(d.price || d.filled_avg_price || 0).toFixed(2)}</span>
                  {d.reason && <span className="truncate text-slate-500">{d.reason}</span>}
                </div>
              </div>

              <div className="text-right shrink-0">
                {time && (
                  <p className="text-xs text-slate-500">{new Date(time).toLocaleString()}</p>
                )}
              </div>
            </div>
          )
        })}
      </div>

      {filtered.length === 0 && (
        <div className="bg-slate-800 rounded-xl p-8 border border-slate-700 text-center">
          <p className="text-slate-400">No decisions {filter !== 'ALL' ? `for "${filter}"` : 'recorded yet'}</p>
        </div>
      )}
      <p className="text-xs text-slate-600 text-center">Auto-refreshes every 30s</p>
    </div>
  )
}
