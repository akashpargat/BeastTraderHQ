'use client'
import { useEffect, useState } from 'react'

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8080'

interface Position {
  symbol: string; qty: number; avg_entry: number; current_price: number;
  market_value: number; unrealized_pl: number; pct: number; is_green: boolean;
}

interface Portfolio {
  equity: number; buying_power: number; cash: number; total_pl: number;
  positions: Position[]; open_orders: any[]; positions_count: number; orders_count: number;
  timestamp: string;
}

interface Scan {
  timestamp: string; regime: string; equity: number; total_pl: number;
  tv_reads: number; sentiments: number; ai_calls: number; trump_score: number;
}

export default function Dashboard() {
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null)
  const [scans, setScans] = useState<Scan[]>([])
  const [system, setSystem] = useState<any>(null)
  const [lastUpdate, setLastUpdate] = useState('')

  const fetchAll = async () => {
    try {
      const [pRes, sRes, sysRes] = await Promise.all([
        fetch(`${API}/api/portfolio`),
        fetch(`${API}/api/scans?limit=10`),
        fetch(`${API}/api/system`),
      ])
      setPortfolio(await pRes.json())
      const scanData = await sRes.json()
      setScans(scanData.scans || [])
      setSystem(await sysRes.json())
      setLastUpdate(new Date().toLocaleTimeString())
    } catch (e) {
      console.error('Fetch failed:', e)
    }
  }

  useEffect(() => {
    fetchAll()
    const interval = setInterval(fetchAll, 60000) // Refresh every 60s
    return () => clearInterval(interval)
  }, [])

  if (!portfolio) return <div className="text-center py-20 text-slate-400">Loading Beast Engine...</div>

  const greens = portfolio.positions.filter(p => p.is_green).length
  const reds = portfolio.positions.length - greens

  return (
    <div className="space-y-6">
      {/* Header Stats */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <StatCard label="Portfolio" value={`$${portfolio.equity.toLocaleString()}`} />
        <StatCard label="Day P&L" value={`$${portfolio.total_pl.toFixed(2)}`}
          color={portfolio.total_pl >= 0 ? 'green' : 'red'} />
        <StatCard label="Positions" value={`${portfolio.positions_count}`}
          sub={`🟢${greens} 🔴${reds}`} />
        <StatCard label="Open Orders" value={`${portfolio.orders_count}`} />
        <StatCard label="Last Update" value={lastUpdate} sub="Auto-refresh 60s" />
      </div>

      {/* System Status Bar */}
      {system && (
        <div className="flex gap-4 text-sm">
          <StatusBadge label="AI Brain" status={system.ai?.status} />
          <StatusBadge label="TradingView" status={system.tv?.status === 'connected' ? 'online' : 'offline'} />
          <StatusBadge label="Discord Bot" status={system.bot?.status === 'running' ? 'online' : 'offline'} />
        </div>
      )}

      {/* Positions Table */}
      <div className="bg-slate-800 rounded-xl p-6 border border-slate-700">
        <h2 className="text-lg font-semibold mb-4">💼 Live Positions</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-slate-400 border-b border-slate-700">
                <th className="text-left py-2 px-3">Stock</th>
                <th className="text-right py-2 px-3">Qty</th>
                <th className="text-right py-2 px-3">Entry</th>
                <th className="text-right py-2 px-3">Current</th>
                <th className="text-right py-2 px-3">Value</th>
                <th className="text-right py-2 px-3">P&L</th>
                <th className="text-right py-2 px-3">%</th>
                <th className="text-left py-2 px-3">Action</th>
              </tr>
            </thead>
            <tbody>
              {portfolio.positions.map(p => (
                <tr key={p.symbol} className="hover:bg-slate-700/50 border-b border-slate-700/50">
                  <td className="py-2.5 px-3 font-mono font-bold">
                    <span className={p.is_green ? 'text-green-400' : 'text-red-400'}>
                      {p.is_green ? '▲' : '▼'} {p.symbol}
                    </span>
                  </td>
                  <td className="text-right py-2.5 px-3">{p.qty}</td>
                  <td className="text-right py-2.5 px-3 text-slate-400">${p.avg_entry.toFixed(2)}</td>
                  <td className="text-right py-2.5 px-3 font-mono">${p.current_price.toFixed(2)}</td>
                  <td className="text-right py-2.5 px-3">${p.market_value.toLocaleString()}</td>
                  <td className={`text-right py-2.5 px-3 font-bold ${p.is_green ? 'text-green-400' : 'text-red-400'}`}>
                    ${p.unrealized_pl.toFixed(2)}
                  </td>
                  <td className={`text-right py-2.5 px-3 ${p.is_green ? 'text-green-400' : 'text-red-400'}`}>
                    {p.pct.toFixed(1)}%
                  </td>
                  <td className="py-2.5 px-3">
                    {p.pct >= 5 ? <Badge text="RUNNER" color="purple" /> :
                     p.pct >= 2 ? <Badge text="SCALP" color="green" /> :
                     p.pct >= 0 ? <Badge text="HOLD" color="gray" /> :
                     p.pct > -5 ? <Badge text="HOLD" color="yellow" /> :
                     <Badge text="DEEP RED" color="red" />}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Recent Scans */}
      <div className="bg-slate-800 rounded-xl p-6 border border-slate-700">
        <h2 className="text-lg font-semibold mb-4">🔍 Recent AI Scans</h2>
        {scans.length === 0 ? (
          <p className="text-slate-400">No scans yet — first scan runs in ~5 minutes</p>
        ) : (
          <div className="space-y-2">
            {scans.slice(0, 5).map((s, i) => (
              <div key={i} className="flex justify-between items-center py-2 border-b border-slate-700/50 text-sm">
                <span className="text-slate-400">{s.timestamp?.slice(11, 19)}</span>
                <span className="font-mono">{s.regime}</span>
                <span className={s.total_pl >= 0 ? 'text-green-400' : 'text-red-400'}>
                  ${s.total_pl?.toFixed(2)}
                </span>
                <span className="text-slate-400">TV:{s.tv_reads} AI:{s.ai_calls}</span>
                <span className="text-slate-400">Trump:{s.trump_score}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Open Orders */}
      {portfolio.open_orders.length > 0 && (
        <div className="bg-slate-800 rounded-xl p-6 border border-slate-700">
          <h2 className="text-lg font-semibold mb-4">📋 Open Orders ({portfolio.orders_count})</h2>
          <div className="space-y-1">
            {portfolio.open_orders.map((o: any, i: number) => (
              <div key={i} className="flex justify-between text-sm py-1.5 border-b border-slate-700/50">
                <span className={o.side === 'buy' ? 'text-green-400' : 'text-red-400'}>
                  {o.side?.toUpperCase()} {o.symbol}
                </span>
                <span>x{o.qty} @ ${o.limit_price}</span>
                <span className="text-slate-400">{o.status}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function StatCard({ label, value, sub, color }: { label: string; value: string; sub?: string; color?: string }) {
  const colorClass = color === 'green' ? 'text-green-400' : color === 'red' ? 'text-red-400' : 'text-white'
  return (
    <div className="bg-slate-800 rounded-xl p-6 border border-slate-700 text-center">
      <p className="text-slate-400 text-xs uppercase mb-1">{label}</p>
      <p className={`text-xl font-bold ${colorClass}`}>{value}</p>
      {sub && <p className="text-slate-500 text-xs mt-1">{sub}</p>}
    </div>
  )
}

function StatusBadge({ label, status }: { label: string; status: string }) {
  const isOnline = status === 'online'
  return (
    <span className={`px-3 py-1 rounded-full text-xs ${isOnline ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}`}>
      {isOnline ? '●' : '○'} {label}
    </span>
  )
}

function Badge({ text, color }: { text: string; color: string }) {
  const colors: Record<string, string> = {
    green: 'bg-green-500/20 text-green-400',
    red: 'bg-red-500/20 text-red-400',
    yellow: 'bg-yellow-500/20 text-yellow-400',
    purple: 'bg-purple-500/20 text-purple-400',
    gray: 'bg-slate-600/30 text-slate-300',
  }
  return <span className={`px-2 py-0.5 rounded text-xs ${colors[color] || colors.gray}`}>{text}</span>
}

