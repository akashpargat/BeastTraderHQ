'use client'
import { useEffect, useState } from 'react'

const API = 'https://api.beast-trader.com'

export default function AnalyticsPage() {
  const [data, setData] = useState<any>(null)

  useEffect(() => {
    fetch(`${API}/api/analytics`).then(r => r.json()).then(setData).catch(() => {})
  }, [])

  if (!data) return <div className="text-center py-20 text-slate-400">Loading analytics...</div>

  // Support both nested (data.overall) and flat (data.total_trades) formats
  const stats = data.overall || data
  const streak = data.streak || {}
  const equityCurve: any[] = data.equity_curve || []

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">📈 Analytics Dashboard</h1>

      {/* Overall Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-slate-800 rounded-xl p-6 border border-slate-700 text-center">
          <p className="text-slate-400 text-xs">Total Trades</p>
          <p className="text-3xl font-bold">{stats.total_trades || 0}</p>
        </div>
        <div className="bg-slate-800 rounded-xl p-6 border border-slate-700 text-center">
          <p className="text-slate-400 text-xs">Win Rate</p>
          <p className="text-3xl font-bold text-amber-400">{(stats.win_rate || 0) > 1 ? (stats.win_rate || 0).toFixed(1) : ((stats.win_rate || 0) * 100).toFixed(0)}%</p>
        </div>
        <div className="bg-slate-800 rounded-xl p-6 border border-slate-700 text-center">
          <p className="text-slate-400 text-xs">Total P&L</p>
          <p className={`text-3xl font-bold ${(stats.total_pnl || 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
            ${(stats.total_pnl || 0).toFixed(2)}
          </p>
        </div>
        <div className="bg-slate-800 rounded-xl p-6 border border-slate-700 text-center">
          <p className="text-slate-400 text-xs">W / L</p>
          <p className="text-3xl font-bold">
            <span className="text-green-400">{stats.wins ?? streak.count ?? 0}</span>
            <span className="text-slate-500 mx-1">/</span>
            <span className="text-red-400">{stats.losses ?? 0}</span>
          </p>
        </div>
      </div>

      {/* Best / Worst Day */}
      {(stats.best_day != null || stats.worst_day != null) && (
        <div className="grid grid-cols-2 gap-4">
          <div className="bg-slate-800 rounded-xl p-6 border border-slate-700 text-center">
            <p className="text-slate-400 text-xs">Best Day</p>
            <p className="text-2xl font-bold text-green-400">+${(stats.best_day ?? 0).toFixed(2)}</p>
          </div>
          <div className="bg-slate-800 rounded-xl p-6 border border-slate-700 text-center">
            <p className="text-slate-400 text-xs">Worst Day</p>
            <p className="text-2xl font-bold text-red-400">${(stats.worst_day ?? 0).toFixed(2)}</p>
          </div>
        </div>
      )}

      {/* Equity Curve */}
      {equityCurve.length > 0 && (
        <div className="bg-slate-800 rounded-xl p-6 border border-slate-700">
          <h2 className="text-lg font-semibold mb-4">📈 Equity Curve</h2>
          <div className="h-48 flex items-end gap-0.5">
            {equityCurve.slice(-60).map((e: any, i: number) => {
              const vals = equityCurve.map((x: any) => x.equity)
              const min = Math.min(...vals); const max = Math.max(...vals)
              const range = max - min || 1
              const height = ((e.equity - min) / range) * 100
              return (
                <div key={i} className="flex-1 bg-green-500/60 hover:bg-green-400 rounded-t transition-colors"
                  style={{ height: `${Math.max(2, height)}%` }}
                  title={`$${e.equity?.toLocaleString()}`}
                />
              )
            })}
          </div>
          <div className="flex justify-between text-xs text-slate-500 mt-1">
            <span>${Math.min(...equityCurve.map((x: any) => x.equity)).toLocaleString()}</span>
            <span>${Math.max(...equityCurve.map((x: any) => x.equity)).toLocaleString()}</span>
          </div>
        </div>
      )}

      {/* By Strategy */}
      {data.by_strategy?.length > 0 && (
        <div className="bg-slate-800 rounded-xl p-6 border border-slate-700">
          <h2 className="text-lg font-semibold mb-4">📋 Performance by Strategy</h2>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-slate-400 border-b border-slate-700">
                <th className="text-left py-2">Strategy</th>
                <th className="text-right py-2">Trades</th>
                <th className="text-right py-2">Win Rate</th>
                <th className="text-right py-2">Total P&L</th>
                <th className="text-right py-2">Avg P&L</th>
                <th className="text-left py-2 w-32">Performance</th>
              </tr>
            </thead>
            <tbody>
              {data.by_strategy.map((s: any) => (
                <tr key={s.strategy} className="border-b border-slate-700/50">
                  <td className="py-2 font-mono font-bold">{s.strategy}</td>
                  <td className="text-right py-2">{s.trades}</td>
                  <td className="text-right py-2">{s.win_rate}%</td>
                  <td className={`text-right py-2 font-bold ${s.total_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                    ${s.total_pnl?.toFixed(2)}
                  </td>
                  <td className="text-right py-2">${s.avg_pnl?.toFixed(2)}</td>
                  <td className="py-2">
                    <div className="w-full bg-slate-700 rounded h-2">
                      <div className={`h-2 rounded ${s.total_pnl >= 0 ? 'bg-green-500' : 'bg-red-500'}`}
                        style={{ width: `${Math.min(100, Math.abs(s.win_rate || 0))}%` }} />
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* By Stock */}
      {data.by_stock?.length > 0 && (
        <div className="bg-slate-800 rounded-xl p-6 border border-slate-700">
          <h2 className="text-lg font-semibold mb-4">📊 Performance by Stock</h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {data.by_stock.slice(0, 12).map((s: any) => (
              <div key={s.symbol} className="bg-slate-700/50 rounded-lg p-3 text-center">
                <p className="font-mono font-bold text-lg">{s.symbol}</p>
                <p className={`text-xl font-bold ${s.total_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                  ${s.total_pnl?.toFixed(2)}
                </p>
                <p className="text-xs text-slate-400">{s.trades}t | WR:{s.win_rate}%</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* By Day */}
      {data.by_day?.length > 0 && (
        <div className="bg-slate-800 rounded-xl p-6 border border-slate-700">
          <h2 className="text-lg font-semibold mb-4">📅 Daily P&L</h2>
          <div className="h-32 flex items-end gap-1">
            {data.by_day.slice(0, 20).reverse().map((d: any, i: number) => {
              const maxPnl = Math.max(...data.by_day.map((x: any) => Math.abs(x.daily_pnl || 0)), 1)
              const height = (Math.abs(d.daily_pnl || 0) / maxPnl) * 100
              return (
                <div key={i} className="flex-1 flex flex-col items-center">
                  <div className={`w-full rounded ${d.daily_pnl >= 0 ? 'bg-green-500' : 'bg-red-500'}`}
                    style={{ height: `${Math.max(4, height)}%` }}
                    title={`${d.trade_date}: $${d.daily_pnl?.toFixed(2)}`} />
                  <span className="text-[8px] text-slate-500 mt-1">{d.trade_date?.slice(5)}</span>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {data.by_strategy?.length === 0 && data.by_stock?.length === 0 && (
        <div className="bg-slate-800 rounded-xl p-6 border border-slate-700 text-center py-10">
          <p className="text-slate-400 text-lg">No trade data yet</p>
          <p className="text-slate-500">Analytics will populate as the bot makes trades</p>
        </div>
      )}
    </div>
  )
}


