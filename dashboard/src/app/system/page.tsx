'use client'
import { useEffect, useState, useCallback } from 'react'
import { authFetch } from '../../lib/api'

interface ServiceCard {
  icon: string
  name: string
  statusKey: string
  getStatus: (sys: any) => boolean
  getDetail: (sys: any) => string
  getSubDetail: (sys: any) => string
}

const SERVICES: ServiceCard[] = [
  {
    icon: '🤖', name: 'GPT-4o',
    statusKey: 'gpt',
    getStatus: (s) => s?.ai?.status === 'online' || s?.gpt?.status === 'online',
    getDetail: (s) => s?.gpt?.endpoint || s?.ai?.url || 'api.openai.com',
    getSubDetail: (s) => s?.gpt?.last_call ? `Last call: ${new Date(s.gpt.last_call).toLocaleTimeString()}` : '',
  },
  {
    icon: '🧠', name: 'Claude',
    statusKey: 'claude',
    getStatus: (s) => s?.claude?.status === 'online' || s?.ai?.status === 'online',
    getDetail: (s) => s?.claude?.tunnel_url || s?.ai?.url || 'ai.beast-trader.com',
    getSubDetail: (s) => s?.claude?.last_deep_scan ? `Deep scan: ${new Date(s.claude.last_deep_scan).toLocaleTimeString()}` : '',
  },
  {
    icon: '📺', name: 'TradingView',
    statusKey: 'tv',
    getStatus: (s) => s?.tv?.status === 'connected' || s?.tv?.status === 'online',
    getDetail: (s) => `CDP :${s?.tv?.port || 9222}`,
    getSubDetail: (s) => s?.tv?.indicators ? `${s.tv.indicators} indicators` : '',
  },
  {
    icon: '💬', name: 'Discord Bot',
    statusKey: 'bot',
    getStatus: (s) => s?.bot?.status === 'running' || s?.bot?.status === 'online',
    getDetail: (s) => s?.bot?.username || 'Beast Trader#5020',
    getSubDetail: (s) => s?.bot?.uptime || '',
  },
  {
    icon: '🗄️', name: 'PostgreSQL',
    statusKey: 'db',
    getStatus: (s) => s?.db?.status === 'online' || s?.db?.status !== 'offline',
    getDetail: (s) => s?.db?.host || 'localhost:5432',
    getSubDetail: (s) => s?.db?.tables ? `${s.db.tables} tables` : '',
  },
  {
    icon: '🌐', name: 'Dashboard API',
    statusKey: 'api',
    getStatus: () => true,
    getDetail: () => ':8080',
    getSubDetail: (s) => s?.api?.endpoints ? `${s.api.endpoints} endpoints` : '',
  },
]

const LOOPS = [
  { name: 'Position Monitor', interval: '60s' },
  { name: 'Full Scan (TV+AI)', interval: '5min' },
  { name: 'Decision Report', interval: '10min' },
  { name: 'Trailing Stop Check', interval: '30s' },
  { name: 'Portfolio Sync', interval: '2min' },
]

export default function SystemPage() {
  const [system, setSystem] = useState<any>(null)

  const fetchData = useCallback(() => {
    authFetch('/api/system').then(r => r.json()).then(setSystem).catch(() => {})
  }, [])

  useEffect(() => {
    fetchData()
    const interval = setInterval(fetchData, 10000)
    return () => clearInterval(interval)
  }, [fetchData])

  if (!system) return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="flex flex-col items-center gap-4">
        <div className="w-12 h-12 border-2 border-[#00ff88]/30 border-t-[#00ff88] rounded-full animate-spin" />
        <p className="text-slate-500 text-sm">Checking systems...</p>
      </div>
    </div>
  )

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">⚙️ System Status</h1>
        <p className="text-slate-500 text-sm mt-1">All services · Auto-refresh 10s</p>
      </div>

      {/* 6 Service Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-3 gap-5 stagger-enter">
        {SERVICES.map((svc) => {
          const online = svc.getStatus(system)
          const detail = svc.getDetail(system)
          const sub = svc.getSubDetail(system)

          return (
            <div key={svc.name} className={`glass-card hover-scale-glow p-5 relative overflow-hidden ${online ? '' : 'opacity-60'}`}>
              <div className={`absolute top-0 left-0 w-full h-0.5 ${online ? 'bg-[#00ff88]' : 'bg-red-500'}`} />
              <div className="flex items-center gap-3 mb-3">
                <span className="text-2xl">{svc.icon}</span>
                <div>
                  <h3 className="font-semibold text-white">{svc.name}</h3>
                  <div className="flex items-center gap-1.5 mt-0.5">
                    <div className={`w-2 h-2 rounded-full ${online ? 'bg-[#00ff88] live-dot' : 'bg-red-500'}`} />
                    <span className={`text-xs font-medium ${online ? 'text-[#00ff88]' : 'text-red-400'}`}>
                      {online ? 'Online' : 'Offline'}
                    </span>
                  </div>
                </div>
              </div>
              <p className="text-xs text-slate-400 font-mono truncate">{detail}</p>
              {sub && <p className="text-[10px] text-slate-600 mt-1">{sub}</p>}
            </div>
          )
        })}
      </div>

      {/* Architecture Diagram */}
      <div className="glass-card p-6">
        <h2 className="text-lg font-semibold mb-4">🏗️ Architecture</h2>
        <pre className="text-[11px] text-slate-400 font-mono leading-relaxed overflow-x-auto">{`
  Work Laptop                          Azure VM (beast-trader-vm)
  ┌────────────────┐                  ┌──────────────────────────────────┐
  │  copilot-api   │◄──Cloudflare────│  Discord Bot (autonomous)        │
  │  Claude 4.7    │   Tunnel        │  ├─ 60s  position monitor        │
  │  Flask :5555   │   (permanent)   │  ├─ 5min full scan (TV+AI)       │
  └────────────────┘                 │  ├─ 10min decision report        │
  ai.beast-trader.com                │  ├─ Auto-scalp / runner / dip    │
                                     │                                  │
                                     │  TradingView Desktop (CDP:9222)  │
                                     │  Dashboard API (:8080)           │
                                     │  Dashboard UI  (:3000)           │
                                     │  PostgreSQL    (:5432)           │
                                     └──────────────────────────────────┘`}</pre>
      </div>

      {/* Loop Status */}
      <div className="glass-card p-6">
        <h2 className="text-lg font-semibold mb-4">🔄 Autonomous Loops</h2>
        <div className="space-y-3">
          {LOOPS.map((loop, i) => {
            const loopData = system?.loops?.[i] || system?.loops?.find?.((l: any) => l.name?.includes(loop.name.split(' ')[0].toLowerCase()))

            return (
              <div key={loop.name} className="flex items-center gap-4 py-2 border-b border-white/[0.04] last:border-0">
                <div className="w-2 h-2 rounded-full bg-[#00ff88] live-dot shrink-0" />
                <div className="flex-1">
                  <p className="text-sm text-white font-medium">{loop.name}</p>
                  <p className="text-[10px] text-slate-500">Every {loop.interval}</p>
                </div>
                <span className="text-xs text-slate-500 font-mono">
                  {loopData?.last_run ? new Date(loopData.last_run).toLocaleTimeString() : '—'}
                </span>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}