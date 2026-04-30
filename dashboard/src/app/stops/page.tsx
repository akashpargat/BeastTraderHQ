'use client'
import { useEffect, useState, useCallback } from 'react'

const API = 'https://api.beast-trader.com'

function gapColor(gap: number): string {
  if (gap >= 5) return 'text-green-400'
  if (gap >= 3) return 'text-yellow-400'
  return 'text-red-400'
}

function gapBg(gap: number): string {
  if (gap >= 5) return 'bg-green-500'
  if (gap >= 3) return 'bg-yellow-500'
  return 'bg-red-500'
}

export default function StopsPage() {
  const [stops, setStops] = useState<any[]>([])
  const [loading, setLoading] = useState(true)

  const fetchData = useCallback(() => {
    fetch(`${API}/api/trailing-stops`)
      .then(r => r.json())
      .then(data => {
        setStops(Array.isArray(data) ? data : data.stops || [])
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [])

  useEffect(() => {
    fetchData()
    const interval = setInterval(fetchData, 30000)
    return () => clearInterval(interval)
  }, [fetchData])

  if (loading) return (
    <div className="space-y-4">
      <div className="h-8 bg-slate-800 rounded animate-pulse w-48" />
      {[...Array(4)].map((_, i) => <div key={i} className="h-28 bg-slate-800 rounded-xl animate-pulse" />)}
    </div>
  )

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">🛡️ Trailing Stops</h1>

      <div className="space-y-3">
        {stops.map((s: any) => {
          const entry = s.entry ?? s.avg_entry ?? 0
          const current = s.current_price ?? s.price ?? 0
          const hwm = s.hwm ?? s.high_water_mark ?? current
          const stop = s.stop_price ?? s.stop ?? 0
          const gap = s.gap_to_stop ?? (current > 0 && stop > 0 ? ((current - stop) / current * 100) : 0)
          const trail = s.trail_percent ?? s.trail_pct ?? 0

          // Bar positions as % of range (stop → hwm)
          const range = hwm - stop || 1
          const entryPct = Math.max(0, Math.min(100, ((entry - stop) / range) * 100))
          const currentPct = Math.max(0, Math.min(100, ((current - stop) / range) * 100))

          return (
            <div key={s.symbol} className="bg-slate-800 rounded-xl p-4 border border-slate-700">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-3">
                  <span className="font-mono font-bold text-white text-lg">{s.symbol}</span>
                  <span className="text-xs text-slate-400">{s.qty ?? 0} shares</span>
                </div>
                <div className="flex items-center gap-4 text-xs">
                  <span className="text-slate-400">Trail: {trail.toFixed(1)}%</span>
                  <span className={`font-bold ${gapColor(gap)}`}>Gap: {gap.toFixed(1)}%</span>
                </div>
              </div>

              {/* Visual bar */}
              <div className="relative h-8 bg-slate-700 rounded-full overflow-hidden">
                {/* Stop level marker */}
                <div className="absolute left-0 top-0 h-full w-1 bg-red-500 z-10" title={`Stop $${stop.toFixed(2)}`} />
                {/* Entry marker */}
                <div className="absolute top-0 h-full w-0.5 bg-blue-400 z-10" style={{ left: `${entryPct}%` }} title={`Entry $${entry.toFixed(2)}`} />
                {/* Current price fill */}
                <div className={`h-full rounded-full transition-all ${gapBg(gap)}`} style={{ width: `${currentPct}%`, opacity: 0.6 }} />
                {/* HWM marker */}
                <div className="absolute right-0 top-0 h-full w-1 bg-white/40 z-10" title={`HWM $${hwm.toFixed(2)}`} />
              </div>

              {/* Gap to stop visual bar */}
              <div className="mt-3">
                <div className="flex justify-between text-xs mb-1">
                  <span className="text-slate-400">Gap to Stop</span>
                  <span className={`font-bold ${gapColor(gap)}`}>{gap.toFixed(1)}%</span>
                </div>
                <div className="w-full bg-slate-700 rounded-full h-2">
                  <div className={`h-2 rounded-full transition-all ${gapBg(gap)}`}
                    style={{ width: `${Math.min(100, gap * 10)}%` }} />
                </div>
                <div className="flex justify-between text-[10px] mt-0.5">
                  <span className="text-red-400">Danger &lt;3%</span>
                  <span className="text-yellow-400">Caution 3-5%</span>
                  <span className="text-green-400">Safe &gt;5%</span>
                </div>
              </div>
            </div>
          )
        })}
      </div>

      {stops.length === 0 && (
        <p className="text-center text-slate-500 py-8">No active trailing stops</p>
      )}
      <p className="text-xs text-slate-600 text-center">Auto-refreshes every 30s</p>
    </div>
  )
}
