'use client'
import { useEffect, useState, useCallback } from 'react'
import { authFetch } from '../../lib/api'

export default function PositionsPage() {
  const [data, setData] = useState<any>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  const fetchData = useCallback(async () => {
    try {
      const res = await authFetch('/api/portfolio')
      if (res.ok) { setData(await res.json()); setError('') }
      else setError(`API error: ${res.status}`)
    } catch (e: any) { setError(e.message || 'Connection failed') }
    setLoading(false)
  }, [])

  useEffect(() => {
    fetchData()
    const i = setInterval(fetchData, 10000)
    return () => clearInterval(i)
  }, [fetchData])

  if (loading) return <div className="flex items-center justify-center min-h-[50vh]"><div className="text-4xl animate-bounce">🦍</div></div>
  if (error) return <div className="glass p-6 text-center text-red-400">{error}</div>

  const positions = (data?.positions || []).sort((a: any, b: any) => (b?.pnl ?? 0) - (a?.pnl ?? 0))

  return (
    <div className="fade-in">
      <h1 className="text-2xl font-bold mb-6">📊 Positions</h1>
      {positions.length === 0 ? (
        <div className="glass p-12 text-center text-gray-500">
          <div className="text-4xl mb-2">📭</div>No open positions
        </div>
      ) : (
        <div className="grid md:grid-cols-2 gap-4">
          {positions.map((p: any, i: number) => {
            const pnl = p?.pnl ?? p?.unrealized_pl ?? 0
            const pct = p?.pnl_pct ?? p?.unrealized_plpc ?? 0
            const isGreen = pnl >= 0
            return (
              <div key={i} className="glass p-4">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <div className={`w-2 h-2 rounded-full ${isGreen ? 'bg-[#00ff88]' : 'bg-[#ff4444]'}`} />
                    <span className="font-mono font-bold text-lg">{p?.symbol ?? '—'}</span>
                  </div>
                  <span className="text-gray-400 text-sm">{p?.qty ?? p?.quantity ?? 0} shares</span>
                </div>
                <div className="grid grid-cols-2 gap-2 text-sm">
                  <div><span className="text-gray-400">Price:</span> ${Number(p?.current_price ?? p?.price ?? 0).toFixed(2)}</div>
                  <div><span className="text-gray-400">Entry:</span> ${Number(p?.avg_entry ?? p?.entry_price ?? 0).toFixed(2)}</div>
                  <div><span className="text-gray-400">P&L:</span> <span className={isGreen ? 'text-[#00ff88]' : 'text-[#ff4444]'}>{isGreen ? '+' : ''}${Number(pnl).toFixed(2)}</span></div>
                  <div><span className="text-gray-400">%:</span> <span className={isGreen ? 'text-[#00ff88]' : 'text-[#ff4444]'}>{isGreen ? '+' : ''}{(Number(pct) * (Math.abs(Number(pct)) < 1 ? 100 : 1)).toFixed(2)}%</span></div>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
