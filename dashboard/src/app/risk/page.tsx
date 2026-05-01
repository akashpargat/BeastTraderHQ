'use client'
import { useEffect, useState, useCallback } from 'react'
import { authFetch } from '@/lib/api'

function limitBar(current: number, limit: number, label: string) {
  const pct = Math.min(Math.abs(current / limit) * 100, 100)
  const color = pct >= 90 ? 'bg-red-500' : pct >= 70 ? 'bg-orange-500' : pct >= 50 ? 'bg-yellow-500' : 'bg-green-500'
  const textColor = pct >= 90 ? 'text-red-400' : pct >= 70 ? 'text-orange-400' : pct >= 50 ? 'text-yellow-400' : 'text-green-400'
  return (
    <div className="mb-3">
      <div className="flex justify-between text-sm mb-1">
        <span className="text-gray-400">{label}</span>
        <span className={textColor}>{current.toFixed(2)}% / {limit}%</span>
      </div>
      <div className="w-full bg-gray-700 rounded-full h-3 relative">
        <div className={`${color} h-3 rounded-full transition-all`} style={{ width: `${pct}%` }} />
        <div className="absolute right-0 top-0 h-full w-0.5 bg-red-400" title={`Kill: ${limit}%`} />
      </div>
    </div>
  )
}

export default function RiskPage() {
  const [risk, setRisk] = useState<any>(null)
  const [antiBuyback, setAntiBuyback] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const fetchData = useCallback(async () => {
    try {
      const [rRes, abRes] = await Promise.all([
        authFetch('/api/v5/risk-status').catch(() => null),
        authFetch('/api/v5/anti-buyback').catch(() => null),
      ])
      if (rRes?.ok) setRisk(await rRes.json())
      if (abRes?.ok) setAntiBuyback(await abRes.json())
      setError('')
    } catch (e: any) {
      setError(e.message || 'Failed to load risk data')
    }
    setLoading(false)
  }, [])

  useEffect(() => {
    fetchData()
    const i = setInterval(fetchData, 30000)
    return () => clearInterval(i)
  }, [fetchData])

  if (loading) return <div className="flex items-center justify-center min-h-[50vh]"><div className="text-4xl animate-bounce">🛡️</div></div>
  if (error && !risk) return <div className="bg-gray-800 rounded-lg p-6 text-center text-red-400">{error}</div>

  const ll = risk?.loss_limits || {}
  const dailyPl = Number(ll.daily_pnl_pct ?? risk?.daily_pnl_pct ?? risk?.daily_pl_pct ?? 0) * 100
  const weeklyPl = Number(ll.weekly_pnl_pct ?? risk?.weekly_pl_pct ?? 0) * 100
  const monthlyPl = Number(ll.monthly_pnl_pct ?? risk?.monthly_pl_pct ?? 0) * 100
  const invested = Number(risk?.portfolio_heat ?? risk?.invested_pct ?? risk?.heat ?? 0) * 100
  const cashPct = 100 - invested
  const sectors = risk?.sector_exposure || {}
  const blocked = antiBuyback?.blocks || antiBuyback?.blocked || antiBuyback?.stocks || []
  const killSwitch = risk?.kill_switch_active ?? !(ll.can_buy ?? true)

  return (
    <div className="space-y-6 fade-in">
      {/* Kill Switch Warning */}
      {killSwitch && (
        <div className="bg-red-900/60 border border-red-500 rounded-lg p-4 text-center animate-pulse">
          <span className="text-red-300 font-bold text-lg">🚨 KILL SWITCH ACTIVE — Trading halted due to daily loss limit</span>
        </div>
      )}

      {/* Daily P&L Bar */}
      <div className="bg-gray-800 rounded-lg p-4 shadow-lg">
        <h2 className="text-lg font-semibold text-white mb-3">📊 Daily P&L</h2>
        <div className="relative h-10 bg-gray-700 rounded-lg overflow-hidden">
          {/* Center line */}
          <div className="absolute left-1/2 top-0 h-full w-0.5 bg-gray-500 z-10" />
          {/* Kill switch line at -2% */}
          <div className="absolute top-0 h-full w-0.5 bg-red-500 z-10" style={{ left: `${Math.max(50 + (-2 / 4) * 50, 5)}%` }}>
            <span className="absolute -top-5 -left-3 text-xs text-red-400">-2%</span>
          </div>
          {/* P&L bar */}
          <div
            className={`absolute top-1 h-8 rounded ${dailyPl >= 0 ? 'bg-green-500' : 'bg-red-500'}`}
            style={{
              left: dailyPl >= 0 ? '50%' : `${50 + (dailyPl / 4) * 50}%`,
              width: `${Math.min(Math.abs(dailyPl / 4) * 50, 50)}%`,
            }}
          />
        </div>
        <div className={`text-center mt-2 text-2xl font-bold ${dailyPl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
          {dailyPl >= 0 ? '+' : ''}{dailyPl.toFixed(2)}%
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Portfolio Heat */}
        <div className="bg-gray-800 rounded-lg p-4 shadow-lg">
          <h2 className="text-lg font-semibold text-white mb-3">🌡️ Portfolio Heat</h2>
          <div className="flex items-center gap-4">
            <div className="relative w-32 h-32">
              <svg viewBox="0 0 36 36" className="w-full h-full -rotate-90">
                <circle cx="18" cy="18" r="15.9" fill="none" stroke="#374151" strokeWidth="3" />
                <circle
                  cx="18" cy="18" r="15.9" fill="none"
                  stroke={invested > 80 ? '#ef4444' : invested > 60 ? '#f59e0b' : '#22c55e'}
                  strokeWidth="3"
                  strokeDasharray={`${invested} ${100 - invested}`}
                />
              </svg>
              <div className="absolute inset-0 flex items-center justify-center">
                <span className="text-2xl font-bold text-white">{invested.toFixed(0)}%</span>
              </div>
            </div>
            <div className="space-y-1 text-sm">
              <div className="flex gap-2"><span className="text-gray-400">Invested:</span><span className="text-white">{invested.toFixed(1)}%</span></div>
              <div className="flex gap-2"><span className="text-gray-400">Cash:</span><span className="text-green-400">{cashPct.toFixed(1)}%</span></div>
              <div className="flex gap-2"><span className="text-gray-400">Positions:</span><span className="text-white">{risk?.position_count ?? 0}</span></div>
            </div>
          </div>
        </div>

        {/* Loss Limits */}
        <div className="bg-gray-800 rounded-lg p-4 shadow-lg">
          <h2 className="text-lg font-semibold text-white mb-3">🚦 Loss Limits</h2>
          {limitBar(dailyPl, -2, 'Daily (-2%)')}
          {limitBar(weeklyPl, -5, 'Weekly (-5%)')}
          {limitBar(monthlyPl, -10, 'Monthly (-10%)')}
        </div>
      </div>

      {/* Sector Exposure */}
      <div className="bg-gray-800 rounded-lg p-4 shadow-lg">
        <h2 className="text-lg font-semibold text-white mb-3">🗺️ Sector Exposure (25% cap)</h2>
        {Object.keys(sectors).length === 0 ? (
          <div className="text-gray-500 text-center py-4">No sector data available</div>
        ) : (
          <div className="space-y-2">
            {Object.entries(sectors)
              .sort(([, a]: any, [, b]: any) => b - a)
              .map(([sector, pct]: [string, any]) => {
                const val = Number(pct)
                const over = val > 25
                return (
                  <div key={sector}>
                    <div className="flex justify-between text-sm mb-1">
                      <span className={over ? 'text-red-400 font-semibold' : 'text-gray-300'}>{sector} {over && '⚠️'}</span>
                      <span className={over ? 'text-red-400' : 'text-gray-400'}>{val.toFixed(1)}%</span>
                    </div>
                    <div className="w-full bg-gray-700 rounded-full h-2">
                      <div
                        className={`h-2 rounded-full ${over ? 'bg-red-500' : val > 20 ? 'bg-yellow-500' : 'bg-green-500'}`}
                        style={{ width: `${Math.min(val * 4, 100)}%` }}
                      />
                    </div>
                  </div>
                )
              })}
          </div>
        )}
      </div>

      {/* Anti-Buyback Monitor */}
      <div className="bg-gray-800 rounded-lg p-4 shadow-lg">
        <h2 className="text-lg font-semibold text-white mb-3">🚫 Anti-Buyback Monitor</h2>
        {blocked.length === 0 ? (
          <div className="text-gray-500 text-center py-4">No blocked stocks</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-gray-400 border-b border-white/10">
                  <th className="text-left py-2 px-3">Symbol</th>
                  <th className="text-left py-2 px-3">Reason</th>
                  <th className="text-right py-2 px-3">Sold At</th>
                  <th className="text-right py-2 px-3">Blocked Until</th>
                  <th className="text-right py-2 px-3">Time Left</th>
                </tr>
              </thead>
              <tbody>
                {blocked.map((b: any, i: number) => {
                  const until = b.blocked_until ? new Date(b.blocked_until) : null
                  const now = new Date()
                  const hoursLeft = until ? Math.max(0, (until.getTime() - now.getTime()) / 3600000) : 0
                  return (
                    <tr key={i} className="border-b border-white/5 hover:bg-white/5">
                      <td className="py-2 px-3 font-mono font-semibold text-white">{b.symbol}</td>
                      <td className="py-2 px-3 text-gray-400">{b.reason ?? 'Loss exit'}</td>
                      <td className="py-2 px-3 text-right text-red-400">${Number(b.sold_price ?? 0).toFixed(2)}</td>
                      <td className="py-2 px-3 text-right text-gray-400">{until ? until.toLocaleDateString() : '—'}</td>
                      <td className="py-2 px-3 text-right">
                        <span className={`px-2 py-0.5 rounded-full text-xs ${hoursLeft < 24 ? 'bg-green-900/40 text-green-400' : 'bg-red-900/40 text-red-400'}`}>
                          {hoursLeft < 1 ? '< 1h' : hoursLeft < 24 ? `${hoursLeft.toFixed(0)}h` : `${(hoursLeft / 24).toFixed(0)}d`}
                        </span>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
