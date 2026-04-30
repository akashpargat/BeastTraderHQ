'use client'
import { useEffect, useState, useCallback } from 'react'
import { authFetch } from '../../lib/api'

export default function NewsPage() {
  const [data, setData] = useState<any>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  const fetchData = useCallback(async () => {
    try {
      const res = await authFetch('/api/live-feed')
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

  const items = data?.feed || []

  return (
    <div className="fade-in">
      <h1 className="text-2xl font-bold mb-6">📰 News Feed</h1>
      {items.length === 0 ? (
        <div className="glass p-12 text-center text-gray-500"><div className="text-4xl mb-2">📭</div>No news available</div>
      ) : (
        <div className="space-y-3">
          {items.map((n: any, i: number) => (
            <div key={i} className="glass p-4">
              <div className="flex items-center gap-2 mb-1">
                {n?.category && <span className="px-2 py-0.5 rounded text-xs font-bold bg-blue-500/20 text-blue-400">{n.category}</span>}
                {n?.type && !n?.category && <span className="px-2 py-0.5 rounded text-xs font-bold bg-purple-500/20 text-purple-400">{n.type}</span>}
                <span className="text-xs text-gray-500">{n?.timestamp ? new Date(n.timestamp).toLocaleString() : ''}</span>
              </div>
              <div className="text-sm">{n?.headline ?? n?.title ?? n?.message ?? '—'}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
