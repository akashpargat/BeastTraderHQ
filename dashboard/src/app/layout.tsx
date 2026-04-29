import './globals.css'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'https://api.beast-trader.com'

export const metadata = {
  title: 'Beast Trader V3 — Dashboard',
  description: 'Autonomous AI Trading Engine Dashboard',
}

const navLinks = [
  { href: '/', label: '📊 Dashboard' },
  { href: '/positions', label: '💼 Positions' },
  { href: '/trades', label: '📋 Trades' },
  { href: '/scans', label: '🔍 Scans' },
  { href: '/analytics', label: '📈 Analytics' },
  { href: '/system', label: '⚙️ System' },
]

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-slate-900">
        {/* Top Nav */}
        <nav className="bg-slate-800 border-b border-slate-700 px-6 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="text-2xl">🦍</span>
            <h1 className="text-xl font-bold text-white">Beast Trader V3</h1>
            <span className="text-xs bg-green-500/20 text-green-400 px-2 py-0.5 rounded-full">LIVE</span>
          </div>
          <div className="flex gap-1">
            {navLinks.map(link => (
              <a key={link.href} href={link.href}
                className="px-3 py-1.5 rounded-lg text-sm text-slate-300 hover:bg-slate-700 hover:text-white transition-colors">
                {link.label}
              </a>
            ))}
          </div>
        </nav>

        {/* Main Content */}
        <main className="max-w-7xl mx-auto px-6 py-6">
          {children}
        </main>

        {/* Footer */}
        <footer className="text-center text-slate-500 text-xs py-4 border-t border-slate-800">
          Beast Engine V3 • Auto-refreshes every 60s • Paper Trading (PA37M4LP1YKP)
        </footer>
      </body>
    </html>
  )
}



