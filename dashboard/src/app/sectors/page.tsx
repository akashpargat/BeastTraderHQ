'use client'
import { useEffect, useState, useCallback } from 'react'
import { authFetch } from '../../lib/api'

function heatColor(pct: number): string {
  if (pct <= -3) return 'bg-red-900 border-red-700 text-red-300'
  if (pct <= -1) return 'bg-red-800/60 border-red-700/60 text-red-300'
  if (pct < 0) return 'bg-yellow-900/40 border-yellow-700/40 text-yellow-300'
  if (pct < 1) return 'bg-green-900/30 border-green-700/30 text-green-300'
  if (pct < 3) return 'bg-green-800/60 border-green-600/50 text-green-300'
  return 'bg-green-700 border-green-500 text-green-100'
}

export default function SectorsPage() {
  const [sectors, setSectors] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const fetchData = useCallback(() => {
    authFetch('/api/sectors')
      .then(r => {
        if (!r.ok) throw new Error(`API returned ${r.status}`)
        return r.json()
      })
      .then(data => {
        // sectors comes as an object {sectorName: {avg_change, ...}}
        const raw = data.sectors || data
        if (typeof raw === 'object' && !Array.isArray(raw)) {
          const arr = Object.entries(raw).map(([name, info]: [string, any]) => ({
            name,
            ...info,
          }))
          setSectors(arr)
        } else {
          setSectors(Array.isArray(raw) ? raw : [])
        }
        if (data.market_closed) {
          setError('market_closed')
        } else {
          setError('')
        }
        setLoading(false)
      })
      .catch((e) => {
        setError(e.message || 'Failed to load sector data')
        setLoading(false)
      })
  }, [])

  useEffect(() => {
    fetchData()
    const interval = setInterval(fetchData, 60000)
    return () => clearInterval(interval)
  }, [fetchData])

  if (loading) return (
    <div className="space-y-4">
      <div className="h-8 bg-slate-800 rounded animate-pulse w-48" />
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
        {[...Array(8)].map((_, i) => <div key={i} className="h-32 bg-slate-800 rounded-xl animate-pulse" />)}
      </div>
    </div>
  )

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">🗺️ Sector Heatmap</h1>

      {error === 'market_closed' && (
        <div className="bg-yellow-500/10 border border-yellow-500/30 rounded-xl p-6 text-center">
          <div className="text-4xl mb-2">🗺️</div>
          <p className="text-slate-400 text-lg">Sectors Offline</p>
          <p className="text-slate-500 text-sm">Live sector data available during market hours</p>
        </div>
      )}

      {error && error !== 'market_closed' && (
        <div className="bg-yellow-500/10 border border-yellow-500/30 rounded-xl p-6 text-center">
          <p className="text-yellow-400 text-lg mb-1">⚠️ Sector Data Unavailable</p>
          <p className="text-slate-400 text-sm">Market may be closed or data is loading. Will retry automatically.</p>
          <p className="text-slate-500 text-xs mt-2">{error}</p>
        </div>
      )}

      {!error && (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
        {sectors.map((s: any) => {
          const pct = s.avg_change ?? s.change_pct ?? 0
          const positive = pct >= 0
          return (
            <div key={s.name ?? s.sector} className={`rounded-xl p-4 border ${heatColor(pct)} transition-all hover:scale-[1.02]`}>
              <h3 className="font-bold text-sm truncate">{s.name ?? s.sector}</h3>
              <p className={`text-3xl font-bold font-mono mt-2 ${positive ? 'text-green-400' : 'text-red-400'}`}>
                {positive ? '+' : ''}{pct.toFixed(2)}%
              </p>
              <p className="text-xs opacity-60 mt-2">
                {s.stocks_sampled ?? s.count ?? 0} stocks sampled
              </p>
            </div>
          )
        })}
        </div>
      )}

      {!error && sectors.length === 0 && (
        <p className="text-center text-slate-500 py-8">No sector data available</p>
      )}

      {/* Legend */}
      <div className="flex items-center justify-center gap-2 text-xs text-slate-500">
        <span className="w-4 h-4 rounded bg-red-900" /> -3%+
        <span className="w-4 h-4 rounded bg-red-800/60" /> -1%
        <span className="w-4 h-4 rounded bg-yellow-900/40" /> 0%
        <span className="w-4 h-4 rounded bg-green-900/30" /> +1%
        <span className="w-4 h-4 rounded bg-green-800/60" /> +3%
        <span className="w-4 h-4 rounded bg-green-700" /> +3%+
      </div>
      <p className="text-xs text-slate-600 text-center">Auto-refreshes every 60s</p>
    </div>
  )
}
