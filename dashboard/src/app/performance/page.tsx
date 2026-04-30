'use client'
import { useEffect, useState, useCallback } from 'react'
import { authFetch } from '../../lib/api'

export default function PerformancePage() {
  const [data, setData] = useState<any>(null)
  const [accuracy, setAccuracy] = useState<any>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  const fetchData = useCallback(async () => {
    try {
      const [pRes, aRes] = await Promise.all([
        authFetch('/api/v4/performance').catch(() => null),
        authFetch('/api/v4/decision-accuracy?days=7').catch(() => null),
      ])
      if (pRes?.ok) setData(await pRes.json())
      if (aRes?.ok) setAccuracy(await aRes.json())
      setError('')
    } catch (e: any) { setError(e.message) }
    setLoading(false)
  }, [])

  useEffect(() => { fetchData(); const i = setInterval(fetchData, 30000); return () => clearInterval(i) }, [fetchData])

  if (loading) return <div className="flex items-center justify-center min-h-[50vh]"><div className="text-4xl animate-bounce">🦍</div></div>

  const lastScan = data?.last_scan || {}
  const scans = data?.recent_scans || []

  return (
    <div className="fade-in space-y-6">
      <h1 className="text-2xl font-bold">⏱️ Performance</h1>
      {error && <div className="glass p-3 text-red-400 text-sm">{error}</div>}

      {/* Last Scan Timing */}
      <div className="glass p-4">
        <h2 className="text-lg font-semibold mb-3">🔬 Last Scan Breakdown</h2>
        {lastScan?.tv ? (
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
            {[
              { label: 'TV Indicators', ms: lastScan.tv?.total_ms, icon: '📺' },
              { label: 'Sentiment', ms: lastScan.sentiment?.total_ms, icon: '💬' },
              { label: 'Confidence', ms: lastScan.confidence?.total_ms, icon: '🎯' },
              { label: 'AI (GPT-4o)', ms: lastScan.ai?.total_ms, icon: '🧠' },
              { label: 'Learning', ms: lastScan.learning?.total_ms, icon: '📚' },
            ].map((s, i) => (
              <div key={i} className="glass p-3 text-center">
                <div className="text-2xl mb-1">{s.icon}</div>
                <div className="text-xs text-gray-400">{s.label}</div>
                <div className="text-xl font-bold font-mono">{s.ms ? `${(s.ms / 1000).toFixed(1)}s` : '—'}</div>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-gray-500 text-center py-4">Waiting for first scan...</div>
        )}
        {lastScan?.total_ms && (
          <div className="mt-3 text-center">
            <span className="text-gray-400">Total: </span>
            <span className="text-2xl font-bold font-mono">{(lastScan.total_ms / 1000).toFixed(1)}s</span>
            <span className="text-gray-400 ml-2">Avg: </span>
            <span className="font-mono">{data?.avg_scan_ms ? `${(data.avg_scan_ms / 1000).toFixed(1)}s` : '—'}</span>
          </div>
        )}
      </div>

      {/* Decision Accuracy */}
      <div className="glass p-4">
        <h2 className="text-lg font-semibold mb-3">🎯 Decision Accuracy (7 days)</h2>
        {accuracy && Object.keys(accuracy).length > 0 ? (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {Object.entries(accuracy).map(([action, stats]: [string, any]) => {
              const pct = stats.total > 0 ? (stats.correct / stats.total * 100) : 0
              const color = pct >= 70 ? 'text-[#00ff88]' : pct >= 50 ? 'text-yellow-400' : 'text-[#ff4444]'
              return (
                <div key={action} className="glass p-3 text-center">
                  <div className="text-xs text-gray-400 mb-1">{action}</div>
                  <div className={`text-2xl font-bold ${color}`}>{pct.toFixed(0)}%</div>
                  <div className="text-xs text-gray-500">{stats.correct}/{stats.total} correct</div>
                </div>
              )
            })}
          </div>
        ) : (
          <div className="text-gray-500 text-center py-4">Grading in progress...</div>
        )}
      </div>

      {/* Scan History */}
      <div className="glass p-4">
        <h2 className="text-lg font-semibold mb-3">📊 Recent Scans</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead><tr className="text-gray-400 border-b border-white/10">
              <th className="text-left py-2 px-3">Time</th>
              <th className="text-right py-2 px-3">Duration</th>
              <th className="text-right py-2 px-3">Stocks</th>
              <th className="text-right py-2 px-3">AI</th>
              <th className="text-right py-2 px-3">Buys</th>
              <th className="text-right py-2 px-3">Blocks</th>
            </tr></thead>
            <tbody>
              {scans.map((s: any, i: number) => (
                <tr key={i} className="border-b border-white/5 hover:bg-white/5">
                  <td className="py-2 px-3 text-gray-400">{s?.created_at ? new Date(s.created_at).toLocaleTimeString() : '—'}</td>
                  <td className="py-2 px-3 text-right font-mono">{s?.duration_ms ? `${(s.duration_ms / 1000).toFixed(0)}s` : '—'}</td>
                  <td className="py-2 px-3 text-right">{s?.stocks_scanned ?? '—'}</td>
                  <td className="py-2 px-3 text-right">{s?.ai_verdicts_count ?? '—'}</td>
                  <td className="py-2 px-3 text-right text-[#00ff88]">{s?.buys_executed ?? 0}</td>
                  <td className="py-2 px-3 text-right text-[#ff4444]">{s?.blocks_count ?? 0}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
