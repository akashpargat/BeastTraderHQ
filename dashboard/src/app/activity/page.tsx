'use client'
import { useEffect, useState, useCallback } from 'react'
import { authFetch } from '../../lib/api'

export default function ActivityPage() {
  const [data, setData] = useState<any>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  const fetchData = useCallback(async () => {
    try {
      const res = await authFetch('/api/actions?limit=50')
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

  const actions = data?.actions || []

  return (
    <div className="fade-in">
      <h1 className="text-2xl font-bold mb-6">⚡ Bot Activity</h1>
      {actions.length === 0 ? (
        <div className="glass p-12 text-center text-gray-500"><div className="text-4xl mb-2">📭</div>No activity yet</div>
      ) : (
        <div className="space-y-2">
          {actions.map((a: any, i: number) => (
            <div key={i} className="glass p-3 flex items-center gap-4">
              <span className="text-xs text-gray-500 w-40 flex-shrink-0">{a?.timestamp ? new Date(a.timestamp).toLocaleString() : '—'}</span>
              <span className="px-2 py-0.5 rounded text-xs font-bold bg-white/10 text-gray-300 flex-shrink-0">{a?.type ?? a?.action ?? '—'}</span>
              <span className="font-mono text-[#00ff88]">{a?.symbol ?? ''}</span>
              <span className="text-sm text-gray-400 truncate">{a?.details ?? a?.message ?? ''}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
