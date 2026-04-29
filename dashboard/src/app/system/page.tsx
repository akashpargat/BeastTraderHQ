'use client'
import { useEffect, useState } from 'react'

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8080'

export default function SystemPage() {
  const [system, setSystem] = useState<any>(null)
  const [debug, setDebug] = useState<any[]>([])
  const [alerts, setAlerts] = useState<any[]>([])

  useEffect(() => {
    fetch(`${API}/api/system`).then(r => r.json()).then(setSystem)
    fetch(`${API}/api/debug?limit=20`).then(r => r.json()).then(d => setDebug(d.entries || []))
    fetch(`${API}/api/alerts`).then(r => r.json()).then(d => setAlerts(d.alerts || []))
  }, [])

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">⚙️ System Status</h1>

      {/* Health Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <HealthCard name="AI Brain" status={system?.ai?.status} detail={system?.ai?.url} icon="🧠" />
        <HealthCard name="TradingView" status={system?.tv?.status === 'connected' ? 'online' : 'offline'} detail="CDP :9222" icon="📺" />
        <HealthCard name="Discord Bot" status={system?.bot?.status === 'running' ? 'online' : 'offline'} detail="Beast Trader#5020" icon="🤖" />
        <HealthCard name="Dashboard API" status="online" detail=":8080" icon="🌐" />
      </div>

      {/* Architecture */}
      <div className="bg-slate-800 rounded-xl p-6 border border-slate-700">
        <h2 className="text-lg font-semibold mb-3">🏗️ Architecture</h2>
        <pre className="text-xs text-slate-400 font-mono leading-relaxed">{`
  Work Laptop                     Azure VM (beast-trader-vm)
  ┌──────────────┐               ┌──────────────────────────────┐
  │ copilot-api  │◄──Cloudflare──│ Discord Bot (autonomous)     │
  │ Claude 4.7   │   Tunnel      │ ├─ 60s position monitor      │
  │ Flask :5555  │   (permanent) │ ├─ 5min full scan (TV+AI)    │
  └──────────────┘               │ ├─ 10min decision report     │
  ai.beast-trader.com            │ ├─ Auto-scalp/runner/dip     │
                                 │ TradingView Desktop (CDP)    │
                                 │ Dashboard API (:8080)        │
                                 │ Dashboard UI (:3000)         │
                                 └──────────────────────────────┘
        `}</pre>
      </div>

      {/* Recent Alerts */}
      {alerts.length > 0 && (
        <div className="bg-slate-800 rounded-xl p-6 border border-slate-700">
          <h2 className="text-lg font-semibold mb-3">🔔 Recent Alerts</h2>
          <div className="space-y-1 max-h-64 overflow-y-auto">
            {alerts.map((a: any, i: number) => (
              <div key={i} className="flex gap-3 text-sm py-1.5 border-b border-slate-700/50">
                <span className="text-slate-500 text-xs w-16">{a.timestamp?.slice(11, 19)}</span>
                <span className={`px-2 py-0.5 rounded text-xs ${
                  a.alert_type === 'TRADE' ? 'bg-green-500/20 text-green-400' :
                  a.alert_type === 'DROP' ? 'bg-red-500/20 text-red-400' :
                  'bg-yellow-500/20 text-yellow-400'
                }`}>{a.alert_type}</span>
                <span className="font-mono">{a.symbol}</span>
                <span className="text-slate-400 truncate">{a.message?.slice(0, 60)}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Debug Log */}
      <div className="bg-slate-800 rounded-xl p-6 border border-slate-700">
        <h2 className="text-lg font-semibold mb-3">🔧 Debug Log</h2>
        {debug.length === 0 ? (
          <p className="text-slate-400">No debug entries. System is clean.</p>
        ) : (
          <div className="space-y-1 max-h-64 overflow-y-auto font-mono text-xs">
            {debug.map((d: any, i: number) => (
              <div key={i} className={`py-1 ${
                d.level === 'ERROR' ? 'text-red-400' :
                d.level === 'WARNING' ? 'text-yellow-400' : 'text-slate-400'
              }`}>
                [{d.timestamp?.slice(11, 19)}] {d.level} {d.component}: {d.message?.slice(0, 80)}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function HealthCard({ name, status, detail, icon }: { name: string; status: string; detail?: string; icon: string }) {
  const isOnline = status === 'online'
  return (
    <div className={`card border ${isOnline ? 'border-green-500/30' : 'border-red-500/30'}`}>
      <div className="flex items-center gap-2 mb-2">
        <span className="text-xl">{icon}</span>
        <span className="font-semibold">{name}</span>
      </div>
      <div className={`text-sm font-bold ${isOnline ? 'text-green-400' : 'text-red-400'}`}>
        {isOnline ? '● Online' : '○ Offline'}
      </div>
      {detail && <p className="text-xs text-slate-500 mt-1 truncate">{detail}</p>}
    </div>
  )
}

