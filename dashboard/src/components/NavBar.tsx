'use client'
import CommandBar from './CommandBar'

const navLinks = [
  { href: '/', label: '📊 Dashboard' },
  { href: '/positions', label: '💼 Positions' },
  { href: '/trades', label: '📋 Trades' },
  { href: '/scans', label: '🔍 Scans' },
  { href: '/analytics', label: '📈 Analytics' },
  { href: '/system', label: '⚙️ System' },
  { href: '/runners', label: '🏃 Runners' },
  { href: '/sectors', label: '🗺️ Sectors' },
  { href: '/stops', label: '🛡️ Stops' },
  { href: '/news', label: '📰 News' },
  { href: '/ai', label: '🧠 AI' },
  { href: '/activity', label: '📋 Activity' },
  { href: '/decisions', label: '🎯 Decisions' },
  { href: '/feed', label: '📡 Feed' },
]

export default function NavBar() {
  return (
    <>
      <nav className="bg-slate-800 border-b border-slate-700 px-6 py-3 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-2xl">🦍</span>
          <h1 className="text-xl font-bold text-white">Beast Terminal V4</h1>
          <span className="text-xs bg-green-500/20 text-green-400 px-2 py-0.5 rounded-full">LIVE</span>
        </div>
        <div className="flex gap-1 flex-wrap">
          {navLinks.map(link => (
            <a key={link.href} href={link.href}
              className="px-2 py-1 rounded-lg text-xs text-slate-300 hover:bg-slate-700 hover:text-white transition-colors">
              {link.label}
            </a>
          ))}
        </div>
      </nav>
      <div className="bg-slate-950 border-b border-slate-700 px-6 py-2">
        <CommandBar />
      </div>
    </>
  )
}
