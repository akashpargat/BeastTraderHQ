'use client'
import { useEffect, useState, useCallback } from 'react'
import { authFetch } from '../../lib/api'

export default function RunnersPage() {
  const [data, setData] = useState<any>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  const fetchData = useCallback(async () => {
    try {
      const res = await authFetch('/api/runners')
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

  const runners = data?.runners || []

  return (
    <div className="fade-in">
      <h1 className="text-2xl font-bold mb-6">🏃 Runners</h1>
      {runners.length === 0 ? (
        <div className="glass p-12 text-center text-gray-500"><div className="text-4xl mb-2">📭</div>No runners detected</div>
      ) : (
        <div className="glass p-4 overflow-x-auto">
          <table className="w-full text-sm">
            <thead><tr className="text-gray-400 border-b border-white/10">
              <th className="text-left py-2 px-3">Symbol</th>
              <th className="text-right py-2 px-3">Price</th>
              <th className="text-right py-2 px-3">Change %</th>
              <th className="text-right py-2 px-3">Volume</th>
            </tr></thead>
            <tbody>
              {runners.map((r: any, i: number) => {
                const chg = Number(r?.change_pct ?? r?.change ?? 0)
                return (
                  <tr key={i} className="border-b border-white/5 hover:bg-white/5 transition">
                    <td className="py-2 px-3 font-mono font-semibold">{r?.symbol ?? '—'}</td>
                    <td className="py-2 px-3 text-right">${Number(r?.price ?? 0).toFixed(2)}</td>
                    <td className={`py-2 px-3 text-right font-semibold ${chg >= 0 ? 'text-[#00ff88]' : 'text-[#ff4444]'}`}>
                      {chg >= 0 ? '+' : ''}{chg.toFixed(2)}%
                    </td>
                    <td className="py-2 px-3 text-right text-gray-400">{Number(r?.volume ?? 0).toLocaleString()}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
