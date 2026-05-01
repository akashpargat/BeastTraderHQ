'use client'
import { useEffect, useState, useCallback } from 'react'
import { authFetch } from '@/lib/api'

function scoreColor(score: number) {
  if (score >= 15) return 'text-green-400'
  if (score >= 5) return 'text-green-300'
  if (score >= -4) return 'text-gray-400'
  if (score >= -14) return 'text-orange-400'
  return 'text-red-400'
}

function scoreBg(score: number) {
  if (score >= 15) return 'border-green-400'
  if (score >= 5) return 'border-green-600'
  if (score >= -4) return 'border-gray-600'
  if (score >= -14) return 'border-orange-500'
  return 'border-red-500'
}

function fgColor(value: number) {
  if (value <= 25) return 'text-red-400'
  if (value <= 45) return 'text-orange-400'
  if (value <= 55) return 'text-yellow-400'
  if (value <= 75) return 'text-green-300'
  return 'text-green-400'
}

function vixStatus(vix: number) {
  if (vix < 15) return { label: 'Low', color: 'text-green-400 bg-green-900/40' }
  if (vix < 25) return { label: 'Elevated', color: 'text-yellow-400 bg-yellow-900/40' }
  return { label: 'High', color: 'text-red-400 bg-red-900/40' }
}

export default function ProIntelPage() {
  const [market, setMarket] = useState<any>(null)
  const [portfolio, setPortfolio] = useState<any>(null)
  const [intelMap, setIntelMap] = useState<Record<string, any>>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const fetchData = useCallback(async () => {
    try {
      const [mRes, pRes] = await Promise.all([
        authFetch('/api/v5/market-conditions').catch(() => null),
        authFetch('/api/portfolio').catch(() => null),
      ])
      const mData = mRes?.ok ? await mRes.json() : null
      const pData = pRes?.ok ? await pRes.json() : null
      if (mData) setMarket(mData)
      if (pData) setPortfolio(pData)

      const positions = pData?.positions || []
      const intelResults: Record<string, any> = {}
      await Promise.all(
        positions.map(async (p: any) => {
          try {
            const r = await authFetch(`/api/v5/pro-intel/${p.symbol}`)
            if (r?.ok) intelResults[p.symbol] = await r.json()
          } catch {}
        })
      )
      setIntelMap(intelResults)
      setError('')
    } catch (e: any) {
      setError(e.message || 'Failed to load pro intel')
    }
    setLoading(false)
  }, [])

  useEffect(() => {
    fetchData()
    const i = setInterval(fetchData, 60000)
    return () => clearInterval(i)
  }, [fetchData])

  if (loading) return <div className="flex items-center justify-center min-h-[50vh]"><div className="text-4xl animate-bounce">🧠</div></div>
  if (error && !market) return <div className="bg-gray-800 rounded-lg p-6 text-center text-red-400">{error}</div>

  const positions = portfolio?.positions || []
  const fg = market?.fear_greed ?? market?.fear_and_greed ?? 50
  const vix = market?.vix ?? 0
  const pcr = market?.put_call_ratio ?? market?.pcr ?? 0
  const highImpact = market?.high_impact_tomorrow ?? false
  const vs = vixStatus(vix)

  return (
    <div className="space-y-6 fade-in">
      {/* High Impact Warning */}
      {highImpact && (
        <div className="bg-red-900/50 border border-red-500 rounded-lg p-4 text-center">
          <span className="text-red-300 font-semibold">⚠️ High-Impact Economic Event Tomorrow — Positions may see elevated volatility</span>
        </div>
      )}

      {/* Top Banner */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-gray-800 rounded-lg p-4 shadow-lg text-center">
          <div className="text-xs text-gray-400 mb-1">Fear & Greed Index</div>
          <div className={`text-4xl font-bold ${fgColor(fg)}`}>{fg}</div>
          <div className={`text-sm mt-1 ${fgColor(fg)}`}>
            {fg <= 25 ? 'Extreme Fear' : fg <= 45 ? 'Fear' : fg <= 55 ? 'Neutral' : fg <= 75 ? 'Greed' : 'Extreme Greed'}
          </div>
        </div>
        <div className="bg-gray-800 rounded-lg p-4 shadow-lg text-center">
          <div className="text-xs text-gray-400 mb-1">VIX</div>
          <div className="text-4xl font-bold text-white">{vix.toFixed(1)}</div>
          <span className={`text-sm px-2 py-0.5 rounded-full ${vs.color}`}>{vs.label}</span>
        </div>
        <div className="bg-gray-800 rounded-lg p-4 shadow-lg text-center">
          <div className="text-xs text-gray-400 mb-1">Put/Call Ratio</div>
          <div className="text-4xl font-bold text-white">{Number(pcr).toFixed(2)}</div>
          <div className={`text-sm mt-1 ${pcr > 1.0 ? 'text-red-400' : pcr > 0.7 ? 'text-yellow-400' : 'text-green-400'}`}>
            {pcr > 1.0 ? 'Bearish' : pcr > 0.7 ? 'Neutral' : 'Bullish'}
          </div>
        </div>
      </div>

      {/* Pro Intel Cards */}
      <h2 className="text-lg font-semibold text-white">🧠 Pro Intelligence — {positions.length} Positions</h2>
      {positions.length === 0 ? (
        <div className="bg-gray-800 rounded-lg p-8 text-center text-gray-500">No open positions to analyze</div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {positions.map((p: any) => {
            const intel = intelMap[p.symbol]
            const proScore = intel?.pro_score ?? intel?.score ?? 0
            return (
              <div key={p.symbol} className={`bg-gray-800 rounded-lg p-4 shadow-lg border-l-4 ${scoreBg(proScore)}`}>
                <div className="flex justify-between items-center mb-3">
                  <span className="text-lg font-mono font-bold text-white">{p.symbol}</span>
                  <span className={`text-2xl font-bold ${scoreColor(proScore)}`}>
                    {proScore > 0 ? '+' : ''}{proScore}
                  </span>
                </div>
                {intel ? (
                  <div className="space-y-2 text-sm">
                    <div className="flex justify-between">
                      <span className="text-gray-400">🏛️ Congress</span>
                      <span className={scoreColor(intel.congress_score ?? 0)}>{intel.congress_score ?? 0}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-400">👤 Insider</span>
                      <span className={scoreColor(intel.insider_score ?? 0)}>{intel.insider_score ?? 0}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-400">📉 Short Interest</span>
                      <span className={scoreColor(intel.short_interest_score ?? 0)}>{intel.short_interest_score ?? 0}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-400">🕳️ Dark Pool</span>
                      <span className={scoreColor(intel.dark_pool_score ?? 0)}>{intel.dark_pool_score ?? 0}</span>
                    </div>
                    {intel.signals && intel.signals.length > 0 && (
                      <div className="mt-2 pt-2 border-t border-gray-700">
                        {intel.signals.slice(0, 2).map((s: string, i: number) => (
                          <div key={i} className="text-xs text-gray-500">• {s}</div>
                        ))}
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="text-sm text-gray-500">Loading intel...</div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
