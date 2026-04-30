'use client'
import { useEffect, useState, useCallback } from 'react'
import { authFetch } from '../../lib/api'

function WinRateRing({ rate }: { rate: number }) {
  const pct = rate > 1 ? rate : rate * 100
  const circumference = 2 * Math.PI * 40
  const offset = circumference - (pct / 100) * circumference
  const color = pct >= 60 ? '#00ff88' : pct >= 40 ? '#facc15' : '#ff4444'

  return (
    <div className="relative w-28 h-28 mx-auto">
      <svg className="w-full h-full -rotate-90" viewBox="0 0 100 100">
        <circle cx="50" cy="50" r="40" fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="6" />
        <circle cx="50" cy="50" r="40" fill="none" stroke={color} strokeWidth="6"
          strokeLinecap="round" strokeDasharray={circumference}
          strokeDashoffset={offset}
          style={{ animation: 'ring-fill 1.2s ease-out forwards' }} />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-2xl font-bold font-mono" style={{ color }}>{pct.toFixed(0)}%</span>
        <span className="text-[10px] text-slate-500">Win Rate</span>
      </div>
    </div>
  )
}

export default function AnalyticsPage() {
  const [data, setData] = useState<any>(null)

  const fetchData = useCallback(() => {
    authFetch('/api/analytics').then(r => r.json()).then(setData).catch(() => {})
  }, [])

  useEffect(() => {
    fetchData()
    const interval = setInterval(fetchData, 10000)
    return () => clearInterval(interval)
  }, [fetchData])

  if (!data) return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="flex flex-col items-center gap-4">
        <div className="w-12 h-12 border-2 border-[#00ff88]/30 border-t-[#00ff88] rounded-full animate-spin" />
        <p className="text-slate-500 text-sm">Loading analytics...</p>
      </div>
    </div>
  )

  const stats = data.overall || data
  const streak = data.streak || {}
  const equityCurve: any[] = data.equity_curve || []
  const byStrategy: any[] = data.by_strategy || []
  const totalPnl = stats.total_pnl ?? 0
  const isGreen = totalPnl >= 0
  const winRate = stats.win_rate ?? 0
  const marketClosed = data.market_closed || false

  const maxStrategyPnl = Math.max(...byStrategy.map((s: any) => Math.abs(s.total_pnl || 0)), 1)

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">📈 Analytics Dashboard</h1>
        <p className="text-slate-500 text-sm mt-1">Auto-refresh 10s</p>
      </div>

      {marketClosed && (
        <div className="glass-card p-6 text-center mb-6">
          <div className="text-4xl mb-2">🌙</div>
          <p className="text-slate-400">Market Closed</p>
          <p className="text-slate-500 text-sm">Analytics will update when market opens at 9:30 AM ET</p>
        </div>
      )}

      {/* Hero: Total P&L */}
      <div className="glass-card p-8 text-center relative overflow-hidden">
        <div className={`absolute inset-0 ${isGreen ? 'bg-[#00ff88]/[0.02]' : 'bg-red-500/[0.02]'}`} />
        <p className="text-slate-500 text-sm uppercase tracking-wider mb-2 relative z-10">Total P&L</p>
        <p className={`text-5xl md:text-6xl font-bold font-mono relative z-10 animate-number-pop ${isGreen ? 'text-[#00ff88] glow-green' : 'text-red-400 glow-red'}`}>
          {isGreen ? '+' : ''}${totalPnl.toFixed(2)}
        </p>
      </div>

      {/* 6 Stat Cards (2x3) */}
      <div className="grid grid-cols-2 lg:grid-cols-3 gap-5 stagger-enter">
        {/* Total Trades */}
        <div className="glass-card p-6 text-center">
          <p className="text-slate-500 text-xs uppercase tracking-wider mb-2">Total Trades</p>
          <p className="text-4xl font-bold font-mono text-white animate-number-pop">{stats.total_trades ?? 0}</p>
        </div>

        {/* Win Rate Ring */}
        <div className="glass-card p-6">
          <WinRateRing rate={winRate} />
        </div>

        {/* Best Day */}
        <div className="glass-card p-6 text-center" style={{ boxShadow: '0 0 30px rgba(0,255,136,0.08)' }}>
          <p className="text-slate-500 text-xs uppercase tracking-wider mb-2">Best Day</p>
          <p className="text-3xl font-bold font-mono text-[#00ff88]">+${(stats.best_day ?? 0).toFixed(2)}</p>
        </div>

        {/* Worst Day */}
        <div className="glass-card p-6 text-center" style={{ boxShadow: '0 0 30px rgba(255,68,68,0.08)' }}>
          <p className="text-slate-500 text-xs uppercase tracking-wider mb-2">Worst Day</p>
          <p className="text-3xl font-bold font-mono text-red-400">${(stats.worst_day ?? 0).toFixed(2)}</p>
        </div>

        {/* Wins / Losses */}
        <div className="glass-card p-6 text-center">
          <p className="text-slate-500 text-xs uppercase tracking-wider mb-2">Wins / Losses</p>
          <p className="text-3xl font-bold font-mono">
            <span className="text-[#00ff88]">{stats.wins ?? 0}</span>
            <span className="text-slate-600 mx-2">/</span>
            <span className="text-red-400">{stats.losses ?? 0}</span>
          </p>
        </div>

        {/* Current Streak */}
        <div className="glass-card p-6 text-center">
          <p className="text-slate-500 text-xs uppercase tracking-wider mb-2">Current Streak</p>
          <p className={`text-3xl font-bold font-mono ${(streak.type || 'win') === 'win' ? 'text-[#00ff88]' : 'text-red-400'}`}>
            {streak.count ?? stats.current_streak ?? 0} {(streak.type || 'W').charAt(0).toUpperCase()}
          </p>
        </div>
      </div>

      {/* Equity Curve — CSS Bar Chart */}
      {equityCurve.length > 0 && (
        <div className="glass-card p-6">
          <h2 className="text-lg font-semibold mb-5">📈 Equity Curve (Last 30 Days)</h2>
          <div className="h-52 flex items-end gap-[3px] group">
            {equityCurve.slice(-30).map((e: any, i: number) => {
              const vals = equityCurve.slice(-30).map((x: any) => x.equity || x.value || 0)
              const min = Math.min(...vals)
              const max = Math.max(...vals)
              const range = max - min || 1
              const height = ((e.equity || e.value || 0) - min) / range * 100
              const prevVal = i > 0 ? (equityCurve.slice(-30)[i - 1]?.equity || 0) : (e.equity || 0)
              const isUp = (e.equity || 0) >= prevVal

              return (
                <div key={i} className="flex-1 relative group/bar" title={`$${(e.equity || 0).toLocaleString()}`}>
                  <div className={`w-full rounded-t transition-all duration-300 ${isUp ? 'bg-[#00ff88]/50 hover:bg-[#00ff88]/80' : 'bg-red-500/50 hover:bg-red-500/80'}`}
                    style={{ height: `${Math.max(3, height)}%` }} />
                  <div className="absolute -top-8 left-1/2 -translate-x-1/2 bg-slate-800 text-[9px] text-white px-1.5 py-0.5 rounded opacity-0 group-hover/bar:opacity-100 transition-opacity whitespace-nowrap pointer-events-none z-10">
                    ${(e.equity || 0).toLocaleString()}
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Strategy Breakdown — Horizontal Bars */}
      {byStrategy.length > 0 && (
        <div className="glass-card p-6">
          <h2 className="text-lg font-semibold mb-5">🎯 Strategy Breakdown</h2>
          <div className="space-y-4">
            {byStrategy.map((s: any) => {
              const pnl = s.total_pnl ?? 0
              const isPos = pnl >= 0
              const width = (Math.abs(pnl) / maxStrategyPnl) * 100

              return (
                <div key={s.strategy}>
                  <div className="flex justify-between text-sm mb-1.5">
                    <span className="font-mono font-semibold text-white">{s.strategy}</span>
                    <span className={`font-mono font-bold ${isPos ? 'text-[#00ff88]' : 'text-red-400'}`}>
                      {isPos ? '+' : ''}${pnl.toFixed(2)}
                    </span>
                  </div>
                  <div className="w-full bg-white/[0.04] rounded-full h-3 overflow-hidden">
                    <div className={`h-full rounded-full transition-all duration-700 ${isPos ? 'bg-gradient-to-r from-[#00ff88]/40 to-[#00ff88]' : 'bg-gradient-to-r from-red-500/40 to-red-500'}`}
                      style={{ width: `${Math.max(4, width)}%` }} />
                  </div>
                  <div className="flex gap-4 text-[10px] text-slate-500 mt-1">
                    <span>{s.trades} trades</span>
                    <span>WR: {s.win_rate}%</span>
                    <span>Avg: ${(s.avg_pnl ?? 0).toFixed(2)}</span>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {byStrategy.length === 0 && equityCurve.length === 0 && (
        <div className="glass-card p-12 text-center">
          <p className="text-slate-400 text-lg">No trade data yet</p>
          <p className="text-slate-600 text-sm mt-1">Analytics populate as the bot makes trades</p>
        </div>
      )}
    </div>
  )
}