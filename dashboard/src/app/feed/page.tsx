'use client'
import { useEffect, useState, useCallback } from 'react'

const API = 'https://api.beast-trader.com'

// Urgency color mapping
const urgencyColors: Record<string, string> = {
  critical: 'border-red-500 bg-red-950/30',
  bearish: 'border-orange-500 bg-orange-950/20',
  bullish: 'border-green-500 bg-green-950/20',
  trade: 'border-blue-500 bg-blue-950/20',
  celebration: 'border-yellow-500 bg-yellow-950/30',
  warning: 'border-purple-500 bg-purple-950/20',
  normal: 'border-slate-700 bg-slate-900/50',
}

const categoryIcons: Record<string, string> = {
  BREAKING: '🚨', TRUMP: '🏛️', FED: '🏦', GEOPOLITICAL: '⚔️',
  EARNINGS: '📊', AI: '🤖', CRYPTO: '₿', STOCK_NEWS: '📰',
  FILL: '💹', PROFIT: '🎉', SQUEEZE: '🔥', 
}

const categoryBadgeColors: Record<string, string> = {
  BREAKING: 'bg-red-600', TRUMP: 'bg-orange-600', FED: 'bg-blue-600',
  GEOPOLITICAL: 'bg-red-800', EARNINGS: 'bg-purple-600', AI: 'bg-cyan-600',
  CRYPTO: 'bg-yellow-600', STOCK_NEWS: 'bg-slate-600', FILL: 'bg-blue-500',
  PROFIT: 'bg-green-500', SQUEEZE: 'bg-red-500',
}

export default function LiveFeed() {
  const [feed, setFeed] = useState<any[]>([])
  const [filter, setFilter] = useState('ALL')
  const [loading, setLoading] = useState(true)

  const fetchFeed = useCallback(async () => {
    try {
      const res = await fetch(`${API}/api/live-feed`)
      const data = await res.json()
      setFeed(data.feed || [])
    } catch (e) { console.error('Feed fetch failed:', e) }
    setLoading(false)
  }, [])

  useEffect(() => {
    fetchFeed()
    const i = setInterval(fetchFeed, 30000) // Refresh every 30s
    return () => clearInterval(i)
  }, [fetchFeed])

  const filters = ['ALL', 'NEWS', 'TRADE', 'CATALYST', 'CELEBRATION']
  const filtered = filter === 'ALL' ? feed : feed.filter(f => f.type === filter)

  if (loading) return (
    <div className="flex items-center justify-center min-h-[60vh]">
      <div className="text-center">
        <div className="text-6xl mb-4 animate-bounce">📡</div>
        <p className="text-slate-400">Loading live feed...</p>
      </div>
    </div>
  )

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-white">📡 Live Feed</h1>
          <p className="text-slate-500 text-sm">24/7 breaking news, catalysts, trades & celebrations</p>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
          <span className="text-green-400 text-sm">LIVE</span>
          <span className="text-slate-600 text-xs">{feed.length} items</span>
        </div>
      </div>

      {/* Filter tabs */}
      <div className="flex gap-2 mb-6 flex-wrap">
        {filters.map(f => (
          <button key={f} onClick={() => setFilter(f)}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
              filter === f 
                ? 'bg-green-600 text-white' 
                : 'bg-slate-800 text-slate-400 hover:bg-slate-700'
            }`}>
            {f === 'ALL' ? `📡 ALL (${feed.length})` :
             f === 'NEWS' ? `📰 NEWS` :
             f === 'TRADE' ? `💹 TRADES` :
             f === 'CATALYST' ? `⚡ CATALYSTS` :
             `🎉 CELEBRATIONS`}
          </button>
        ))}
      </div>

      {/* Feed items */}
      <div className="space-y-3">
        {filtered.map((item, i) => (
          <div key={i} 
            className={`border-l-4 rounded-r-xl p-4 transition-all hover:translate-x-1 ${urgencyColors[item.urgency] || urgencyColors.normal}`}
            style={{ animationDelay: `${i * 0.05}s` }}>
            <div className="flex items-start justify-between">
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-lg">{categoryIcons[item.category] || '📌'}</span>
                  <span className={`text-[10px] px-2 py-0.5 rounded-full text-white font-bold ${categoryBadgeColors[item.category] || 'bg-slate-600'}`}>
                    {item.category}
                  </span>
                  {item.symbol && (
                    <span className="text-xs px-2 py-0.5 rounded bg-slate-700 text-white font-mono">
                      {item.symbol}
                    </span>
                  )}
                  {item.urgency === 'critical' && (
                    <span className="text-red-400 text-xs animate-pulse font-bold">⚠ CRITICAL</span>
                  )}
                </div>
                <p className={`text-sm ${
                  item.urgency === 'celebration' ? 'text-yellow-300 font-bold' :
                  item.urgency === 'critical' ? 'text-red-300' :
                  item.urgency === 'bullish' ? 'text-green-300' :
                  'text-slate-300'
                }`}>
                  {item.headline}
                </p>
              </div>
              <span className="text-slate-600 text-xs whitespace-nowrap ml-4">
                {item.time ? new Date(item.time).toLocaleTimeString() : ''}
              </span>
            </div>

            {/* Celebration animation */}
            {item.type === 'CELEBRATION' && (
              <div className="mt-2 text-2xl animate-bounce">
                🎉💰🎊💸✨
              </div>
            )}
          </div>
        ))}

        {filtered.length === 0 && (
          <div className="glass-card p-8 text-center">
            <div className="text-5xl mb-3">📡</div>
            <p className="text-slate-400">No items in this category</p>
          </div>
        )}
      </div>
    </div>
  )
}
