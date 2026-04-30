'use client'
import { useEffect, useState, useCallback } from 'react'
import { authFetch } from '../../lib/api'

export default function ScansPage() {
  const [scans, setScans] = useState<any[]>([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  const fetchData = useCallback(async () => {
    try {
      const res = await authFetch('/api/v4/scan-snapshots?limit=30')
      if (res.ok) { setScans(await res.json()); setError('') }
      else setError(`API error: ${res.status}`)
    } catch (e: any) { setError(e.message || 'Connection failed') }
    setLoading(false)
  }, [])

  useEffect(() => { fetchData(); const i = setInterval(fetchData, 15000); return () => clearInterval(i) }, [fetchData])

  if (loading) return <div className="flex items-center justify-center min-h-[50vh]"><div className="text-4xl animate-bounce">🦍</div></div>
  if (error) return <div className="glass p-6 text-center text-red-400">{error}</div>

  return (
    <div className="fade-in">
      <h1 className="text-2xl font-bold mb-6">🔍 Scan History ({scans.length})</h1>
      {scans.length === 0 ? (
        <div className="glass p-12 text-center text-gray-500"><div className="text-4xl mb-2">📭</div>No scans yet</div>
      ) : (
        <div className="glass p-4 overflow-x-auto">
          <table className="w-full text-sm">
            <thead><tr className="text-gray-400 border-b border-white/10">
              <th className="text-left py-2 px-3">Time</th>
              <th className="text-right py-2 px-3">Duration</th>
              <th className="text-right py-2 px-3">Stocks</th>
              <th className="text-right py-2 px-3">TV</th>
              <th className="text-right py-2 px-3">AI</th>
              <th className="text-right py-2 px-3">Buys</th>
              <th className="text-right py-2 px-3">Blocks</th>
              <th className="text-left py-2 px-3">Regime</th>
              <th className="text-right py-2 px-3">P&L</th>
            </tr></thead>
            <tbody>
              {scans.map((s: any, i: number) => (
                <tr key={i} className="border-b border-white/5 hover:bg-white/5 transition">
                  <td className="py-2 px-3 text-gray-400">{s?.created_at ? new Date(s.created_at).toLocaleTimeString() : '—'}</td>
                  <td className="py-2 px-3 text-right font-mono">{s?.duration_ms ? `${(s.duration_ms / 1000).toFixed(0)}s` : '—'}</td>
                  <td className="py-2 px-3 text-right">{s?.stocks_scanned ?? '—'}</td>
                  <td className="py-2 px-3 text-right">{s?.stocks_with_tv ?? '—'}</td>
                  <td className="py-2 px-3 text-right">{s?.ai_verdicts_count ?? '—'}</td>
                  <td className="py-2 px-3 text-right text-[#00ff88]">{s?.buys_executed ?? 0}</td>
                  <td className="py-2 px-3 text-right text-[#ff4444]">{s?.blocks_count ?? 0}</td>
                  <td className="py-2 px-3">{s?.regime ?? '—'}</td>
                  <td className={`py-2 px-3 text-right ${(s?.total_pl ?? 0) >= 0 ? 'text-[#00ff88]' : 'text-[#ff4444]'}`}>
                    ${Number(s?.total_pl ?? 0).toFixed(0)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
