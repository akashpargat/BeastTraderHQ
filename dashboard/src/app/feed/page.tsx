'use client'
import { useEffect, useState, useCallback } from 'react'
import { authFetch } from '../../lib/api'

export default function FeedPage() {
  const [data, setData] = useState<any>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState('ALL')

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

  const allItems = data?.feed || []
  const filtered = filter === 'ALL' ? allItems : allItems.filter((f: any) => (f?.type ?? f?.category ?? '').toUpperCase() === filter)
  const tabs = ['ALL', 'NEWS', 'TRADE', 'CATALYST']

  return (
    <div className="fade-in">
      <h1 className="text-2xl font-bold mb-4">📡 Live Feed</h1>
      <div className="flex gap-2 mb-4">
        {tabs.map(t => (
          <button key={t} onClick={() => setFilter(t)}
            className={`px-4 py-1.5 rounded-full text-sm font-semibold transition ${filter === t ? 'bg-white/10 text-white' : 'text-gray-500 hover:text-gray-300'}`}>
            {t}
          </button>
        ))}
      </div>
      {filtered.length === 0 ? (
        <div className="glass p-12 text-center text-gray-500"><div className="text-4xl mb-2">📭</div>No items</div>
      ) : (
        <div className="space-y-2">
          {filtered.map((f: any, i: number) => (
            <div key={i} className="glass p-3 flex items-start gap-3">
              <div className="flex-shrink-0 mt-1">
                <span className="px-2 py-0.5 rounded text-xs font-bold bg-white/10 text-gray-300">{f?.type ?? f?.category ?? '—'}</span>
              </div>
              <div className="flex-1 text-sm">
                <span className="font-mono text-[#00ff88] mr-2">{f?.symbol ?? ''}</span>
                {f?.headline ?? f?.title ?? f?.message ?? '—'}
              </div>
              <span className="text-xs text-gray-500 flex-shrink-0">{f?.timestamp ? new Date(f.timestamp).toLocaleTimeString() : ''}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
