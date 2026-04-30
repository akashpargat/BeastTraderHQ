'use client'
import { useEffect, useState, useCallback } from 'react'
import { authFetch } from '../../lib/api'

const STRATEGY_STYLES: Record<string, string> = {
  scalp: 'bg-blue-500/15 text-blue-400 border border-blue-500/30',
  runner: 'bg-green-500/15 text-green-400 border border-green-500/30',
  dip: 'bg-orange-500/15 text-orange-400 border border-orange-500/30',
  ai: 'bg-purple-500/15 text-purple-400 border border-purple-500/30',
  protect: 'bg-rose-500/15 text-rose-400 border border-rose-500/30',
  earnings: 'bg-amber-500/15 text-amber-400 border border-amber-500/30',
}

function extractStrategy(t: any): string {
  if (t.strategy) return t.strategy
  const cid = (t.client_order_id || '').toLowerCase()
  if (cid.includes('scalp')) return 'Scalp'
  if (cid.includes('runner')) return 'Runner'
  if (cid.includes('dip')) return 'DipBuy'
  if (cid.includes('ai') || cid.includes('claude') || cid.includes('gpt')) return 'AI'
  if (cid.includes('protect')) return 'Protect'
  return cid.split('-')[0] || 'Manual'
}

function strategyStyle(name: string): string {
  const n = name.toLowerCase()
  for (const key of Object.keys(STRATEGY_STYLES)) {
    if (n.includes(key)) return STRATEGY_STYLES[key]
  }
  return 'bg-slate-500/15 text-slate-400 border border-slate-500/30'
}

type Filter = 'ALL' | 'BUY' | 'SELL' | 'TODAY'

export default function TradesPage() {
  const [trades, setTrades] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState<Filter>('ALL')

  const fetchData = useCallback(() => {
    authFetch('/api/trades?limit=100')
      .then(r => r.json())
      .then(d => { setTrades(d.trades || []); setLoading(false) })
      .catch(() => setLoading(false))
  }, [])

  useEffect(() => {
    fetchData()
    const interval = setInterval(fetchData, 10000)
    return () => clearInterval(interval)
  }, [fetchData])

  const todayStr = new Date().toISOString().slice(0, 10)
  const filtered = trades.filter((t: any) => {
    const side = (t.side || '').toLowerCase()
    if (filter === 'BUY' && side !== 'buy') return false
    if (filter === 'SELL' && side !== 'sell') return false
    if (filter === 'TODAY') {
      const d = t.filled_at || t.created_at || t.time || ''
      if (!d.startsWith(todayStr)) return false
    }
    return true
  })

  const filters: Filter[] = ['ALL', 'BUY', 'SELL', 'TODAY']

  if (loading) return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="flex flex-col items-center gap-4">
        <div className="w-12 h-12 border-2 border-[#00ff88]/30 border-t-[#00ff88] rounded-full animate-spin" />
        <p className="text-slate-500 text-sm">Loading trade history...</p>
      </div>
    </div>
  )

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">📋 Trade History</h1>
          <p className="text-slate-500 text-sm mt-1">{trades.length} total fills · Auto-refresh 10s</p>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="w-2 h-2 rounded-full bg-[#00ff88] live-dot" />
          <span className="text-xs text-[#00ff88]/70">LIVE</span>
        </div>
      </div>

      {/* Filter Tabs */}
      <div className="flex gap-2">
        {filters.map(f => (
          <button key={f} onClick={() => setFilter(f)}
            className={`px-5 py-2 rounded-xl text-xs font-semibold transition-all ${
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
          <p className="text-slate-400 text-lg">No trades {filter !== 'ALL' ? `for "${filter}"` : 'recorded yet'}</p>
        </div>
      ) : (
        <div className="relative timeline-line pl-10 space-y-1 stagger-enter">
          {filtered.map((t: any, idx: number) => {
            const side = (t.side || '').toLowerCase()
            const isBuy = side === 'buy'
            const time = t.filled_at || t.created_at || t.time || ''
            const strategy = extractStrategy(t)

            return (
              <div key={t.id || idx} className="relative flex items-start gap-4 pb-4">
                {/* Dot */}
                <div className={`absolute left-[-24px] top-2 w-3.5 h-3.5 rounded-full border-2 z-10 ${
                  isBuy ? 'bg-[#00ff88] border-[#00ff88]/50 shadow-[0_0_8px_rgba(0,255,136,0.5)]' : 'bg-red-500 border-red-500/50 shadow-[0_0_8px_rgba(255,68,68,0.5)]'
                }`} />

                {/* Card */}
                <div className="glass-card p-4 flex-1 flex items-center gap-4 hover:border-white/15 transition-all">
                  {/* Time */}
                  <div className="shrink-0 w-20">
                    <p className="text-[10px] text-slate-500 font-mono">{time ? new Date(time).toLocaleDateString() : ''}</p>
                    <p className="text-xs text-slate-400 font-mono">{time ? new Date(time).toLocaleTimeString() : '—'}</p>
                  </div>

                  {/* Symbol Avatar */}
                  <div className={`w-9 h-9 rounded-full flex items-center justify-center text-xs font-bold shrink-0 ${isBuy ? 'bg-[#00ff88]/15 text-[#00ff88]' : 'bg-red-500/15 text-red-400'}`}>
                    {(t.symbol || '??').slice(0, 2)}
                  </div>

                  {/* Info */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-mono font-bold text-white">{t.symbol}</span>
                      <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${isBuy ? 'bg-[#00ff88]/15 text-[#00ff88]' : 'bg-red-500/15 text-red-400'}`}>
                        {isBuy ? 'BUY' : 'SELL'}
                      </span>
                      <span className={`text-[10px] px-2 py-0.5 rounded-full ${strategyStyle(strategy)}`}>{strategy}</span>
                    </div>
                  </div>

                  {/* Qty + Price */}
                  <div className="text-right shrink-0">
                    <p className="text-sm font-mono text-white">{t.qty || t.filled_qty || '—'} × ${Number(t.filled_avg_price || t.price || 0).toFixed(2)}</p>
                    <p className="text-[10px] text-slate-500">${(Number(t.qty || 0) * Number(t.filled_avg_price || t.price || 0)).toFixed(0)} total</p>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}