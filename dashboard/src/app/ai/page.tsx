'use client'
import { useEffect, useState, useCallback } from 'react'

const API = 'https://api.beast-trader.com'

function actionStyle(action: string) {
  const a = (action || '').toUpperCase()
  if (a === 'BUY') return { bg: 'bg-green-500/20 border-green-500/40', text: 'text-green-400', bar: 'bg-green-500' }
  if (a === 'SELL') return { bg: 'bg-red-500/20 border-red-500/40', text: 'text-red-400', bar: 'bg-red-500' }
  return { bg: 'bg-yellow-500/10 border-yellow-500/30', text: 'text-yellow-400', bar: 'bg-yellow-500' }
}

export default function AIPage() {
  const [verdicts, setVerdicts] = useState<any[]>([])
  const [loading, setLoading] = useState(true)

  const fetchData = useCallback(() => {
    fetch(`${API}/api/ai-verdicts`)
      .then(r => r.json())
      .then(data => {
        setVerdicts(data.verdicts || [])
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

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">🧠 AI Panel</h1>
        <span className="text-xs text-slate-500">{verdicts.length} positions analyzed</span>
      </div>

      {verdicts.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {verdicts.map((v: any) => {
            const style = actionStyle(v.ai_action)
            const confidence = v.ai_confidence ?? 50

            return (
              <div key={v.symbol} className={`bg-slate-800 rounded-xl p-4 border ${style.bg}`}>
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-3">
                    <span className="font-mono font-bold text-white text-lg">{v.symbol}</span>
                    <span className="text-xs text-slate-400">${(v.price ?? 0).toFixed(2)}</span>
                    <span className={`text-xs font-mono ${(v.pnl ?? 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                      {(v.pnl ?? 0) >= 0 ? '+' : ''}${(v.pnl ?? 0).toFixed(2)} ({(v.pct ?? 0).toFixed(1)}%)
                    </span>
                  </div>
                  <span className={`text-sm font-bold px-3 py-1 rounded-full ${style.text} bg-slate-900/50`}>
                    {(v.ai_action || 'HOLD').toUpperCase()}
                  </span>
                </div>

                {/* Confidence bar */}
                <div className="mb-3">
                  <div className="flex justify-between text-xs mb-1">
                    <span className="text-slate-400">Confidence</span>
                    <span className={style.text}>{confidence}%</span>
                  </div>
                  <div className="w-full bg-slate-700 rounded-full h-2">
                    <div className={`h-2 rounded-full transition-all ${style.bar}`}
                      style={{ width: `${confidence}%` }} />
                  </div>
                </div>

                {/* Reasoning */}
                <p className="text-xs text-slate-400 leading-relaxed">{v.ai_reasoning || 'No reasoning provided'}</p>

                {/* Source info */}
                <div className="flex gap-4 mt-3 text-xs text-slate-500">
                  <span className="bg-slate-700/60 px-2 py-0.5 rounded">🤖 {v.ai_source || 'Unknown'}</span>
                  <span className="bg-slate-700/60 px-2 py-0.5 rounded">⏱ {v.scan_type || 'N/A'}</span>
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
