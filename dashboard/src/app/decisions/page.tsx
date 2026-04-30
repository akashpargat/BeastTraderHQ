'use client'
import { useEffect, useState, useCallback } from 'react'

const API = 'https://api.beast-trader.com'

const STRATEGY_META: Record<string, { label: string; color: string; border: string; badge: string }> = {
  scalp:   { label: 'Auto-Scalp',  color: '#3b82f6', border: 'border-l-blue-500',   badge: 'bg-blue-500/15 text-blue-400 border border-blue-500/30' },
  runner:  { label: 'Runner',      color: '#00ff88', border: 'border-l-green-500',   badge: 'bg-green-500/15 text-green-400 border border-green-500/30' },
  dip:     { label: 'Akash Dip',   color: '#f97316', border: 'border-l-orange-500',  badge: 'bg-orange-500/15 text-orange-400 border border-orange-500/30' },
  claude:  { label: 'Claude AI',   color: '#a855f7', border: 'border-l-purple-500',  badge: 'bg-purple-500/15 text-purple-400 border border-purple-500/30' },
  gpt:     { label: 'GPT-4o',      color: '#06b6d4', border: 'border-l-cyan-500',    badge: 'bg-cyan-500/15 text-cyan-400 border border-cyan-500/30' },
  manual:  { label: 'Manual',      color: '#6b7280', border: 'border-l-gray-500',    badge: 'bg-slate-500/15 text-slate-400 border border-slate-500/30' },
}

const FILTERS = ['ALL', 'SCALP', 'RUNNER', 'DIP', 'CLAUDE', 'GPT', 'MANUAL']

function getStrategy(d: any): string {
  if (d.strategy) return d.strategy
  const cid = (d.client_order_id || d.reason || '').toLowerCase()
  if (cid.includes('scalp')) return 'scalp'
  if (cid.includes('runner')) return 'runner'
  if (cid.includes('dip')) return 'dip'
  if (cid.includes('claude')) return 'claude'
  if (cid.includes('gpt') || cid.includes('ai')) return 'gpt'
  return 'manual'
}

function getMeta(key: string) {
  const k = key.toLowerCase()
  for (const [sk, v] of Object.entries(STRATEGY_META)) {
    if (k.includes(sk)) return v
  }
  return STRATEGY_META.manual
}

export default function DecisionsPage() {
  const [decisions, setDecisions] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState('ALL')
  const [expanded, setExpanded] = useState<Set<number>>(new Set())

  const fetchData = useCallback(() => {
    fetch(`${API}/api/decision-log`)
      .then(r => r.json())
      .then(data => { setDecisions(data.decisions || data.log || []); setLoading(false) })
      .catch(() => setLoading(false))
  }, [])

  useEffect(() => {
    fetchData()
    const interval = setInterval(fetchData, 10000)
    return () => clearInterval(interval)
  }, [fetchData])

  const filtered = filter === 'ALL'
    ? decisions
    : decisions.filter(d => getStrategy(d).toLowerCase().includes(filter.toLowerCase()))

  const toggleExpand = (i: number) => {
    setExpanded(prev => {
      const next = new Set(prev)
      next.has(i) ? next.delete(i) : next.add(i)
      return next
    })
  }

  if (loading) return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="flex flex-col items-center gap-4">
        <div className="w-12 h-12 border-2 border-[#00ff88]/30 border-t-[#00ff88] rounded-full animate-spin" />
        <p className="text-slate-500 text-sm">Loading decisions...</p>
      </div>
    </div>
  )

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">🎯 Decision History</h1>
        <p className="text-slate-500 text-sm mt-1">The WHY behind every trade · {decisions.length} decisions · Auto-refresh 10s</p>
      </div>

      {/* Filter Tabs */}
      <div className="flex gap-2 flex-wrap">
        {FILTERS.map(f => (
          <button key={f} onClick={() => setFilter(f)}
            className={`px-4 py-2 rounded-xl text-xs font-semibold transition-all ${
              filter === f
                ? 'bg-[#00ff88]/15 text-[#00ff88] border border-[#00ff88]/30 shadow-[0_0_15px_rgba(0,255,136,0.15)]'
                : 'glass-card text-slate-400 hover:text-white'
            }`}>
            {f}
          </button>
        ))}
      </div>

      {/* Timeline */}
      {filtered.length === 0 ? (
        <div className="glass-card p-12 text-center">
          <p className="text-slate-400 text-lg">No decisions {filter !== 'ALL' ? `for "${filter}"` : 'recorded yet'}</p>
        </div>
      ) : (
        <div className="relative timeline-line pl-10 space-y-2 stagger-enter">
          {filtered.map((d: any, idx: number) => {
            const side = (d.side || d.type || '').toLowerCase()
            const isBuy = side === 'buy'
            const stratKey = getStrategy(d)
            const meta = getMeta(stratKey)
            const time = d.time || d.timestamp || d.filled_at || ''
            const reasoning = d.reasoning || d.reason || d.ai_reasoning || ''
            const isExpanded = expanded.has(idx)

            return (
              <div key={idx} className="relative">
                {/* Timeline dot */}
                <div className={`absolute left-[-24px] top-5 w-3.5 h-3.5 rounded-full border-2 z-10 ${
                  isBuy ? 'bg-[#00ff88] border-[#00ff88]/50' : 'bg-red-500 border-red-500/50'
                }`} />

                {/* Card with gradient left border */}
                <div className={`glass-card p-5 border-l-4 ${meta.border} cursor-pointer hover:border-l-[5px] transition-all`}
                  onClick={() => reasoning && toggleExpand(idx)}>
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap mb-2">
                        <span className="font-mono font-bold text-white text-lg">{d.symbol}</span>
                        <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${isBuy ? 'bg-[#00ff88]/15 text-[#00ff88]' : 'bg-red-500/15 text-red-400'}`}>
                          {isBuy ? 'BUY' : 'SELL'}
                        </span>
                        <span className={`text-[10px] px-2 py-0.5 rounded-full ${meta.badge}`}>{meta.label}</span>
                      </div>
                      <div className="flex gap-4 text-xs text-slate-400">
                        <span>{d.qty} shares</span>
                        <span>@ ${Number(d.price || d.filled_avg_price || 0).toFixed(2)}</span>
                      </div>
                    </div>
                    <div className="text-right shrink-0">
                      <p className="text-xs text-slate-500">{time ? new Date(time).toLocaleString() : '—'}</p>
                      {reasoning && <p className="text-[10px] text-slate-600 mt-1">{isExpanded ? '▼' : '▶'} reasoning</p>}
                    </div>
                  </div>

                  {/* Expandable reasoning */}
                  {isExpanded && reasoning && (
                    <div className="mt-4 border-l-2 border-white/10 pl-4 animate-fade-in">
                      <p className="text-sm text-slate-300 italic leading-relaxed">&ldquo;{reasoning}&rdquo;</p>
                    </div>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
