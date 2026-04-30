'use client'
import { useEffect, useState, useCallback } from 'react'

const API = 'https://api.beast-trader.com'

export default function TradesPage() {
  const [trades, setTrades] = useState<any[]>([])
  const [loading, setLoading] = useState(true)

  const fetchData = useCallback(() => {
    fetch(`${API}/api/trades?limit=50`)
      .then(r => r.json())
      .then(d => {
        setTrades(d.trades || [])
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [])

  useEffect(() => {
    fetchData()
    const interval = setInterval(fetchData, 30000)
    return () => clearInterval(interval)
  }, [fetchData])

  function extractStrategy(t: any): string {
    if (t.strategy) return t.strategy
    const cid = t.client_order_id || ''
    if (cid.includes('scalp')) return 'Scalp'
    if (cid.includes('runner')) return 'Runner'
    if (cid.includes('dip')) return 'Dip'
    if (cid.includes('protect')) return 'Protect'
    if (cid.includes('earn')) return 'Earnings'
    return cid.split('-')[0] || '—'
  }

  if (loading) return (
    <div className="space-y-4">
      <div className="h-8 bg-slate-800 rounded animate-pulse w-48" />
      {[...Array(6)].map((_, i) => <div key={i} className="h-12 bg-slate-800 rounded-xl animate-pulse" />)}
    </div>
  )

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">📋 Trade History</h1>
        <span className="text-xs text-slate-500">{trades.length} fills</span>
      </div>

      {trades.length === 0 ? (
        <div className="bg-slate-800 rounded-xl p-6 border border-slate-700 text-center py-10">
          <p className="text-slate-400">No trades logged yet. Trades appear as the bot auto-executes.</p>
        </div>
      ) : (
        <div className="bg-slate-800 rounded-xl border border-slate-700 overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-slate-400 border-b border-slate-700 text-xs uppercase">
                <th className="text-left py-3 px-3">Time</th>
                <th className="text-left py-3 px-3">Symbol</th>
                <th className="text-left py-3 px-3">Side</th>
                <th className="text-right py-3 px-3">Qty</th>
                <th className="text-right py-3 px-3">Price</th>
                <th className="text-left py-3 px-3">Strategy</th>
                <th className="text-left py-3 px-3">Status</th>
              </tr>
            </thead>
            <tbody>
              {trades.map((t: any, idx: number) => {
                const side = (t.side || '').toLowerCase()
                const time = t.filled_at || t.created_at || t.time || ''
                return (
                  <tr key={t.id || idx} className="hover:bg-slate-700/50 border-b border-slate-700/50">
                    <td className="py-2 px-3 text-slate-400 text-xs font-mono">{time ? new Date(time).toLocaleString() : '—'}</td>
                    <td className="py-2 px-3 font-mono font-bold text-white">{t.symbol}</td>
                    <td className="py-2 px-3">
                      <span className={`px-2 py-0.5 rounded text-xs font-bold ${
                        side === 'buy' ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'
                      }`}>
                        {side === 'buy' ? '🟢 BUY' : '🔴 SELL'}
                      </span>
                    </td>
                    <td className="text-right py-2 px-3 font-mono">{t.qty || t.filled_qty || '—'}</td>
                    <td className="text-right py-2 px-3 font-mono">${Number(t.filled_avg_price || t.price || 0).toFixed(2)}</td>
                    <td className="py-2 px-3">
                      <span className="text-xs bg-slate-700 px-2 py-0.5 rounded text-slate-300">{extractStrategy(t)}</span>
                    </td>
                    <td className="py-2 px-3">
                      <span className={`text-xs px-2 py-0.5 rounded ${
                        t.status === 'filled' ? 'bg-green-500/15 text-green-400' :
                        t.status === 'partially_filled' ? 'bg-yellow-500/15 text-yellow-400' :
                        'bg-slate-700 text-slate-400'
                      }`}>{(t.status || 'filled').toUpperCase()}</span>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
      <p className="text-xs text-slate-600 text-center">Auto-refreshes every 30s</p>
    </div>
  )
}