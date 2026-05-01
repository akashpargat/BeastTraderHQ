'use client'
import { useEffect, useState, useCallback } from 'react'
import { authFetch } from '@/lib/api'

function fgColor(value: number) {
  if (value <= 25) return 'text-red-400'
  if (value <= 45) return 'text-orange-400'
  if (value <= 55) return 'text-yellow-400'
  if (value <= 75) return 'text-green-300'
  return 'text-green-400'
}

function fgLabel(value: number) {
  if (value <= 25) return 'Extreme Fear'
  if (value <= 45) return 'Fear'
  if (value <= 55) return 'Neutral'
  if (value <= 75) return 'Greed'
  return 'Extreme Greed'
}

export default function MarketPage() {
  const [market, setMarket] = useState<any>(null)
  const [calendar, setCalendar] = useState<any>(null)
  const [squeeze, setSqueeze] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const fetchData = useCallback(async () => {
    try {
      const [mRes, cRes, sRes] = await Promise.all([
        authFetch('/api/v5/market-conditions').catch(() => null),
        authFetch('/api/v5/economic-calendar').catch(() => null),
        authFetch('/api/v5/short-squeeze').catch(() => null),
      ])
      if (mRes?.ok) setMarket(await mRes.json())
      if (cRes?.ok) setCalendar(await cRes.json())
      if (sRes?.ok) setSqueeze(await sRes.json())
      setError('')
    } catch (e: any) {
      setError(e.message || 'Failed to load market data')
    }
    setLoading(false)
  }, [])

  useEffect(() => {
    fetchData()
    const i = setInterval(fetchData, 120000) // 2 minutes
    return () => clearInterval(i)
  }, [fetchData])

  if (loading) return <div className="flex items-center justify-center min-h-[50vh]"><div className="text-4xl animate-bounce">🌍</div></div>
  if (error && !market) return <div className="bg-gray-800 rounded-lg p-6 text-center text-red-400">{error}</div>

  const vixData = market?.vix_structure || market?.vix || {}
  const vix = Number(typeof vixData === 'object' ? (vixData.vix ?? 0) : (vixData ?? 0)) || 0
  const vix3m = Number(typeof vixData === 'object' ? (vixData.vix3m ?? 0) : (market?.vix3m ?? 0)) || 0
  const contango = vix3m > 0 ? vix3m > vix : (typeof vixData === 'object' ? !vixData.is_inverted : false)
  const fgData = market?.fear_greed || {}
  const fg = Number(typeof fgData === 'object' ? (fgData.value ?? 50) : (fgData ?? 50)) || 50
  const fgHistory = (typeof fgData === 'object' ? fgData.history : market?.fear_greed_history) ?? []
  const pcrData = market?.pcr || market?.put_call_ratio || {}
  const pcr = Number(typeof pcrData === 'object' ? (pcrData.value ?? 0) : (pcrData ?? 0)) || 0
  const events = calendar?.events ?? calendar?.upcoming ?? []
  const squeezeList = (squeeze?.squeeze_candidates ?? squeeze?.stocks ?? squeeze?.candidates ?? [])
    .filter((s: any) => {
      const ratio = Number(s.short_ratio ?? s.short_pct ?? 0)
      return ratio >= 0.30 || ratio >= 30  // Handle both 0.44 and 44% formats
    })
    .sort((a: any, b: any) => Number(b.short_ratio ?? b.short_pct ?? 0) - Number(a.short_ratio ?? a.short_pct ?? 0))

  return (
    <div className="space-y-6 fade-in">
      <h1 className="text-2xl font-bold text-white">🌍 Market Conditions</h1>

      {/* Top Row: VIX + Fear&Greed + PCR */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* VIX Term Structure */}
        <div className="bg-gray-800 rounded-lg p-4 shadow-lg">
          <h3 className="text-sm text-gray-400 mb-3">VIX Term Structure</h3>
          <div className="flex items-end gap-6 justify-center">
            <div className="text-center">
              <div className="text-3xl font-bold text-white">{Number(vix).toFixed(1)}</div>
              <div className="text-xs text-gray-400 mt-1">VIX (spot)</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-semibold text-gray-300">{vix3m > 0 ? vix3m.toFixed(1) : '—'}</div>
              <div className="text-xs text-gray-400 mt-1">VIX3M</div>
            </div>
          </div>
          {vix3m > 0 && (
            <div className={`text-center mt-3 px-3 py-1 rounded-full text-sm font-medium ${
              contango ? 'bg-green-900/40 text-green-400' : 'bg-red-900/40 text-red-400'
            }`}>
              {contango ? '📈 Contango (Normal)' : '📉 Backwardation (Stress)'}
            </div>
          )}
        </div>

        {/* Fear & Greed */}
        <div className="bg-gray-800 rounded-lg p-4 shadow-lg text-center">
          <h3 className="text-sm text-gray-400 mb-2">Fear & Greed Index</h3>
          <div className={`text-5xl font-bold ${fgColor(fg)}`}>{fg}</div>
          <div className={`text-lg mt-1 ${fgColor(fg)}`}>{fgLabel(fg)}</div>
          {fgHistory.length > 0 && (
            <div className="flex justify-center gap-1 mt-3">
              {fgHistory.slice(-7).map((v: number, i: number) => (
                <div key={i} className="flex flex-col items-center">
                  <div className={`w-6 rounded-sm ${fgColor(v)}`}
                    style={{ height: `${Math.max(v / 2, 4)}px`, backgroundColor: v <= 25 ? '#f87171' : v <= 45 ? '#fb923c' : v <= 55 ? '#facc15' : v <= 75 ? '#86efac' : '#4ade80' }}
                  />
                  <span className="text-[10px] text-gray-500 mt-0.5">{v}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Put/Call Ratio */}
        <div className="bg-gray-800 rounded-lg p-4 shadow-lg text-center">
          <h3 className="text-sm text-gray-400 mb-2">Put/Call Ratio</h3>
          <div className="text-4xl font-bold text-white">{Number(pcr).toFixed(2)}</div>
          <div className={`text-sm mt-2 px-3 py-1 rounded-full inline-block ${
            pcr > 1.0 ? 'bg-red-900/40 text-red-400' : pcr > 0.7 ? 'bg-yellow-900/40 text-yellow-400' : 'bg-green-900/40 text-green-400'
          }`}>
            {pcr > 1.0 ? '🐻 Bearish Signal' : pcr > 0.7 ? '⚖️ Neutral' : '🐂 Bullish Signal'}
          </div>
        </div>
      </div>

      {/* Economic Calendar */}
      <div className="bg-gray-800 rounded-lg p-4 shadow-lg">
        <h2 className="text-lg font-semibold text-white mb-3">📅 Economic Calendar</h2>
        {events.length === 0 ? (
          <div className="text-gray-500 text-center py-4">No upcoming events</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-gray-400 border-b border-white/10">
                  <th className="text-left py-2 px-3">Date</th>
                  <th className="text-left py-2 px-3">Time</th>
                  <th className="text-left py-2 px-3">Event</th>
                  <th className="text-center py-2 px-3">Impact</th>
                  <th className="text-right py-2 px-3">Forecast</th>
                  <th className="text-right py-2 px-3">Previous</th>
                </tr>
              </thead>
              <tbody>
                {events.slice(0, 20).map((e: any, i: number) => {
                  const impact = (e.impact ?? e.importance ?? '').toLowerCase()
                  const isHigh = impact === 'high' || impact === '3' || impact === 'red'
                  return (
                    <tr key={i} className={`border-b border-white/5 hover:bg-white/5 ${isHigh ? 'bg-red-900/10' : ''}`}>
                      <td className="py-2 px-3 text-gray-400">{e.date ? new Date(e.date).toLocaleDateString() : '—'}</td>
                      <td className="py-2 px-3 text-gray-400">{e.time ?? '—'}</td>
                      <td className={`py-2 px-3 ${isHigh ? 'text-red-300 font-semibold' : 'text-white'}`}>
                        {e.event ?? e.name ?? e.title ?? '—'}
                      </td>
                      <td className="py-2 px-3 text-center">
                        <span className={`px-2 py-0.5 rounded-full text-xs ${
                          isHigh ? 'bg-red-900/50 text-red-400' : 'bg-gray-700 text-gray-400'
                        }`}>
                          {isHigh ? '🔴 HIGH' : impact || 'Low'}
                        </span>
                      </td>
                      <td className="py-2 px-3 text-right text-gray-300">{e.forecast ?? '—'}</td>
                      <td className="py-2 px-3 text-right text-gray-400">{e.previous ?? e.actual ?? '—'}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Short Squeeze Radar */}
      <div className="bg-gray-800 rounded-lg p-4 shadow-lg">
        <h2 className="text-lg font-semibold text-white mb-3">🎯 Short Squeeze Radar ({'>'}30% Short Interest)</h2>
        {squeezeList.length === 0 ? (
          <div className="text-gray-500 text-center py-4">No stocks above 30% short ratio</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-gray-400 border-b border-white/10">
                  <th className="text-left py-2 px-3">Symbol</th>
                  <th className="text-right py-2 px-3">Short %</th>
                  <th className="text-right py-2 px-3">Days to Cover</th>
                  <th className="text-right py-2 px-3">Float</th>
                  <th className="text-right py-2 px-3">Price</th>
                  <th className="text-right py-2 px-3">Change</th>
                </tr>
              </thead>
              <tbody>
                {squeezeList.slice(0, 15).map((s: any, i: number) => {
                  const ratio = s.short_ratio ?? s.short_pct ?? 0
                  const change = s.change_pct ?? s.change ?? 0
                  return (
                    <tr key={i} className="border-b border-white/5 hover:bg-white/5">
                      <td className="py-2 px-3 font-mono font-semibold text-white">{s.symbol ?? '—'}</td>
                      <td className="py-2 px-3 text-right">
                        <span className={`font-semibold ${ratio >= 50 ? 'text-red-400' : ratio >= 40 ? 'text-orange-400' : 'text-yellow-400'}`}>
                          {Number(ratio).toFixed(1)}%
                        </span>
                      </td>
                      <td className="py-2 px-3 text-right text-gray-300">{s.days_to_cover?.toFixed(1) ?? '—'}</td>
                      <td className="py-2 px-3 text-right text-gray-400">{s.float ? `${(s.float / 1e6).toFixed(1)}M` : '—'}</td>
                      <td className="py-2 px-3 text-right text-white">${Number(s.price ?? 0).toFixed(2)}</td>
                      <td className={`py-2 px-3 text-right ${change >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                        {change >= 0 ? '+' : ''}{Number(change).toFixed(1)}%
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}

