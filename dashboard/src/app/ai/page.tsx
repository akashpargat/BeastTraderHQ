'use client'
import { useEffect, useState, useCallback } from 'react'

const API = 'https://api.beast-trader.com'

function actionMeta(action: string) {
  const a = (action || '').toUpperCase()
  if (a === 'BUY') return { label: 'BUY', bg: 'bg-[#00ff88]/15', text: 'text-[#00ff88]', glow: 'shadow-[0_0_20px_rgba(0,255,136,0.4)]', barFrom: '#ff4444', barTo: '#00ff88' }
  if (a === 'SELL') return { label: 'SELL', bg: 'bg-red-500/15', text: 'text-red-400', glow: 'shadow-[0_0_20px_rgba(255,68,68,0.4)]', barFrom: '#ff4444', barTo: '#00ff88' }
  return { label: 'HOLD', bg: 'bg-slate-500/15', text: 'text-slate-400', glow: '', barFrom: '#ff4444', barTo: '#00ff88' }
}

function confidenceColor(pct: number): string {
  if (pct >= 70) return '#00ff88'
  if (pct >= 40) return '#facc15'
  return '#ff4444'
}

export default function AIPage() {
  const [verdicts, setVerdicts] = useState<any[]>([])
  const [loading, setLoading] = useState(true)

  const fetchData = useCallback(() => {
    fetch(`${API}/api/ai-verdicts`)
      .then(r => r.json())
      .then(data => { setVerdicts(data.verdicts || []); setLoading(false) })
      .catch(() => setLoading(false))
  }, [])

  useEffect(() => {
    fetchData()
    const interval = setInterval(fetchData, 10000)
    return () => clearInterval(interval)
  }, [fetchData])

  // Sort by confidence descending
  const sorted = [...verdicts].sort((a, b) => (b.ai_confidence ?? 0) - (a.ai_confidence ?? 0))
  const allNoData = verdicts.length > 0 && verdicts.every((v: any) => (v.ai_action || '').toUpperCase() === 'NO DATA')

  if (loading) return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="flex flex-col items-center gap-4">
        <div className="w-12 h-12 border-2 border-purple-500/30 border-t-purple-500 rounded-full animate-spin" />
        <p className="text-slate-500 text-sm">Loading AI verdicts...</p>
      </div>
    </div>
  )

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">🧠 AI Analysis Panel</h1>
          <p className="text-slate-500 text-sm mt-1">{verdicts.length} positions analyzed · Sorted by confidence · Auto-refresh 10s</p>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="w-2 h-2 rounded-full bg-purple-500 live-dot" />
          <span className="text-xs text-purple-400/70">AI ACTIVE</span>
        </div>
      </div>

      {allNoData && (
        <div className="glass-card p-8 text-center">
          <div className="text-5xl mb-3">🧠</div>
          <p className="text-slate-300 text-lg">AI Scanning Paused</p>
          <p className="text-slate-500">Scans resume at 4:00 AM ET pre-market</p>
          <p className="text-slate-600 text-sm mt-2">Last scan data will appear here when available</p>
        </div>
      )}

      {sorted.length > 0 ? (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5 stagger-enter">
          {sorted.map((v: any) => {
            const meta = actionMeta(v.ai_action)
            const confidence = v.ai_confidence ?? 50
            const confColor = confidenceColor(confidence)
            const pnl = v.pnl ?? 0
            const isGreen = pnl >= 0
            const source = (v.ai_source || 'Unknown').toLowerCase()
            const isGpt = source.includes('gpt')

            return (
              <div key={v.symbol} className={`glass-card hover-scale-glow p-6 relative overflow-hidden`}>
                {/* Top glow line */}
                <div className="absolute top-0 left-0 w-full h-0.5" style={{ background: confColor }} />

                {/* Header: Symbol + Action Badge */}
                <div className="flex items-start justify-between mb-5">
                  <div className="flex items-center gap-3">
                    <div className={`w-11 h-11 rounded-full flex items-center justify-center text-sm font-bold ${isGreen ? 'bg-[#00ff88]/15 text-[#00ff88]' : 'bg-red-500/15 text-red-400'}`}>
                      {(v.symbol || '??').slice(0, 2)}
                    </div>
                    <div>
                      <h3 className="text-xl font-bold font-mono">{v.symbol}</h3>
                      <p className="text-xs text-slate-500">${(v.price ?? 0).toFixed(2)}</p>
                    </div>
                  </div>
                  <span className={`px-4 py-1.5 rounded-full text-sm font-bold ${meta.bg} ${meta.text} ${meta.glow}`}>
                    {meta.label}
                  </span>
                </div>

                {/* Confidence Bar */}
                <div className="mb-5">
                  <div className="flex justify-between text-xs mb-2">
                    <span className="text-slate-500 uppercase tracking-wider text-[10px]">Confidence</span>
                    <span className="font-bold font-mono" style={{ color: confColor }}>{confidence}%</span>
                  </div>
                  <div className="w-full bg-white/[0.04] rounded-full h-3 overflow-hidden">
                    <div className="h-full rounded-full confidence-bar-fill"
                      style={{
                        width: `${confidence}%`,
                        background: `linear-gradient(90deg, #ff4444 0%, #facc15 50%, #00ff88 100%)`,
                      }} />
                  </div>
                </div>

                {/* Source + Scan Badges */}
                <div className="flex gap-2 mb-4">
                  <span className={`text-[10px] px-2.5 py-1 rounded-full font-medium ${isGpt ? 'bg-cyan-500/15 text-cyan-400 border border-cyan-500/30' : 'bg-purple-500/15 text-purple-400 border border-purple-500/30'}`}>
                    {isGpt ? '🤖 GPT-4o' : '🧠 Claude Opus'}
                  </span>
                  <span className="text-[10px] px-2.5 py-1 rounded-full bg-white/[0.04] text-slate-400 border border-white/[0.06]">
                    ⏱ {v.scan_type || '5min'}
                  </span>
                </div>

                {/* Reasoning Quote */}
                <div className="border-l-2 border-white/10 pl-4 mb-4">
                  <p className="text-sm text-slate-300 italic leading-relaxed">
                    &ldquo;{v.ai_reasoning || 'No reasoning provided'}&rdquo;
                  </p>
                </div>

                {/* P&L Context */}
                <div className="flex items-center gap-3 text-xs">
                  <span className={`font-mono font-bold ${isGreen ? 'text-[#00ff88]' : 'text-red-400'}`}>
                    {isGreen ? '+' : ''}${pnl.toFixed(2)}
                  </span>
                  <span className={`font-mono ${isGreen ? 'text-[#00ff88]/60' : 'text-red-400/60'}`}>
                    ({(v.pct ?? 0).toFixed(1)}%)
                  </span>
                </div>
              </div>
            )
          })}
        </div>
      ) : (
        <div className="glass-card p-12 text-center">
          <p className="text-slate-400 text-lg">No AI verdicts available</p>
          <p className="text-slate-600 text-sm mt-1">AI analysis runs on active positions every scan cycle</p>
        </div>
      )}
    </div>
  )
}
