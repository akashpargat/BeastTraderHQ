import './globals.css'
import NavBar from '../components/NavBar'

export const metadata = {
  title: 'Beast Terminal V4 — Trading Dashboard',
  description: 'Autonomous AI Trading Terminal',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-slate-900">
        <NavBar />
        <main className="max-w-7xl mx-auto px-6 py-6">
          {children}
        </main>
        <footer className="text-center text-slate-500 text-xs py-4 border-t border-slate-800">
          Beast Terminal V4 • Auto-refreshes every 10s • Paper Trading
        </footer>
      </body>
    </html>
  )
}



