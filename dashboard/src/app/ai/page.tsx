'use client'
import { useEffect, useState, useCallback } from 'react'

const API = 'https://api.beast-trader.com'

function verdictStyle(v: string): { bg: string; text: string } {
  const verdict = (v || '').toUpperCase()
  if (verdict.includes('BUY')) return { bg: 'bg-green-500/20 border-green-500/40', text: 'text-green-400' }
  if (verdict.includes('SELL')) return { bg: 'bg-red-500/20 border-red-500/40', text: 'text-red-400' }
  return { bg: 'bg-yellow-500/10 border-yellow-500/30', text: 'text-yellow-400' }
}

export default function AIPage() {
  const [positions, setPositions] = useState<any[]>([])
  const [loading, setLoading] = useState(true)

  const fetchData = useCallback(() => {
    fetch(`${API}/api/portfolio`)
      .then(r => r.json())
      .then(data => {
        setPositions(data.positions || [])
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [])

  useEffect(() => {
    fetchData()
    const interval = setInterval(fetchData, 60000)
    return () => clearInterval(interval)
  }, [fetchData])

  if (loading) return (
    <div className="space-y-4">
      <div className="h-8 bg-slate-800 rounded animate-pulse w-48" />
      {[...Array(4)].map((_, i) => <div key={i} className="h-36 bg-slate-800 rounded-xl animate-pulse" />)}
    </div>
  )

  const withAI = positions.filter((p: any) => p.ai_verdict || p.ai_action || p.ai_recommendation)

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">🧠 AI Panel</h1>
        <span className="text-xs text-slate-500">{withAI.length} positions analyzed</span>
      </div>

      {withAI.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {withAI.map((p: any) => {
            const verdict = p.ai_verdict || p.ai_action || p.ai_recommendation || 'HOLD'
            const confidence = p.ai_confidence ?? p.confidence ?? 50
            const reasoning = p.ai_reasoning || p.ai_reason || p.reason || 'No reasoning provided'
            const style = verdictStyle(verdict)

            return (
              <div key={p.symbol} className={`bg-slate-800 rounded-xl p-4 border ${style.bg}`}>
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-3">
                    <span className="font-mono font-bold text-white text-lg">{p.symbol}</span>
                    <span className="text-xs text-slate-400">${(p.current_price ?? 0).toFixed(2)}</span>
                  </div>
                  <span className={`text-sm font-bold px-3 py-1 rounded-full ${style.text} bg-slate-900/50`}>
                    {verdict.toUpperCase()}
                  </span>
                </div>

                {/* Confidence bar */}
                <div className="mb-3">
                  <div className="flex justify-between text-xs mb-1">
                    <span className="text-slate-400">Confidence</span>
                    <span className={style.text}>{confidence}%</span>
                  </div>
                  <div className="w-full bg-slate-700 rounded-full h-2">
                    <div
                      className={`h-2 rounded-full transition-all ${
                        confidence >= 70 ? 'bg-green-500' : confidence >= 40 ? 'bg-yellow-500' : 'bg-red-500'
                      }`}
                      style={{ width: `${confidence}%` }}
                    />
                  </div>
                </div>

                {/* Reasoning */}
                <p className="text-xs text-slate-400 leading-relaxed">{reasoning}</p>

                {/* Position info */}
                <div className="flex gap-4 mt-3 text-xs text-slate-500">
                  <span>{p.qty} shares</span>
                  <span className={p.unrealized_pl >= 0 ? 'text-green-400' : 'text-red-400'}>
                    P&L: ${(p.unrealized_pl ?? 0).toFixed(2)}
                  </span>
                </div>
              </div>
            )
          })}
        </div>
      ) : (
        <div className="bg-slate-800 rounded-xl p-8 border border-slate-700 text-center">
          <p className="text-slate-400">No AI verdicts available</p>
          <p className="text-xs text-slate-500 mt-1">AI analysis runs on active positions</p>
        </div>
      )}
      <p className="text-xs text-slate-600 text-center">Auto-refreshes every 60s</p>
    </div>
  )
}
