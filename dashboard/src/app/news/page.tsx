'use client'
import { useEffect, useState, useCallback } from 'react'

const API = 'https://api.beast-trader.com'

function scoreBadge(score: number | null | undefined): { text: string; color: string } {
  if (score == null) return { text: '—', color: 'bg-slate-600 text-slate-300' }
  if (score > 0) return { text: `+${score}`, color: 'bg-green-500/20 text-green-400' }
  if (score < 0) return { text: `${score}`, color: 'bg-red-500/20 text-red-400' }
  return { text: '0', color: 'bg-slate-600/40 text-slate-400' }
}

function categoryIcon(cat: string): string {
  const c = (cat || '').toLowerCase()
  if (c.includes('trump') || c.includes('tariff')) return '🏛️'
  if (c.includes('break')) return '🔴'
  if (c.includes('geo')) return '🌍'
  if (c.includes('fed') || c.includes('rate')) return '🏦'
  if (c.includes('earn')) return '💰'
  return '📰'
}

export default function NewsPage() {
  const [news, setNews] = useState<any[]>([])
  const [loading, setLoading] = useState(true)

  const fetchData = useCallback(() => {
    fetch(`${API}/api/news`)
      .then(r => r.json())
      .then(data => {
        setNews(Array.isArray(data) ? data : data.headlines || data.news || [])
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [])

  useEffect(() => {
    fetchData()
    const interval = setInterval(fetchData, 120000)
    return () => clearInterval(interval)
  }, [fetchData])

  if (loading) return (
    <div className="space-y-4">
      <div className="h-8 bg-slate-800 rounded animate-pulse w-48" />
      {[...Array(6)].map((_, i) => <div key={i} className="h-20 bg-slate-800 rounded-xl animate-pulse" />)}
    </div>
  )

  // Group by category
  const grouped: Record<string, any[]> = {}
  news.forEach(item => {
    const cat = item.category || item.section || 'General'
    if (!grouped[cat]) grouped[cat] = []
    grouped[cat].push(item)
  })

  // Sort each group newest first
  Object.values(grouped).forEach(items =>
    items.sort((a, b) => new Date(b.timestamp ?? b.time ?? 0).getTime() - new Date(a.timestamp ?? a.time ?? 0).getTime())
  )

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">📰 Live News Feed</h1>

      {Object.entries(grouped).length > 0 ? (
        Object.entries(grouped).map(([category, items]) => (
          <div key={category}>
            <h2 className="text-sm font-bold text-slate-400 uppercase tracking-wider mb-3 flex items-center gap-2">
              {categoryIcon(category)} {category}
            </h2>
            <div className="space-y-2">
              {items.map((item: any, idx: number) => {
                const badge = scoreBadge(item.score ?? item.sentiment)
                const time = item.timestamp ?? item.time
                return (
                  <div key={idx} className="bg-slate-800 rounded-xl p-4 border border-slate-700 flex items-start gap-3">
                    <div className="flex-1 min-w-0">
                      <p className="text-white text-sm font-medium leading-snug">{item.headline ?? item.title}</p>
                      {item.summary && <p className="text-slate-400 text-xs mt-1 line-clamp-2">{item.summary}</p>}
                      {time && (
                        <p className="text-slate-500 text-xs mt-1">
                          {new Date(time).toLocaleTimeString()}
                        </p>
                      )}
                    </div>
                    <span className={`text-xs font-bold px-2 py-1 rounded-full whitespace-nowrap ${badge.color}`}>
                      {badge.text}
                    </span>
                  </div>
                )
              })}
            </div>
          </div>
        ))
      ) : (
        <div className="glass-card p-6 text-center">
          <div className="text-4xl mb-2">📰</div>
          <p className="text-slate-400">No recent headlines</p>
          <p className="text-slate-500 text-sm">News feed refreshes every 2 minutes</p>
        </div>
      )}
      <p className="text-xs text-slate-600 text-center">Auto-refreshes every 2 min</p>
    </div>
  )
}
