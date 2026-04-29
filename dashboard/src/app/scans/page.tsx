'use client'
import { useEffect, useState } from 'react'

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8080'

export default function ScansPage() {
  const [scans, setScans] = useState<any[]>([])

  useEffect(() => {
    fetch(`${API}/api/scans?limit=50`).then(r => r.json()).then(d => setScans(d.scans || []))
  }, [])

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">🔍 AI Scan History</h1>
      <p className="text-slate-400">Every 5 minutes, Beast runs a full scan: TV indicators → Sentiment → Confidence Engine → AI Analysis</p>

      {scans.length === 0 ? (
        <div className="bg-slate-800 rounded-xl p-6 border border-slate-700 text-center py-10">
          <p className="text-slate-400">No scans yet. First scan runs ~5 minutes after bot starts.</p>
        </div>
      ) : (
        <div className="bg-slate-800 rounded-xl p-6 border border-slate-700 overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-slate-400 border-b border-slate-700">
                <th className="text-left py-2 px-3">Time</th>
                <th className="text-left py-2 px-3">Type</th>
                <th className="text-left py-2 px-3">Regime</th>
                <th className="text-right py-2 px-3">Equity</th>
                <th className="text-right py-2 px-3">P&L</th>
                <th className="text-right py-2 px-3">SPY</th>
                <th className="text-center py-2 px-3">TV</th>
                <th className="text-center py-2 px-3">Sent</th>
                <th className="text-center py-2 px-3">AI</th>
                <th className="text-center py-2 px-3">Trump</th>
                <th className="text-center py-2 px-3">Pos</th>
              </tr>
            </thead>
            <tbody>
              {scans.map((s: any, i: number) => (
                <tr key={i} className="hover:bg-slate-700/50 border-b border-slate-700/50">
                  <td className="py-2 px-3 text-slate-400 text-xs font-mono">{s.timestamp?.slice(11, 19)}</td>
                  <td className="py-2 px-3">
                    <span className="px-2 py-0.5 rounded text-xs bg-blue-500/20 text-blue-400">{s.scan_type}</span>
                  </td>
                  <td className="py-2 px-3">
                    <span className={`px-2 py-0.5 rounded text-xs ${
                      s.regime === 'BULL' ? 'bg-green-500/20 text-green-400' :
                      s.regime === 'BEAR' ? 'bg-red-500/20 text-red-400' :
                      'bg-yellow-500/20 text-yellow-400'
                    }`}>{s.regime}</span>
                  </td>
                  <td className="text-right py-2 px-3 font-mono">${s.equity?.toLocaleString()}</td>
                  <td className={`text-right py-2 px-3 font-bold ${(s.total_pl || 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                    ${s.total_pl?.toFixed(2)}
                  </td>
                  <td className={`text-right py-2 px-3 ${(s.spy_change || 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                    {((s.spy_change || 0) * 100).toFixed(2)}%
                  </td>
                  <td className="text-center py-2 px-3">{s.tv_reads || 0}</td>
                  <td className="text-center py-2 px-3">{s.sentiments || 0}</td>
                  <td className="text-center py-2 px-3">{s.ai_calls || 0}</td>
                  <td className={`text-center py-2 px-3 ${(s.trump_score || 0) < 0 ? 'text-red-400' : 'text-green-400'}`}>
                    {s.trump_score || 0}
                  </td>
                  <td className="text-center py-2 px-3">{s.positions || 0}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

