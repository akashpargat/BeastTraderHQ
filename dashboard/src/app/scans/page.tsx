'use client'
import { useEffect, useState, useCallback } from 'react'
import { authFetch } from '../../lib/api'

export default function ScansPage() {
  const [data, setData] = useState<any>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  const fetchData = useCallback(async () => {
    try {
      const res = await authFetch('/api/scans')
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

  const scans = Array.isArray(data) ? data : (data?.scans || [])

  return (
    <div className="fade-in">
      <h1 className="text-2xl font-bold mb-6">🔍 Scans</h1>
      {scans.length === 0 ? (
        <div className="glass p-12 text-center text-gray-500"><div className="text-4xl mb-2">📭</div>No scans available</div>
      ) : (
        <div className="space-y-3">
          {scans.map((s: any, i: number) => (
            <div key={i} className="glass p-4">
              <div className="flex items-center justify-between mb-2">
                <span className="font-semibold">{s?.name ?? s?.type ?? `Scan #${i + 1}`}</span>
                <span className="text-xs text-gray-500">{s?.timestamp ? new Date(s.timestamp).toLocaleString() : ''}</span>
              </div>
              <div className="flex gap-4 text-sm">
                {s?.tv_count != null && <span className="text-gray-400">TV: <span className="text-white">{s.tv_count}</span></span>}
                {s?.sentiment_count != null && <span className="text-gray-400">Sentiment: <span className="text-white">{s.sentiment_count}</span></span>}
                {s?.ai_count != null && <span className="text-gray-400">AI: <span className="text-white">{s.ai_count}</span></span>}
                {s?.count != null && <span className="text-gray-400">Results: <span className="text-white">{s.count}</span></span>}
              </div>
              {s?.symbols && <div className="text-xs text-gray-500 mt-1 font-mono">{Array.isArray(s.symbols) ? s.symbols.join(', ') : s.symbols}</div>}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
