'use client'
import { useEffect, useState, useCallback } from 'react'
import { authFetch } from '../../lib/api'

export default function AIPage() {
  const [data, setData] = useState<any>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  const fetchData = useCallback(async () => {
    try {
      const res = await authFetch('/api/ai-verdicts')
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

  const verdicts = data?.verdicts || []

  return (
    <div className="fade-in">
      <h1 className="text-2xl font-bold mb-6">🧠 AI Verdicts</h1>
      {verdicts.length === 0 ? (
        <div className="glass p-12 text-center text-gray-500"><div className="text-4xl mb-2">🔄</div>Waiting for next AI scan</div>
      ) : (
        <div className="space-y-3">
          {verdicts.map((v: any, i: number) => {
            const action = (v?.action ?? 'HOLD').toUpperCase()
            const color = action === 'BUY' ? 'bg-[#00ff88]/20 text-[#00ff88]' : action === 'SELL' ? 'bg-[#ff4444]/20 text-[#ff4444]' : 'bg-gray-500/20 text-gray-400'
            return (
              <div key={i} className="glass p-4">
                <div className="flex items-center justify-between mb-2">
                  <span className="font-mono font-bold text-lg">{v?.symbol ?? '—'}</span>
                  <span className={`px-3 py-1 rounded-full text-xs font-bold ${color}`}>{action}</span>
                </div>
                <div className="flex items-center gap-4 text-sm">
                  <span className="text-gray-400">Confidence: <span className="text-white font-semibold">{Number(v?.confidence ?? 0).toFixed(0)}%</span></span>
                </div>
                {v?.reasoning && <p className="text-sm text-gray-400 mt-2">{v.reasoning}</p>}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
