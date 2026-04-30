'use client'
import { useEffect, useState, useCallback, useRef } from 'react'
import { authFetch } from '../lib/api'

// ── Animated number counter hook ──
function useCounter(target: number, duration = 1000) {
  const [value, setValue] = useState(0)
  const prev = useRef(0)
  useEffect(() => {
    if (target === prev.current) return
    const start = prev.current
    const diff = target - start
    const startTime = performance.now()
    const tick = (now: number) => {
      const elapsed = now - startTime
      const progress = Math.min(elapsed / duration, 1)
      const eased = 1 - Math.pow(1 - progress, 3) // ease-out cubic
      setValue(start + diff * eased)
      if (progress < 1) requestAnimationFrame(tick)
    }
    requestAnimationFrame(tick)
    prev.current = target
  }, [target, duration])
  return value
}

// ── Format helpers ──
const fmt = (n: number) => n?.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) ?? '0.00'
const fmtInt = (n: number) => Math.round(n)?.toLocaleString('en-US') ?? '0'
const pct = (n: number) => (n >= 0 ? '+' : '') + n?.toFixed(2) + '%'
const ago = (ts: string) => {
  if (!ts) return ''
  const diff = (Date.now() - new Date(ts).getTime()) / 1000
  if (diff < 60) return `${Math.round(diff)}s ago`
  if (diff < 3600) return `${Math.round(diff / 60)}m ago`
  return `${Math.round(diff / 3600)}h ago`
}

const ACTION_ICONS: Record<string, string> = {
  buy: '🎯', sell: '💰', trail_update: '🛡️', stop_loss: '📉',
  runner: '🏃', scan: '🔍', alert: '⚡', default: '📌',
}
const STOCK_COLORS = ['#00aaff', '#9b59b6', '#00ff88', '#ff4444', '#f39c12', '#e74c3c', '#1abc9c', '#3498db']

function stockColor(sym: string) {
  let hash = 0
  for (let i = 0; i < (sym?.length || 0); i++) hash = sym.charCodeAt(i) + ((hash << 5) - hash)
  return STOCK_COLORS[Math.abs(hash) % STOCK_COLORS.length]
}

// ── Circular progress ring ──
function Ring({ pct: p, size = 56, stroke = 5 }: { pct: number; size?: number; stroke?: number }) {
  const r = (size - stroke) / 2
  const circ = 2 * Math.PI * r
  const offset = circ - (Math.min(p, 100) / 100) * circ
  return (
    <svg width={size} height={size} className="transform -rotate-90">
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth={stroke} />
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#00ff88" strokeWidth={stroke}
        strokeDasharray={circ} strokeDashoffset={offset} strokeLinecap="round"
        style={{ transition: 'stroke-dashoffset 1s ease-out' }} />
    </svg>
  )
}

// ── Fear & Greed gauge ──
function FearGreedGauge({ value }: { value: number }) {
  const angle = -90 + (Math.min(Math.max(value, 0), 100) / 100) * 180
  const color = value < 25 ? '#ff4444' : value < 45 ? '#f39c12' : value < 55 ? '#888' : value < 75 ? '#00aaff' : '#00ff88'
  const label = value < 25 ? 'Extreme Fear' : value < 45 ? 'Fear' : value < 55 ? 'Neutral' : value < 75 ? 'Greed' : 'Extreme Greed'
  return (
    <div className="flex flex-col items-center">
      <svg width="140" height="80" viewBox="0 0 140 80">
        <path d="M 15 75 A 55 55 0 0 1 125 75" fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth="10" strokeLinecap="round" />
        <path d="M 15 75 A 55 55 0 0 1 125 75" fill="none" stroke={color} strokeWidth="10" strokeLinecap="round"
          strokeDasharray="173" strokeDashoffset={173 - (value / 100) * 173}
          style={{ transition: 'stroke-dashoffset 1.5s ease-out' }} />
        <line x1="70" y1="75" x2="70" y2="30" stroke={color} strokeWidth="2.5" strokeLinecap="round"
          transform={`rotate(${angle}, 70, 75)`} style={{ transition: 'transform 1.5s ease-out' }} />
        <circle cx="70" cy="75" r="4" fill={color} />
      </svg>
      <span className="text-2xl font-bold mt-1" style={{ color }}>{Math.round(value)}</span>
      <span className="text-xs text-gray-400">{label}</span>
    </div>
  )
}

// ── Skeleton loader ──
function Skeleton({ className = '' }: { className?: string }) {
  return <div className={`skeleton ${className}`} />
}

function SkeletonDashboard() {
  return (
    <div className="min-h-screen p-6 space-y-6">
      <Skeleton className="h-48 w-full" />
      <div className="grid grid-cols-4 gap-4">
        {[...Array(4)].map((_, i) => <Skeleton key={i} className="h-28" />)}
      </div>
      <Skeleton className="h-96 w-full" />
    </div>
  )
}

// ═══════════════════════════════════════════
//  MAIN DASHBOARD
// ═══════════════════════════════════════════
export default function Dashboard() {
  const [portfolio, setPortfolio] = useState<any>(null)
  const [verdicts, setVerdicts] = useState<any[]>([])
  const [actions, setActions] = useState<any[]>([])
  const [breakingNews, setBreakingNews] = useState<any[]>([])
  const [analytics, setAnalytics] = useState<any>(null)
  const [tradingStatus, setTradingStatus] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [expandedRow, setExpandedRow] = useState<string | null>(null)
  const feedRef = useRef<HTMLDivElement>(null)

  const fetchAll = useCallback(async () => {
    try {
      const [pRes, vRes, aRes, anRes, tRes, nRes] = await Promise.all([
        authFetch('/api/portfolio').catch(() => null),
        authFetch('/api/ai-verdicts').catch(() => null),
        authFetch('/api/actions?limit=10').catch(() => null),
        authFetch('/api/analytics').catch(() => null),
        authFetch('/api/trading-status').catch(() => null),
        authFetch('/api/live-feed').catch(() => null),
      ])
      if (pRes?.ok) setPortfolio(await pRes.json())
      if (vRes?.ok) { const d = await vRes.json(); setVerdicts(d.verdicts || d || []) }
      if (aRes?.ok) { const d = await aRes.json(); setActions(d.actions || d || []) }
      if (anRes?.ok) setAnalytics(await anRes.json())
      if (tRes?.ok) setTradingStatus(await tRes.json())
      if (nRes?.ok) { const d = await nRes.json(); setBreakingNews(d.feed?.filter((f: any) => f.type === 'NEWS') || []) }
    } catch (_) {}
    setLoading(false)
  }, [])

  useEffect(() => {
    fetchAll()
    const iv = setInterval(fetchAll, 10_000)
    return () => clearInterval(iv)
  }, [fetchAll])

  // ── Derived values ──
  const positions: any[] = portfolio?.positions || []
  const totalPnl = portfolio?.total_pnl ?? portfolio?.unrealized_pnl ?? 0
  const equity = portfolio?.equity ?? portfolio?.portfolio_value ?? 0
  const cash = portfolio?.cash ?? 0
  const heat = portfolio?.heat_pct ?? portfolio?.heat ?? 0
  const winRate = analytics?.win_rate ?? analytics?.winRate ?? 0
  const posCount = positions.length
  const greenCount = positions.filter((p: any) => (p.unrealized_pnl ?? p.pnl ?? 0) >= 0).length
  const redCount = posCount - greenCount
  const fearGreed = analytics?.fear_greed ?? analytics?.fearGreed ?? 50
  const spyChange = analytics?.spy_change ?? analytics?.spyChange ?? 0
  const regime = analytics?.regime ?? 'unknown'
  const trumpSentiment = analytics?.trump_sentiment ?? analytics?.geoSentiment ?? 0

  // Animated counters
  const animPnl = useCounter(totalPnl, 1200)
  const animEquity = useCounter(equity, 1000)
  const animCash = useCounter(cash, 800)
  const animHeat = useCounter(heat, 800)
  const animWinRate = useCounter(winRate, 1000)

  // Market hours check (ET timezone)
  const isMarketOpen = (() => {
    const now = new Date()
    const et = new Date(now.toLocaleString('en-US', { timeZone: 'America/New_York' }))
    const h = et.getHours()
    const d = et.getDay()
    return d >= 1 && d <= 5 && h >= 9 && h < 16
  })()

  if (loading) return <SkeletonDashboard />

  const pnlPositive = totalPnl >= 0

  return (
    <div className="min-h-screen bg-[#0a0a0a] text-white">

      {/* ═══ SECTION 1: HERO BANNER ═══ */}
      <section className="hero-gradient relative overflow-hidden">
        <div className="max-w-7xl mx-auto px-6 py-10">
          {/* Live indicator */}
          <div className="flex items-center gap-2 mb-6">
            <div className="w-2.5 h-2.5 rounded-full bg-[#00ff88] live-dot" />
            <span className="text-xs font-medium text-[#00ff88] tracking-widest uppercase">Live Terminal</span>
            <span className="text-xs text-gray-500 ml-2">{new Date().toLocaleTimeString()}</span>
          </div>

          {/* Main P&L */}
          <div className="animate-count-up">
            <p className="text-sm text-gray-400 mb-1 tracking-wide uppercase">Total P&L</p>
            <h1 className={`text-6xl md:text-7xl font-black tracking-tight ${pnlPositive ? 'text-[#00ff88] glow-green' : 'text-[#ff4444] glow-red'}`}>
              {pnlPositive ? '+' : ''}{fmt(animPnl)}
            </h1>
          </div>

          {/* Sub-stats */}
          <div className="flex flex-wrap gap-8 mt-6">
            {[
              { label: 'Portfolio Equity', value: `$${fmtInt(animEquity)}` },
              { label: 'Cash Available', value: `$${fmtInt(animCash)}` },
              { label: 'Heat', value: `${animHeat.toFixed(1)}%`, warn: heat > 60 },
            ].map((s) => (
              <div key={s.label} className="animate-card-enter" style={{ animationDelay: '0.2s' }}>
                <p className="text-xs text-gray-500 uppercase tracking-wider">{s.label}</p>
                <p className={`text-xl font-semibold ${s.warn ? 'text-[#f39c12]' : 'text-white'}`}>{s.value}</p>
              </div>
            ))}
          </div>
        </div>
        {/* Subtle bottom fade */}
        <div className="absolute bottom-0 left-0 right-0 h-16 bg-gradient-to-t from-[#0a0a0a] to-transparent" />
      </section>

      <div className="max-w-7xl mx-auto px-6 pb-12 space-y-6">

        {/* Market closed banner */}
        {!isMarketOpen && (
          <div className="p-3 rounded-xl bg-yellow-900/20 border border-yellow-800/30 text-center -mt-2 mb-2">
            <span className="text-yellow-400 text-sm">🌙 Market Closed — Next open: 9:30 AM ET</span>
          </div>
        )}

        {/* ═══ SECTION 2: QUICK STATS BAR ═══ */}
        <section className="grid grid-cols-2 lg:grid-cols-4 gap-4 -mt-6 relative z-10 stagger-enter">
          {/* Total P&L card */}
          <div className="glass hover-glow p-5">
            <p className="text-xs text-gray-400 uppercase tracking-wider mb-2">Total P&L</p>
            <div className="flex items-baseline gap-2">
              <span className={`text-2xl font-bold ${pnlPositive ? 'text-[#00ff88]' : 'text-[#ff4444]'}`}>
                {pnlPositive ? '+' : ''}{fmt(animPnl)}
              </span>
              <span className={`text-lg ${pnlPositive ? 'text-[#00ff88]' : 'text-[#ff4444]'}`}>
                {pnlPositive ? '↑' : '↓'}
              </span>
            </div>
          </div>

          {/* Win Rate card */}
          <div className="glass hover-glow p-5">
            <p className="text-xs text-gray-400 uppercase tracking-wider mb-2">Win Rate</p>
            <div className="flex items-center gap-3">
              <Ring pct={animWinRate} size={48} stroke={4} />
              <span className="text-2xl font-bold text-white">{animWinRate.toFixed(1)}%</span>
            </div>
          </div>

          {/* Positions card */}
          <div className="glass hover-glow p-5">
            <p className="text-xs text-gray-400 uppercase tracking-wider mb-2">Positions</p>
            <div className="flex items-baseline gap-2">
              <span className="text-2xl font-bold text-white">{posCount}</span>
              <span className="text-sm">
                <span className="text-[#00ff88]">{greenCount}↑</span>
                {' / '}
                <span className="text-[#ff4444]">{redCount}↓</span>
              </span>
            </div>
          </div>

          {/* AI Status card */}
          <div className="glass hover-glow p-5">
            <p className="text-xs text-gray-400 uppercase tracking-wider mb-2">AI Status</p>
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <span className="text-green-400">✅</span>
                <span className="text-sm text-gray-300">GPT-4o</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-green-400">✅</span>
                <span className="text-sm text-gray-300">Claude</span>
              </div>
            </div>
          </div>
        </section>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* ═══ SECTION 3: LIVE POSITIONS ═══ */}
          <section className="lg:col-span-2 glass p-0 overflow-hidden">
            <div className="px-5 py-4 border-b border-white/5 flex items-center justify-between">
              <h2 className="text-sm font-semibold uppercase tracking-wider text-gray-300">Live Positions</h2>
              <span className="text-xs text-gray-500">{posCount} open</span>
            </div>

            {positions.length === 0 ? (
              <div className="p-8 text-center text-gray-500">No open positions</div>
            ) : (
              <div className="divide-y divide-white/5 stagger-enter">
                {positions.map((pos: any) => {
                  const sym = pos.symbol || pos.ticker || '??'
                  const pnl = pos.unrealized_pnl ?? pos.pnl ?? 0
                  const pnlPct = pos.unrealized_pnl_pct ?? pos.pnl_pct ?? 0
                  const price = pos.current_price ?? pos.price ?? 0
                  const qty = pos.qty ?? pos.quantity ?? 0
                  const verdict = pos.ai_verdict ?? pos.verdict ?? ''
                  const hasStop = pos.trailing_stop != null || pos.stop_loss != null
                  const isGreen = pnl >= 0
                  const expanded = expandedRow === sym

                  return (
                    <div key={sym}>
                      <div
                        className="position-row flex items-center px-5 py-3.5 cursor-pointer"
                        style={{ borderLeft: `3px solid ${isGreen ? '#00ff88' : '#ff4444'}` }}
                        onClick={() => setExpandedRow(expanded ? null : sym)}
                      >
                        {/* Symbol badge */}
                        <div className="w-9 h-9 rounded-full flex items-center justify-center text-white font-bold text-xs mr-3 flex-shrink-0"
                          style={{ backgroundColor: stockColor(sym) }}>
                          {sym.charAt(0)}
                        </div>

                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="font-semibold text-white">{sym}</span>
                            {hasStop && <span title="Protected" className="text-[#00aaff] text-xs">🛡️</span>}
                            {verdict && (
                              <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium uppercase tracking-wider ${
                                verdict.toLowerCase().includes('buy') ? 'bg-[#00ff88]/15 text-[#00ff88]' :
                                verdict.toLowerCase().includes('sell') ? 'bg-[#ff4444]/15 text-[#ff4444]' :
                                'bg-white/10 text-gray-400'
                              }`}>{verdict}</span>
                            )}
                          </div>
                          <span className="text-xs text-gray-500">{qty} shares @ ${fmt(price)}</span>
                        </div>

                        <div className="text-right">
                          <p className={`font-semibold ${isGreen ? 'text-[#00ff88]' : 'text-[#ff4444]'}`}>
                            {isGreen ? '+' : ''}{fmt(pnl)}
                          </p>
                          <p className={`text-xs ${isGreen ? 'text-[#00ff88]/70' : 'text-[#ff4444]/70'}`}>
                            {pct(pnlPct)}
                          </p>
                        </div>

                        <span className={`ml-3 text-gray-500 text-xs transition-transform duration-200 ${expanded ? 'rotate-180' : ''}`}>▼</span>
                      </div>

                      {/* Expanded detail */}
                      {expanded && (
                        <div className="px-5 py-4 bg-white/[0.02] border-t border-white/5 animate-fade-in text-xs space-y-2">
                          {pos.ai_reasoning && <p className="text-gray-400"><span className="text-gray-500 font-medium">AI Reasoning:</span> {pos.ai_reasoning}</p>}
                          {pos.trailing_stop && <p className="text-gray-400"><span className="text-gray-500 font-medium">Trailing Stop:</span> ${fmt(pos.trailing_stop)}</p>}
                          {pos.indicators && <p className="text-gray-400"><span className="text-gray-500 font-medium">Indicators:</span> {JSON.stringify(pos.indicators)}</p>}
                          {pos.sentiment && <p className="text-gray-400"><span className="text-gray-500 font-medium">Sentiment:</span> {pos.sentiment}</p>}
                          {!pos.ai_reasoning && !pos.trailing_stop && <p className="text-gray-500 italic">No additional details</p>}
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            )}
          </section>

          {/* ═══ SECTION 4: AI COMMAND CENTER ═══ */}
          <section className="glass p-0 overflow-hidden flex flex-col">
            <div className="px-5 py-4 border-b border-white/5">
              <h2 className="text-sm font-semibold uppercase tracking-wider text-gray-300">AI Command Center</h2>
              <p className="text-xs text-gray-500 mt-0.5">
                Last scan: {verdicts.length > 0 ? ago(verdicts[0]?.timestamp || verdicts[0]?.created_at || '') : '—'}
              </p>
            </div>

            <div className="flex-1 overflow-y-auto scrollbar-thin p-4 space-y-3 stagger-enter" style={{ maxHeight: 420 }}>
              {verdicts.length === 0 && <p className="text-gray-500 text-sm text-center py-8">No recent verdicts</p>}
              {verdicts.slice(0, 8).map((v: any, i: number) => {
                const action = (v.verdict || v.action || 'hold').toLowerCase()
                const conf = v.confidence ?? v.score ?? 50
                const isBuy = action.includes('buy')
                const isSell = action.includes('sell')
                const accent = isBuy ? '#00ff88' : isSell ? '#ff4444' : '#666'
                return (
                  <div key={i} className="rounded-xl p-3.5" style={{
                    background: 'rgba(255,255,255,0.03)',
                    border: `1px solid ${accent}22`,
                    boxShadow: `0 0 20px ${accent}10`,
                  }}>
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-white text-sm">{v.symbol || v.ticker || '—'}</span>
                        <span className="text-[10px] px-2 py-0.5 rounded-full font-bold uppercase tracking-wider"
                          style={{ color: accent, background: `${accent}18` }}>
                          {action}
                        </span>
                      </div>
                      <span className="text-[10px] text-gray-500 flex items-center gap-1">
                        {v.source === 'claude' || v.model?.includes('claude') ? '🟣' : '🟢'}
                        {v.source || v.model || 'AI'}
                      </span>
                    </div>
                    {/* Confidence bar */}
                    <div className="h-1.5 rounded-full bg-white/5 overflow-hidden">
                      <div className="h-full rounded-full confidence-bar-fill" style={{
                        width: `${conf}%`, backgroundColor: accent,
                      }} />
                    </div>
                    <p className="text-[10px] text-gray-500 mt-1.5">{conf}% confidence{v.reason ? ` · ${v.reason}` : ''}</p>
                  </div>
                )
              })}
            </div>
          </section>
        </div>

        {/* ═══ SECTION 5 & 6: FEED + MARKET PULSE ═══ */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

          {/* Activity Feed */}
          <section className="glass p-0 overflow-hidden">
            <div className="px-5 py-4 border-b border-white/5">
              <h2 className="text-sm font-semibold uppercase tracking-wider text-gray-300">Live Activity</h2>
            </div>
            <div ref={feedRef} className="overflow-y-auto scrollbar-thin p-4 space-y-2" style={{ maxHeight: 340 }}>
              {actions.length === 0 && <p className="text-gray-500 text-sm text-center py-6">No recent activity</p>}
              {actions.slice(0, 10).map((a: any, i: number) => {
                const icon = ACTION_ICONS[a.action_type || a.type || ''] || ACTION_ICONS.default
                return (
                  <div key={i} className="flex items-start gap-3 py-2 animate-feed-enter" style={{ animationDelay: `${i * 0.04}s` }}>
                    <span className="text-lg flex-shrink-0">{icon}</span>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-gray-200 leading-snug">
                        <span className="font-medium text-white">{a.symbol || a.ticker || ''}</span>{' '}
                        {a.description || a.message || a.action_type || a.type || ''}
                      </p>
                      <p className="text-[10px] text-gray-500 mt-0.5">{ago(a.timestamp || a.created_at || '')}</p>
                    </div>
                    {a.pnl != null && (
                      <span className={`text-xs font-semibold flex-shrink-0 ${a.pnl >= 0 ? 'text-[#00ff88]' : 'text-[#ff4444]'}`}>
                        {a.pnl >= 0 ? '+' : ''}{fmt(a.pnl)}
                      </span>
                    )}
                  </div>
                )
              })}
            </div>
          </section>

          {/* Breaking News Ticker */}
          <section className="glass p-0 overflow-hidden">
            <div className="px-5 py-4 border-b border-white/5 flex items-center justify-between">
              <h2 className="text-sm font-semibold uppercase tracking-wider text-gray-300">📡 Breaking News</h2>
              <a href="/feed" className="text-xs text-green-400 hover:text-green-300">View all →</a>
            </div>
            <div className="p-4 space-y-2 overflow-y-auto" style={{ maxHeight: 340 }}>
              {breakingNews.length === 0 && <p className="text-gray-500 text-sm text-center py-6">Loading news...</p>}
              {breakingNews.slice(0, 5).map((item: any, i: number) => (
                <div key={i} className={`flex items-center gap-2 text-xs p-2 rounded-lg ${
                  item.urgency === 'critical' ? 'bg-red-950/40 text-red-300' :
                  item.urgency === 'bullish' ? 'bg-green-950/30 text-green-300' :
                  'bg-slate-800/50 text-slate-400'
                }`}>
                  <span>{({'BREAKING':'🚨','TRUMP':'🏛️','FED':'🏦','GEOPOLITICAL':'⚔️','EARNINGS':'📊','AI':'🤖','CRYPTO':'₿'} as Record<string,string>)[item.category] || '📌'}</span>
                  <span className="flex-1 truncate">{item.headline}</span>
                </div>
              ))}
            </div>
          </section>

          {/* Market Pulse */}
          <section className="glass p-5">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-gray-300 mb-5">Market Pulse</h2>

            <div className="flex items-start justify-between">
              {/* Fear & Greed */}
              <FearGreedGauge value={fearGreed} />

              {/* Market stats */}
              <div className="space-y-4 text-right">
                <div>
                  <p className="text-xs text-gray-500 uppercase tracking-wider">SPY</p>
                  <p className={`text-lg font-bold ${spyChange >= 0 ? 'text-[#00ff88]' : 'text-[#ff4444]'}`}>
                    {pct(spyChange)}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-gray-500 uppercase tracking-wider">Regime</p>
                  <span className={`inline-block text-xs px-3 py-1 rounded-full font-medium ${
                    regime === 'bull' ? 'bg-[#00ff88]/15 text-[#00ff88]' :
                    regime === 'bear' ? 'bg-[#ff4444]/15 text-[#ff4444]' :
                    'bg-white/10 text-gray-400'
                  }`}>{regime}</span>
                </div>
                <div>
                  <p className="text-xs text-gray-500 uppercase tracking-wider">Geo Sentiment</p>
                  <p className={`text-lg font-bold ${
                    trumpSentiment > 0 ? 'text-[#00ff88]' :
                    trumpSentiment < 0 ? 'text-[#ff4444]' : 'text-gray-400'
                  }`}>{trumpSentiment > 0 ? '+' : ''}{trumpSentiment}</p>
                </div>
              </div>
            </div>
          </section>
        </div>

        {/* Footer tagline */}
        <div className="text-center py-6">
          <p className="text-xs text-gray-600">Beast Trader Terminal · AI-Powered · Real-Time</p>
        </div>
      </div>
    </div>
  )
}
