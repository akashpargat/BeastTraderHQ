'use client'
import { useEffect, useState, useCallback } from 'react'
import { authFetch } from '../../lib/api'

export default function TradesPage() {
  const [data, setData] = useState<any>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  const fetchData = useCallback(async () => {
    try {
      const res = await authFetch('/api/trades')
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

  const trades = data?.trades || []

  return (
    <div className="fade-in">
      <h1 className="text-2xl font-bold mb-6">📈 Trade History</h1>
      {trades.length === 0 ? (
        <div className="glass p-12 text-center text-gray-500"><div className="text-4xl mb-2">📭</div>No trades yet</div>
      ) : (
        <div className="glass p-4 overflow-x-auto">
          <table className="w-full text-sm">
            <thead><tr className="text-gray-400 border-b border-white/10">
              <th className="text-left py-2 px-3">Time</th>
              <th className="text-left py-2 px-3">Symbol</th>
              <th className="text-left py-2 px-3">Side</th>
              <th className="text-right py-2 px-3">Qty</th>
              <th className="text-right py-2 px-3">Price</th>
              <th className="text-right py-2 px-3">Status</th>
            </tr></thead>
            <tbody>
              {trades.map((t: any, i: number) => (
                <tr key={i} className="border-b border-white/5 hover:bg-white/5 transition">
                  <td className="py-2 px-3 text-gray-400">{t?.timestamp || t?.time ? new Date(t.timestamp || t.time).toLocaleString() : '—'}</td>
                  <td className="py-2 px-3 font-mono font-semibold">{t?.symbol ?? '—'}</td>
                  <td className="py-2 px-3">
                    <span className={`px-2 py-0.5 rounded text-xs font-bold ${(t?.side ?? '').toUpperCase() === 'BUY' ? 'bg-[#00ff88]/20 text-[#00ff88]' : 'bg-[#ff4444]/20 text-[#ff4444]'}`}>
                      {(t?.side ?? '—').toUpperCase()}
                    </span>
                  </td>
                  <td className="py-2 px-3 text-right">{t?.qty ?? t?.quantity ?? '—'}</td>
                  <td className="py-2 px-3 text-right">${Number(t?.price ?? 0).toFixed(2)}</td>
                  <td className="py-2 px-3 text-right text-gray-400">{t?.status ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
