'use client'
import { useEffect, useState } from 'react'
import { authFetch } from '../../lib/api'

export default function BacktestPage() {
  const [whatIf, setWhatIf] = useState<any>(null)
  const [historical, setHistorical] = useState<any>(null)
  const [symbol, setSymbol] = useState('GOOGL')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const loadWhatIf = async () => {
    setLoading(true)
    try {
      const res = await authFetch('/api/v4/backtest/what-if')
      if (res.ok) setWhatIf(await res.json())
    } catch (e: any) { setError(e.message) }
    setLoading(false)
  }

  const loadHistorical = async () => {
    setLoading(true)
    try {
      const res = await authFetch(`/api/v4/backtest/historical?symbol=${symbol}&days=90&strategy=all`)
      if (res.ok) setHistorical(await res.json())
    } catch (e: any) { setError(e.message) }
    setLoading(false)
  }

  useEffect(() => { loadWhatIf() }, [])

  return (
    <div className="fade-in space-y-6">
      <h1 className="text-2xl font-bold">🔬 Backtesting</h1>
      {error && <div className="glass p-3 text-red-400 text-sm">{error}</div>}

      {/* What-If Scenarios */}
      <div className="glass p-4">
        <h2 className="text-lg font-semibold mb-3">📊 What-If Analysis (past 7 days)</h2>
        <p className="text-xs text-gray-500 mb-3">Replays your actual trade decisions with different settings. Shows how much more/less you would have made.</p>
        {!whatIf ? (
          <div className="text-center py-4 text-gray-500">Loading scenarios...</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="text-gray-400 border-b border-white/10">
                <th className="text-left py-2 px-3">Scenario</th>
                <th className="text-right py-2 px-3">Trades</th>
                <th className="text-right py-2 px-3">Win Rate</th>
                <th className="text-right py-2 px-3">Total P&L</th>
                <th className="text-right py-2 px-3">Avg P&L</th>
                <th className="text-right py-2 px-3">PF</th>
              </tr></thead>
              <tbody>
                {Object.entries(whatIf).map(([name, s]: [string, any]) => {
                  const isBase = name === 'current_settings'
                  return (
                    <tr key={name} className={`border-b border-white/5 ${isBase ? 'bg-white/5' : ''}`}>
                      <td className="py-2 px-3">
                        {isBase ? '📌 ' : '🔄 '}{name.replace(/_/g, ' ')}
                      </td>
                      <td className="py-2 px-3 text-right">{s.trades}</td>
                      <td className={`py-2 px-3 text-right ${(s.win_rate || 0) >= 60 ? 'text-[#00ff88]' : 'text-[#ff4444]'}`}>
                        {(s.win_rate || 0).toFixed(0)}%
                      </td>
                      <td className={`py-2 px-3 text-right font-semibold ${(s.total_pnl || 0) >= 0 ? 'text-[#00ff88]' : 'text-[#ff4444]'}`}>
                        ${(s.total_pnl || 0).toFixed(0)}
                      </td>
                      <td className="py-2 px-3 text-right">${(s.avg_pnl || 0).toFixed(0)}</td>
                      <td className="py-2 px-3 text-right">{(s.profit_factor || 0).toFixed(1)}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Historical Strategy Test */}
      <div className="glass p-4">
        <h2 className="text-lg font-semibold mb-3">📈 Historical Strategy Test (90 days)</h2>
        <div className="flex gap-3 mb-4">
          <input value={symbol} onChange={e => setSymbol(e.target.value.toUpperCase())}
            placeholder="Symbol" className="bg-white/5 border border-white/10 rounded px-3 py-2 text-white w-28" />
          <button onClick={loadHistorical} disabled={loading}
            className="px-4 py-2 bg-[#00ff88]/20 text-[#00ff88] rounded hover:bg-[#00ff88]/30 transition disabled:opacity-50">
            {loading ? 'Testing...' : 'Run Backtest'}
          </button>
        </div>

        {historical && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="text-gray-400 border-b border-white/10">
                <th className="text-left py-2 px-3">Strategy</th>
                <th className="text-right py-2 px-3">Trades</th>
                <th className="text-right py-2 px-3">Win Rate</th>
                <th className="text-right py-2 px-3">Total P&L</th>
                <th className="text-right py-2 px-3">Avg P&L</th>
                <th className="text-right py-2 px-3">PF</th>
                <th className="text-right py-2 px-3">Max DD</th>
              </tr></thead>
              <tbody>
                {Object.entries(historical).map(([strat, s]: [string, any]) => (
                  <tr key={strat} className="border-b border-white/5 hover:bg-white/5">
                    <td className="py-2 px-3 font-mono">{strat}</td>
                    <td className="py-2 px-3 text-right">{s.trades}</td>
                    <td className={`py-2 px-3 text-right ${(s.win_rate || 0) >= 55 ? 'text-[#00ff88]' : 'text-[#ff4444]'}`}>
                      {(s.win_rate || 0).toFixed(0)}%
                    </td>
                    <td className={`py-2 px-3 text-right font-semibold ${(s.total_pnl || 0) >= 0 ? 'text-[#00ff88]' : 'text-[#ff4444]'}`}>
                      ${(s.total_pnl || 0).toFixed(0)}
                    </td>
                    <td className="py-2 px-3 text-right">${(s.avg_pnl || 0).toFixed(0)}</td>
                    <td className="py-2 px-3 text-right">{(s.profit_factor || 0).toFixed(1)}</td>
                    <td className="py-2 px-3 text-right text-[#ff4444]">{(s.max_drawdown || 0).toFixed(1)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
