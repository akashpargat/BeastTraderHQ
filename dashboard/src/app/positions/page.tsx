'use client'
import { useEffect, useState, useCallback } from 'react'

const API = 'https://api.beast-trader.com'

type SortKey = 'pnl' | 'pct' | 'value' | 'alpha'

function aiVerdict(p: any): { label: string; color: string } {
  if (p.ai_action) {
    const a = p.ai_action.toUpperCase()
    if (a === 'BUY') return { label: 'BUY', color: 'bg-green-500/20 text-green-400 shadow-[0_0_12px_rgba(0,255,136,0.3)]' }
    if (a === 'SELL') return { label: 'SELL', color: 'bg-red-500/20 text-red-400 shadow-[0_0_12px_rgba(255,68,68,0.3)]' }
    return { label: 'HOLD', color: 'bg-yellow-500/15 text-yellow-400' }
  }
  if (p.pct >= 3) return { label: 'BUY', color: 'bg-green-500/20 text-green-400 shadow-[0_0_12px_rgba(0,255,136,0.3)]' }
  if (p.pct <= -3) return { label: 'SELL', color: 'bg-red-500/20 text-red-400 shadow-[0_0_12px_rgba(255,68,68,0.3)]' }
  return { label: 'HOLD', color: 'bg-yellow-500/15 text-yellow-400' }
}

export default function PositionsPage() {
  const [portfolio, setPortfolio] = useState<any>(null)
  const [sort, setSort] = useState<SortKey>('pnl')

  const fetchData = useCallback(() => {
    fetch(`${API}/api/portfolio`).then(r => r.json()).then(setPortfolio).catch(() => {})
  }, [])

  useEffect(() => {
    fetchData()
    const interval = setInterval(fetchData, 10000)
    return () => clearInterval(interval)
  }, [fetchData])

  if (!portfolio) return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="flex flex-col items-center gap-4">
        <div className="w-12 h-12 border-2 border-[#00ff88]/30 border-t-[#00ff88] rounded-full animate-spin" />
        <p className="text-slate-500 text-sm">Loading positions...</p>
      </div>
    </div>
  )

  const positions = [...(portfolio.positions || [])]
  if (sort === 'pnl') positions.sort((a: any, b: any) => b.unrealized_pl - a.unrealized_pl)
  else if (sort === 'pct') positions.sort((a: any, b: any) => b.pct - a.pct)
  else if (sort === 'value') positions.sort((a: any, b: any) => b.market_value - a.market_value)
  else positions.sort((a: any, b: any) => a.symbol.localeCompare(b.symbol))

  const sortBtns: { key: SortKey; label: string }[] = [
    { key: 'pnl', label: 'By P&L' },
    { key: 'pct', label: 'By %' },
    { key: 'value', label: 'By Value' },
    { key: 'alpha', label: 'A → Z' },
  ]

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">💼 Positions Deep Dive</h1>
          <p className="text-slate-500 text-sm mt-1">{positions.length} active positions · Auto-refresh 10s</p>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="w-2 h-2 rounded-full bg-[#00ff88] live-dot" />
          <span className="text-xs text-[#00ff88]/70">LIVE</span>
        </div>
      </div>

      {/* Summary Strip */}
      <div className="grid grid-cols-3 gap-4">
        {[
          { label: 'Portfolio Value', value: `$${portfolio.equity?.toLocaleString() ?? '—'}`, color: 'text-white' },
          { label: 'Day P&L', value: `${(portfolio.total_pl ?? 0) >= 0 ? '+' : ''}$${(portfolio.total_pl ?? 0).toFixed(2)}`, color: (portfolio.total_pl ?? 0) >= 0 ? 'text-[#00ff88] glow-green' : 'text-red-400 glow-red' },
          { label: 'Buying Power', value: `$${portfolio.buying_power?.toLocaleString() ?? '—'}`, color: 'text-slate-300' },
        ].map((s, i) => (
          <div key={i} className="glass-card p-5 text-center">
            <p className="text-slate-500 text-xs uppercase tracking-wider mb-1">{s.label}</p>
            <p className={`text-2xl font-bold font-mono ${s.color}`}>{s.value}</p>
          </div>
        ))}
      </div>

      {/* Sort Buttons */}
      <div className="flex gap-2">
        {sortBtns.map(b => (
          <button key={b.key} onClick={() => setSort(b.key)}
            className={`px-4 py-2 rounded-xl text-xs font-semibold transition-all ${
              sort === b.key
                ? 'bg-[#00ff88]/15 text-[#00ff88] border border-[#00ff88]/30 shadow-[0_0_15px_rgba(0,255,136,0.15)]'
                : 'glass-card text-slate-400 hover:text-white'
            }`}>
            {b.label}
          </button>
        ))}
      </div>

      {/* Position Hero Cards */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5 stagger-enter">
        {positions.map((p: any) => {
          const isGreen = (p.unrealized_pl ?? 0) >= 0
          const verdict = aiVerdict(p)
          const sentimentGreen = Math.max(0, Math.min(100, 50 + p.pct * 5))

          return (
            <div key={p.symbol} className="glass-card hover-scale-glow p-6 relative overflow-hidden group">
              {/* Glow accent */}
              <div className={`absolute top-0 left-0 w-full h-1 ${isGreen ? 'bg-gradient-to-r from-[#00ff88] to-transparent' : 'bg-gradient-to-r from-red-500 to-transparent'}`} />

              {/* Top row: Symbol + Verdict */}
              <div className="flex items-start justify-between mb-4">
                <div className="flex items-center gap-3">
                  <div className={`w-11 h-11 rounded-full flex items-center justify-center text-sm font-bold ${isGreen ? 'bg-[#00ff88]/15 text-[#00ff88]' : 'bg-red-500/15 text-red-400'}`}>
                    {p.symbol?.slice(0, 2)}
                  </div>
                  <div>
                    <h3 className="text-xl font-bold font-mono tracking-tight">{p.symbol}</h3>
                    <p className="text-xs text-slate-500">{p.qty} shares</p>
                  </div>
                </div>
                <span className={`px-3 py-1 rounded-full text-xs font-bold ${verdict.color}`}>{verdict.label}</span>
              </div>

              {/* P&L Hero Number */}
              <div className="mb-4">
                <p className={`text-3xl font-bold font-mono ${isGreen ? 'text-[#00ff88] glow-green' : 'text-red-400 glow-red'}`}>
                  {isGreen ? '+' : ''}${(p.unrealized_pl ?? 0).toFixed(2)}
                </p>
                <p className={`text-sm font-mono ${isGreen ? 'text-[#00ff88]/60' : 'text-red-400/60'}`}>
                  {isGreen ? '+' : ''}{(p.pct ?? 0).toFixed(2)}%
                </p>
              </div>

              {/* Price Arrow */}
              <div className="flex items-center gap-2 mb-4 text-sm">
                <span className="text-slate-400 font-mono">${(p.avg_entry ?? 0).toFixed(2)}</span>
                <span className={`${isGreen ? 'text-[#00ff88]' : 'text-red-400'}`}>→</span>
                <span className="text-white font-mono font-bold">${(p.current_price ?? 0).toFixed(2)}</span>
                <span className="text-slate-600 mx-2">|</span>
                <span className="text-slate-400 text-xs">MV: ${(p.market_value ?? 0).toLocaleString()}</span>
              </div>

              {/* Bottom row: Stop + Sentiment */}
              <div className="flex items-center justify-between">
                <span className={`text-xs px-2 py-1 rounded-lg ${p.trailing_stop ? 'bg-[#00ff88]/10 text-[#00ff88]' : 'bg-orange-500/10 text-orange-400'}`}>
                  {p.trailing_stop ? '🛡️ Protected' : '⚠️ Exposed'}
                </span>
                {/* Mini sentiment bar */}
                <div className="flex items-center gap-2">
                  <span className="text-[10px] text-slate-600">Sentiment</span>
                  <div className="w-20 h-1.5 rounded-full bg-slate-700 overflow-hidden flex">
                    <div className="h-full bg-[#00ff88] rounded-l-full" style={{ width: `${sentimentGreen}%` }} />
                    <div className="h-full bg-red-500 rounded-r-full" style={{ width: `${100 - sentimentGreen}%` }} />
                  </div>
                </div>
              </div>
            </div>
          )
        })}
      </div>

      {positions.length === 0 && (
        <div className="glass-card p-12 text-center">
          <p className="text-slate-400 text-lg">No active positions</p>
          <p className="text-slate-600 text-sm mt-1">Positions appear when the bot executes trades</p>
        </div>
      )}
    </div>
  )
}