'use client'
import CommandBar from './CommandBar'
import { useAuth } from './AuthProvider'

const navLinks = [
  { href: '/', label: '📊 Dashboard' },
  { href: '/positions', label: '💼 Positions' },
  { href: '/trades', label: '📋 Trades' },
  { href: '/decisions', label: '🎯 Decisions' },
  { href: '/ai', label: '🧠 AI' },
  { href: '/performance', label: '⏱️ Perf' },
  { href: '/blue-chips', label: '💎 Blue Chips' },
  { href: '/config', label: '🔧 Config' },
  { href: '/runners', label: '🏃 Runners' },
  { href: '/stops', label: '🛡️ Stops' },
  { href: '/sectors', label: '🗺️ Sectors' },
  { href: '/analytics', label: '📈 Analytics' },
  { href: '/backtest', label: '🔬 Backtest' },
  { href: '/activity', label: '⚡ Activity' },
  { href: '/scans', label: '🔍 Scans' },
  { href: '/news', label: '📰 News' },
  { href: '/system', label: '⚙️ System' },
  { href: '/notifications', label: '🔔 Alerts' },
  { href: '/feed', label: '📡 Feed' },
  { href: '/pro-intel', label: '🧠 Pro Intel' },
  { href: '/risk', label: '🛡️ Risk' },
  { href: '/congress', label: '🏛️ Congress' },
  { href: '/market', label: '🌍 Market' },
]

export default function NavBar() {
  const { username, logout } = useAuth()
  return (
    <>
      <nav className="bg-slate-800 border-b border-slate-700 px-6 py-3 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-2xl">🦍</span>
          <h1 className="text-xl font-bold text-white">Beast Terminal V4</h1>
          <span className="text-xs bg-green-500/20 text-green-400 px-2 py-0.5 rounded-full">LIVE</span>
        </div>
        <div className="flex gap-1 flex-wrap items-center">
          {navLinks.map(link => (
            <a key={link.href} href={link.href}
              className="px-2 py-1 rounded-lg text-xs text-slate-300 hover:bg-slate-700 hover:text-white transition-colors">
              {link.label}
            </a>
          ))}
          <div className="flex items-center gap-2 ml-4 pl-4 border-l border-slate-700">
            <span className="text-slate-400 text-xs">👤 {username}</span>
            <button onClick={logout}
              className="px-2 py-1 bg-slate-800 border border-slate-700 rounded text-slate-400 text-xs hover:bg-slate-700 transition">
              Logout
            </button>
          </div>
        </div>
      </nav>
      <div className="bg-slate-950 border-b border-slate-700 px-6 py-2">
        <CommandBar />
      </div>
    </>
  )
}
