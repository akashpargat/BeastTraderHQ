import './globals.css'
import NavBar from '../components/NavBar'
import { AuthProvider } from '../components/AuthProvider'

export const metadata = {
  title: 'Beast Terminal V4',
  description: 'Autonomous AI Trading Terminal',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-[#0a0a0a]">
        <AuthProvider>
          <NavBar />
          <main className="max-w-7xl mx-auto px-6 py-6">
            {children}
          </main>
          <footer className="text-center text-slate-600 text-xs py-4 border-t border-slate-800/50">
            Beast Terminal V4 • 🔒 Authenticated Session
          </footer>
        </AuthProvider>
      </body>
    </html>
  )
}



