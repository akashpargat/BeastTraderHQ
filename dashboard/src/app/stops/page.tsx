'use client'
import { useEffect, useState, useCallback } from 'react'
import { authFetch } from '../../lib/api'

export default function StopsPage() {
  const [data, setData] = useState<any>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  const fetchData = useCallback(async () => {
    try {
      const res = await authFetch('/api/trailing-stops')
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

  if (loading) return <div className="flex items-center justify-center min-h-[50vh]"><div className="text-4xl animate-bounce">��</div></div>
  if (error) return <div className="glass p-6 text-center text-red-400">{error}</div>

  const stops = data?.trailing_stops || []

  return (
    <div className="fade-in">
      <h1 className="text-2xl font-bold mb-6">🛑 Trailing Stops</h1>
      {stops.length === 0 ? (
        <div className="glass p-12 text-center text-gray-500"><div className="text-4xl mb-2">📭</div>No trailing stops active</div>
      ) : (
        <div className="glass p-4 overflow-x-auto">
          <table className="w-full text-sm">
            <thead><tr className="text-gray-400 border-b border-white/10">
              <th className="text-left py-2 px-3">Symbol</th>
              <th className="text-right py-2 px-3">Qty</th>
              <th className="text-right py-2 px-3">Trail %</th>
              <th className="text-right py-2 px-3">Stop Price</th>
              <th className="text-right py-2 px-3">Gap %</th>
            </tr></thead>
            <tbody>
              {stops.map((s: any, i: number) => (
                <tr key={i} className="border-b border-white/5 hover:bg-white/5 transition">
                  <td className="py-2 px-3 font-mono font-semibold">{s?.symbol ?? '—'}</td>
                  <td className="py-2 px-3 text-right">{s?.qty ?? s?.quantity ?? '—'}</td>
                  <td className="py-2 px-3 text-right">{Number(s?.trail_pct ?? s?.trail_percent ?? 0).toFixed(2)}%</td>
                  <td className="py-2 px-3 text-right text-[#ff4444]">${Number(s?.stop_price ?? 0).toFixed(2)}</td>
                  <td className="py-2 px-3 text-right text-yellow-400">{Number(s?.gap_pct ?? s?.gap_to_stop ?? 0).toFixed(2)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
