'use client'
import { useEffect, useState, useCallback } from 'react'
import { authFetch } from '../../lib/api'

export default function DecisionsPage() {
  const [decisions, setDecisions] = useState<any[]>([])
  const [accuracy, setAccuracy] = useState<any>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState('all')

  const fetchData = useCallback(async () => {
    try {
      const actionParam = filter !== 'all' ? `&action=${filter}` : ''
      const [dRes, aRes] = await Promise.all([
        authFetch(`/api/v4/decisions?limit=50${actionParam}`).catch(() => null),
        authFetch('/api/v4/decision-accuracy?days=7').catch(() => null),
      ])
      if (dRes?.ok) setDecisions(await dRes.json())
      if (aRes?.ok) setAccuracy(await aRes.json())
      setError('')
    } catch (e: any) { setError(e.message) }
    setLoading(false)
  }, [filter])

  useEffect(() => { fetchData(); const i = setInterval(fetchData, 15000); return () => clearInterval(i) }, [fetchData])

  if (loading) return <div className="flex items-center justify-center min-h-[50vh]"><div className="text-4xl animate-bounce">🦍</div></div>

  const actionColor: Record<string, string> = {
    BUY: 'bg-[#00ff88]/20 text-[#00ff88]',
    SELL: 'bg-[#ff4444]/20 text-[#ff4444]',
    BLOCK: 'bg-red-900/30 text-red-400',
    SKIP: 'bg-yellow-900/30 text-yellow-400',
    HOLD: 'bg-gray-500/20 text-gray-400',
  }

  return (
    <div className="fade-in space-y-6">
      <h1 className="text-2xl font-bold">🎯 Trade Decisions ({decisions.length})</h1>
      {error && <div className="glass p-3 text-red-400 text-sm">{error}</div>}

      {/* Accuracy cards */}
      {accuracy && Object.keys(accuracy).length > 0 && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {Object.entries(accuracy).map(([action, stats]: [string, any]) => {
            const pct = stats.total > 0 ? (stats.correct / stats.total * 100) : 0
            const color = pct >= 70 ? 'text-[#00ff88]' : pct >= 50 ? 'text-yellow-400' : 'text-[#ff4444]'
            return (
              <div key={action} className="glass p-3 text-center">
                <div className="text-xs text-gray-400">{action} accuracy</div>
                <div className={`text-2xl font-bold ${color}`}>{pct.toFixed(0)}%</div>
                <div className="text-xs text-gray-500">{stats.correct}/{stats.total}</div>
              </div>
            )
          })}
        </div>
      )}

      {/* Filters */}
      <div className="flex gap-2">
        {['all', 'BUY', 'BLOCK', 'SKIP'].map(f => (
          <button key={f} onClick={() => setFilter(f)}
            className={`px-3 py-1 rounded text-sm ${filter === f ? 'bg-white/20 text-white' : 'bg-white/5 text-gray-400'}`}>
            {f}
          </button>
        ))}
      </div>

      {/* Decision list */}
      {decisions.length === 0 ? (
        <div className="glass p-12 text-center text-gray-500"><div className="text-4xl mb-2">📭</div>No decisions</div>
      ) : (
        <div className="space-y-2">
          {decisions.map((d: any, i: number) => {
            const pipeline = d?.signals?.pipeline || []
            const correct = d?.was_correct
            return (
              <div key={i} className={`glass p-4 ${correct === true ? 'border-l-4 border-l-[#00ff88]' : correct === false ? 'border-l-4 border-l-[#ff4444]' : ''}`}>
                <div className="flex items-center justify-between mb-1">
                  <div className="flex items-center gap-2">
                    <span className="font-mono font-bold">{d?.symbol ?? '—'}</span>
                    <span className={`px-2 py-0.5 rounded text-xs font-bold ${actionColor[d?.action] || actionColor.HOLD}`}>
                      {d?.action ?? '—'}
                    </span>
                    {d?.confidence > 0 && <span className="text-xs text-gray-400">{d.confidence}%</span>}
                    {d?.executed && <span className="text-xs bg-green-900/30 text-green-400 px-1 rounded">executed</span>}
                    {correct === true && <span className="text-xs text-[#00ff88]">✓ correct</span>}
                    {correct === false && <span className="text-xs text-[#ff4444]">✗ wrong</span>}
                  </div>
                  <span className="text-xs text-gray-500">{d?.created_at ? new Date(d.created_at).toLocaleTimeString() : ''}</span>
                </div>
                {d?.block_reason && <div className="text-sm text-red-400">{d.block_reason}</div>}
                {d?.strategy && <div className="text-xs text-gray-500">Strategy: {d.strategy}</div>}
                {pipeline.length > 0 && (
                  <div className="text-xs text-gray-600 font-mono mt-1">{pipeline.join(' → ')}</div>
                )}
                {d?.price_at_decision && d?.price_after_1h && (
                  <div className="text-xs text-gray-500 mt-1">
                    Price: ${Number(d.price_at_decision).toFixed(2)} → ${Number(d.price_after_1h).toFixed(2)}
                    ({((d.price_after_1h - d.price_at_decision) / d.price_at_decision * 100).toFixed(1)}%)
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
