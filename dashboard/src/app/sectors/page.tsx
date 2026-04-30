'use client'
import { useEffect, useState, useCallback } from 'react'
import { authFetch } from '../../lib/api'

export default function SectorsPage() {
  const [data, setData] = useState<any>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  const fetchData = useCallback(async () => {
    try {
      const res = await authFetch('/api/sectors')
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

  const sectors = Object.entries(data?.sectors || data || {}).filter(([k]) => k !== 'timestamp' && k !== 'status')

  return (
    <div className="fade-in">
      <h1 className="text-2xl font-bold mb-6">🏭 Sectors</h1>
      {sectors.length === 0 ? (
        <div className="glass p-12 text-center text-gray-500"><div className="text-4xl mb-2">📭</div>Sector data unavailable</div>
      ) : (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
          {sectors.map(([name, val]: [string, any], i) => {
            const change = typeof val === 'number' ? val : Number(val?.avg_change ?? val?.change ?? val?.change_pct ?? 0)
            const isGreen = change >= 0
            const sampled = val?.stocks_sampled ?? 0
            return (
              <div key={i} className="glass p-4 text-center">
                <div className="text-sm text-gray-300 mb-1">{name}</div>
                <div className={`text-xl font-bold ${isGreen ? 'text-[#00ff88]' : 'text-[#ff4444]'}`}>
                  {isGreen ? '+' : ''}{change.toFixed(2)}%
                </div>
                {sampled > 0 && <div className="text-xs text-gray-500">{sampled} stocks</div>}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
