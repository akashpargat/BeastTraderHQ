'use client'
import { useEffect, useState } from 'react'

const API = typeof window !== 'undefined' ? 'https://api.beast-trader.com' : 'http://localhost:8080'

export default function TradesPage() {
  const [trades, setTrades] = useState<any[]>([])

  useEffect(() => {
    fetch(`${API}/api/trades?limit=50`).then(r => r.json()).then(d => setTrades(d.trades || []))
  }, [])

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">📋 Trade History</h1>

      {trades.length === 0 ? (
        <div className="bg-slate-800 rounded-xl p-6 border border-slate-700 text-center py-10">
          <p className="text-slate-400">No trades logged yet. Trades appear as the bot auto-executes.</p>
        </div>
      ) : (
        <div className="bg-slate-800 rounded-xl p-6 border border-slate-700 overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-slate-400 border-b border-slate-700">
                <th className="text-left py-2 px-3">Time</th>
                <th className="text-left py-2 px-3">Symbol</th>
                <th className="text-left py-2 px-3">Side</th>
                <th className="text-right py-2 px-3">Qty</th>
                <th className="text-right py-2 px-3">Price</th>
                <th className="text-right py-2 px-3">P&L</th>
                <th className="text-left py-2 px-3">Strategy</th>
                <th className="text-left py-2 px-3">Reason</th>
              </tr>
            </thead>
            <tbody>
              {trades.map((t: any) => (
                <tr key={t.id} className="hover:bg-slate-700/50 border-b border-slate-700/50">
                  <td className="py-2 px-3 text-slate-400 text-xs">{t.created_at?.slice(0, 16)}</td>
                  <td className="py-2 px-3 font-mono font-bold">{t.symbol}</td>
                  <td className="py-2 px-3">
                    <span className={`px-2 py-0.5 rounded text-xs ${t.side === 'buy' ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}`}>
                      {t.side?.toUpperCase()}
                    </span>
                  </td>
                  <td className="text-right py-2 px-3">{t.qty}</td>
                  <td className="text-right py-2 px-3 font-mono">${t.price?.toFixed(2)}</td>
                  <td className={`text-right py-2 px-3 font-bold ${(t.pnl || 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                    {t.exit_price > 0 ? `$${t.pnl?.toFixed(2)}` : '—'}
                  </td>
                  <td className="py-2 px-3 text-slate-400">{t.strategy}</td>
                  <td className="py-2 px-3 text-slate-500 text-xs max-w-xs truncate">{t.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}


