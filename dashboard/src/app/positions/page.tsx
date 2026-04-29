'use client'
import { useEffect, useState } from 'react'

const API = typeof window !== 'undefined' ? 'https://api.beast-trader.com' : 'http://localhost:8080'

export default function PositionsPage() {
  const [portfolio, setPortfolio] = useState<any>(null)

  useEffect(() => {
    const fetch_data = () => fetch(`${API}/api/portfolio`).then(r => r.json()).then(setPortfolio)
    fetch_data()
    const interval = setInterval(fetch_data, 60000)
    return () => clearInterval(interval)
  }, [])

  if (!portfolio) return <div className="text-center py-20 text-slate-400">Loading...</div>

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">💼 Positions</h1>

      <div className="grid grid-cols-3 gap-4">
        <div className="bg-slate-800 rounded-xl p-6 border border-slate-700 text-center">
          <p className="text-slate-400 text-xs">Total Value</p>
          <p className="text-2xl font-bold">${portfolio.equity?.toLocaleString()}</p>
        </div>
        <div className="bg-slate-800 rounded-xl p-6 border border-slate-700 text-center">
          <p className="text-slate-400 text-xs">Day P&L</p>
          <p className={`text-2xl font-bold ${portfolio.total_pl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
            ${portfolio.total_pl?.toFixed(2)}
          </p>
        </div>
        <div className="bg-slate-800 rounded-xl p-6 border border-slate-700 text-center">
          <p className="text-slate-400 text-xs">Buying Power</p>
          <p className="text-2xl font-bold text-slate-300">${portfolio.buying_power?.toLocaleString()}</p>
        </div>
      </div>

      {/* Position Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {portfolio.positions?.map((p: any) => (
          <div key={p.symbol} className={`card border-l-4 ${p.is_green ? 'border-l-green-500' : 'border-l-red-500'}`}>
            <div className="flex justify-between items-start mb-3">
              <div>
                <h3 className="text-lg font-bold font-mono">{p.symbol}</h3>
                <p className="text-slate-400 text-sm">{p.qty} shares @ ${p.avg_entry.toFixed(2)}</p>
              </div>
              <div className="text-right">
                <p className="text-lg font-mono">${p.current_price.toFixed(2)}</p>
                <p className={`text-sm font-bold ${p.is_green ? 'text-green-400' : 'text-red-400'}`}>
                  ${p.unrealized_pl.toFixed(2)} ({p.pct.toFixed(1)}%)
                </p>
              </div>
            </div>
            {/* P&L Bar */}
            <div className="w-full bg-slate-700 rounded-full h-2 mt-2">
              <div className={`h-2 rounded-full ${p.is_green ? 'bg-green-500' : 'bg-red-500'}`}
                style={{ width: `${Math.min(100, Math.abs(p.pct) * 10)}%` }} />
            </div>
            <div className="flex justify-between text-xs text-slate-500 mt-1">
              <span>Value: ${p.market_value.toLocaleString()}</span>
              <span>{p.pct >= 5 ? '🏃 RUNNER' : p.pct >= 2 ? '🎯 SCALP' : p.pct >= 0 ? '✅ HOLD' : p.pct > -5 ? '🔒 HOLD' : '⚠️ DEEP RED'}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}


