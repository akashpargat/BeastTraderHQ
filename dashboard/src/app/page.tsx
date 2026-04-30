'use client'
import { useEffect, useState, useCallback } from 'react'
import { authFetch } from '../lib/api'

export default function Dashboard() {
  const [portfolio, setPortfolio] = useState<any>(null)
  const [actions, setActions] = useState<any>(null)
  const [feed, setFeed] = useState<any>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  const fetchData = useCallback(async () => {
    try {
      const [pRes, aRes, fRes] = await Promise.all([
        authFetch('/api/portfolio').catch(() => null),
        authFetch('/api/actions?limit=10').catch(() => null),
        authFetch('/api/live-feed').catch(() => null),
      ])
      if (pRes?.ok) setPortfolio(await pRes.json())
      if (aRes?.ok) setActions(await aRes.json())
      if (fRes?.ok) setFeed(await fRes.json())
      setError('')
    } catch (e: any) {
      setError(e.message || 'Connection failed')
    }
    setLoading(false)
  }, [])

  useEffect(() => {
    fetchData()
    const i = setInterval(fetchData, 10000)
    return () => clearInterval(i)
  }, [fetchData])

  if (loading) return <div className="flex items-center justify-center min-h-[50vh]"><div className="text-4xl animate-bounce">🦍</div></div>
  if (error && !portfolio) return <div className="glass p-6 text-center text-red-400">{error}</div>

  const positions = portfolio?.positions || []
  const pnl = portfolio?.total_pl ?? portfolio?.pnl ?? 0
  const dailyPl = portfolio?.daily_pl ?? 0
  const equity = portfolio?.equity ?? 0
  const cash = portfolio?.cash ?? 0
  const buyingPower = portfolio?.buying_power ?? 0
  const greenCount = portfolio?.green_count ?? positions.filter((p: any) => (p?.unrealized_pl ?? p?.pnl ?? 0) >= 0).length
  const redCount = portfolio?.red_count ?? positions.filter((p: any) => (p?.unrealized_pl ?? p?.pnl ?? 0) < 0).length
  const recentActions = actions?.actions || []
  const newsItems = (feed?.feed || []).filter((f: any) => f?.type === 'NEWS' || f?.category === 'NEWS').slice(0, 5)

  return (
    <div className="fade-in space-y-6">
      {/* Hero P&L */}
      <div className={`glass p-8 text-center ${pnl >= 0 ? 'glow-green' : 'glow-red'}`}>
        <div className="text-sm text-gray-400 mb-2">Unrealized P&L</div>
        <div className={`text-5xl font-bold ${pnl >= 0 ? 'text-[#00ff88]' : 'text-[#ff4444]'}`}>
          {pnl >= 0 ? '+' : ''}{typeof pnl === 'number' ? pnl.toLocaleString('en-US', { style: 'currency', currency: 'USD' }) : '$0.00'}
        </div>
        <div className="flex justify-center gap-6 mt-4 text-sm">
          <span className={`${dailyPl >= 0 ? 'text-[#00ff88]' : 'text-[#ff4444]'}`}>
            Today: {dailyPl >= 0 ? '+' : ''}${typeof dailyPl === 'number' ? dailyPl.toFixed(2) : '0.00'}
          </span>
          <span className="text-gray-400">Equity: ${equity?.toLocaleString() ?? '0'}</span>
          <span className="text-gray-400">Cash: ${cash?.toLocaleString() ?? '0'}</span>
          <span className="text-gray-400">BP: ${buyingPower?.toLocaleString() ?? '0'}</span>
        </div>
      </div>

      {/* Stat Cards */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <div className="glass p-4 text-center">
          <div className="text-xs text-gray-400">Unrealized</div>
          <div className={`text-xl font-bold ${pnl >= 0 ? 'text-[#00ff88]' : 'text-[#ff4444]'}`}>
            {pnl >= 0 ? '+' : ''}${typeof pnl === 'number' ? pnl.toFixed(2) : '0.00'}
          </div>
        </div>
        <div className="glass p-4 text-center">
          <div className="text-xs text-gray-400">Today</div>
          <div className={`text-xl font-bold ${dailyPl >= 0 ? 'text-[#00ff88]' : 'text-[#ff4444]'}`}>
            {dailyPl >= 0 ? '+' : ''}${typeof dailyPl === 'number' ? dailyPl.toFixed(2) : '0.00'}
          </div>
        </div>
        <div className="glass p-4 text-center">
          <div className="text-xs text-gray-400">Positions</div>
          <div className="text-xl font-bold">
            <span className="text-[#00ff88]">{greenCount}↑</span> / <span className="text-[#ff4444]">{redCount}↓</span>
          </div>
        </div>
        <div className="glass p-4 text-center">
          <div className="text-xs text-gray-400">Orders</div>
          <div className="text-xl font-bold">{portfolio?.orders_count ?? 0}</div>
        </div>
        <div className="glass p-4 text-center">
          <div className="text-xs text-gray-400">Heat</div>
          <div className="text-xl font-bold">{equity > 0 ? ((1 - cash / equity) * 100).toFixed(0) : 0}%</div>
        </div>
      </div>

      {/* Positions Table */}
      <div className="glass p-4">
        <h2 className="text-lg font-semibold mb-3">📊 Positions ({positions.length})</h2>
        {positions.length === 0 ? (
          <div className="text-center text-gray-500 py-8">No open positions</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="text-gray-400 border-b border-white/10">
                <th className="text-left py-2 px-3">Symbol</th>
                <th className="text-right py-2 px-3">Price</th>
                <th className="text-right py-2 px-3">Entry</th>
                <th className="text-right py-2 px-3">Qty</th>
                <th className="text-right py-2 px-3">P&L ($)</th>
                <th className="text-right py-2 px-3">P&L (%)</th>
                <th className="text-right py-2 px-3">Today</th>
              </tr></thead>
              <tbody>
                {positions.map((p: any, i: number) => {
                  const posPnl = p?.unrealized_pl ?? p?.pnl ?? 0
                  const posPct = p?.pct ?? p?.pnl_pct ?? 0
                  const todayPct = p?.change_today ?? p?.intraday_pct ?? 0
                  const isGreen = posPnl >= 0
                  const todayGreen = todayPct >= 0
                  return (
                    <tr key={i} className={`border-l-2 ${isGreen ? 'border-l-[#00ff88]' : 'border-l-[#ff4444]'} hover:bg-white/5 transition`}>
                      <td className="py-2 px-3 font-mono font-semibold">{p?.symbol ?? '—'}</td>
                      <td className="py-2 px-3 text-right">${Number(p?.current_price ?? 0).toFixed(2)}</td>
                      <td className="py-2 px-3 text-right text-gray-400">${Number(p?.avg_entry ?? 0).toFixed(2)}</td>
                      <td className="py-2 px-3 text-right">{p?.qty ?? 0}</td>
                      <td className={`py-2 px-3 text-right font-semibold ${isGreen ? 'text-[#00ff88]' : 'text-[#ff4444]'}`}>
                        {isGreen ? '+' : ''}${Number(posPnl).toFixed(2)}
                      </td>
                      <td className={`py-2 px-3 text-right ${isGreen ? 'text-[#00ff88]' : 'text-[#ff4444]'}`}>
                        {isGreen ? '+' : ''}{Number(posPct).toFixed(2)}%
                      </td>
                      <td className={`py-2 px-3 text-right text-xs ${todayGreen ? 'text-[#00ff88]' : 'text-[#ff4444]'}`}>
                        {todayGreen ? '+' : ''}{Number(todayPct).toFixed(1)}%
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="grid md:grid-cols-2 gap-4">
        {/* Recent Activity */}
        <div className="glass p-4">
          <h2 className="text-lg font-semibold mb-3">⚡ Recent Activity</h2>
          {recentActions.length === 0 ? (
            <div className="text-center text-gray-500 py-4">No recent activity</div>
          ) : (
            <div className="space-y-2">
              {recentActions.slice(0, 10).map((a: any, i: number) => (
                <div key={i} className="flex justify-between text-sm py-1 border-b border-white/5">
                  <span className="text-gray-400">{a?.timestamp ? new Date(a.timestamp).toLocaleTimeString() : '—'}</span>
                  <span className="font-mono">{a?.symbol ?? ''}</span>
                  <span>{a?.action ?? a?.type ?? '—'}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Breaking News */}
        <div className="glass p-4">
          <h2 className="text-lg font-semibold mb-3">📰 Breaking News</h2>
          {newsItems.length === 0 ? (
            <div className="text-center text-gray-500 py-4">No news available</div>
          ) : (
            <div className="space-y-2">
              {newsItems.map((n: any, i: number) => (
                <div key={i} className="text-sm py-1 border-b border-white/5">
                  <span className="text-gray-300">{n?.headline ?? n?.title ?? n?.message ?? '—'}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
