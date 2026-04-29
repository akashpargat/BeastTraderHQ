'use client'
import { useEffect, useState, useCallback } from 'react'

const API = 'https://api.beast-trader.com'

export default function Dashboard() {
  const [portfolio, setPortfolio] = useState<any>(null)
  const [actions, setActions] = useState<any[]>([])
  const [sentiment, setSentiment] = useState<any>({})
  const [intraday, setIntraday] = useState<any[]>([])
  const [system, setSystem] = useState<any>(null)
  const [lastUpdate, setLastUpdate] = useState('')
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [tick, setTick] = useState(0)

  const fetchAll = useCallback(async () => {
    setIsRefreshing(true)
    try {
      const [pRes, aRes, sRes, iRes, sysRes] = await Promise.all([
        fetch(`${API}/api/portfolio`), fetch(`${API}/api/actions?limit=20`),
        fetch(`${API}/api/sentiment`), fetch(`${API}/api/intraday`),
        fetch(`${API}/api/system`),
      ])
      setPortfolio(await pRes.json())
      setActions((await aRes.json()).actions || [])
      setSentiment(await sRes.json())
      setIntraday((await iRes.json()).data || [])
      setSystem(await sysRes.json())
      setLastUpdate(new Date().toLocaleTimeString())
      setTick(t => t + 1)
    } catch (e) { console.error('Fetch failed:', e) }
    setTimeout(() => setIsRefreshing(false), 600)
  }, [])

  useEffect(() => { fetchAll(); const i = setInterval(fetchAll, 60000); return () => clearInterval(i) }, [fetchAll])

  if (!portfolio) return (
    <div className="flex items-center justify-center min-h-[60vh]">
      <div className="text-center animate-fade-in">
        <div className="text-6xl mb-4 animate-bounce">🦍</div>
        <p className="text-slate-400 text-lg">Loading Beast Engine...</p>
        <div className="mt-4 w-48 h-1 bg-slate-700 rounded-full mx-auto overflow-hidden">
          <div className="h-full bg-green-500 rounded-full animate-loading-bar" />
        </div>
      </div>
    </div>
  )

  const greens = portfolio.positions?.filter((p: any) => p.is_green).length || 0
  const reds = (portfolio.positions?.length || 0) - greens
  const trumpData = sentiment['_trump'] || {}
  const bestStock = portfolio.positions?.[0]
  const worstStock = portfolio.positions?.[portfolio.positions.length - 1]

  return (
    <div className={`space-y-4 transition-opacity duration-500 ${isRefreshing ? 'opacity-80' : 'opacity-100'}`}>

      {/* ── HERO STATS ── */}
      <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
        <GlowCard label="Portfolio" value={`$${portfolio.equity?.toLocaleString()}`} glow="blue" />
        <GlowCard label="Day P&L" value={`${portfolio.total_pl >= 0 ? '+' : ''}$${portfolio.total_pl?.toFixed(2)}`}
          glow={portfolio.total_pl >= 0 ? 'green' : 'red'} />
        <GlowCard label="Positions" value={`${portfolio.positions_count}`} sub={`🟢${greens} 🔴${reds}`} />
        <GlowCard label="Orders" value={`${portfolio.orders_count}`} />
        <GlowCard label="Trump" value={`${trumpData.score >= 0 ? '+' : ''}${trumpData.score || 0}/5`}
          glow={(trumpData.score || 0) >= 0 ? 'green' : 'red'} />
        <GlowCard label="Updated" value={lastUpdate} sub="⟳ 60s" />
      </div>

      {/* ── SYSTEM STATUS ── */}
      {system && (
        <div className="flex gap-2 flex-wrap animate-fade-in">
          <PulsingBadge label="AI Brain" ok={system.ai?.status === 'online'} />
          <PulsingBadge label="TradingView" ok={system.tv?.status === 'connected'} />
          <PulsingBadge label="Discord Bot" ok={system.bot?.status === 'running'} />
          <PulsingBadge label="API" ok={true} />
          {isRefreshing && <span className="px-2.5 py-1 rounded-full text-[10px] bg-blue-500/15 text-blue-400 border border-blue-500/30 animate-pulse">⟳ Refreshing...</span>}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* ── LEFT COLUMN (2/3) ── */}
        <div className="lg:col-span-2 space-y-4">

          {/* P&L CHART */}
          <Card title="📈 Intraday Equity" animate>
            {intraday.length > 1 ? (
              <>
                <div className="h-36 flex items-end gap-px">
                  {intraday.slice(-100).map((e: any, i: number) => {
                    const vals = intraday.map((x: any) => x.equity)
                    const min = Math.min(...vals); const max = Math.max(...vals)
                    const h = ((e.equity - min) / (max - min || 1)) * 100
                    return (
                      <div key={i} className="flex-1 min-w-[1px] group relative"
                        title={`$${e.equity?.toLocaleString()}`}>
                        <div className={`rounded-t transition-all duration-300 group-hover:brightness-150 ${e.total_pl >= 0 ? 'bg-gradient-to-t from-green-600 to-green-400' : 'bg-gradient-to-t from-red-600 to-red-400'}`}
                          style={{ height: `${Math.max(4, h)}%` }} />
                      </div>
                    )
                  })}
                </div>
                <div className="flex justify-between text-[10px] text-slate-500 mt-1 px-1">
                  <span>{intraday[0]?.timestamp?.slice(11, 16)}</span>
                  <span className="text-slate-400">
                    ${Math.min(...intraday.map((x: any) => x.equity)).toLocaleString()} — ${Math.max(...intraday.map((x: any) => x.equity)).toLocaleString()}
                  </span>
                  <span>{intraday[intraday.length - 1]?.timestamp?.slice(11, 16)}</span>
                </div>
              </>
            ) : (
              <div className="h-36 flex items-center justify-center text-slate-500 text-sm">
                Chart populates during market hours
              </div>
            )}
          </Card>

          {/* POSITIONS TABLE */}
          <Card title="💼 Live Positions" animate>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-slate-500 text-[10px] uppercase tracking-wider border-b border-slate-700">
                    <th className="text-left py-2 px-2">Stock</th>
                    <th className="text-right py-2 px-2">Price</th>
                    <th className="text-right py-2 px-2">P&L</th>
                    <th className="text-right py-2 px-2">%</th>
                    <th className="text-right py-2 px-2">Value</th>
                    <th className="text-center py-2 px-2">Sentiment</th>
                    <th className="text-center py-2 px-2">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {portfolio.positions?.map((p: any, idx: number) => {
                    const s = sentiment[p.symbol] || {}
                    return (
                      <tr key={p.symbol}
                        className="border-b border-slate-700/20 hover:bg-slate-700/40 transition-colors duration-200"
                        style={{ animationDelay: `${idx * 50}ms` }}>
                        <td className="py-2 px-2">
                          <div className="flex items-center gap-1.5">
                            <span className={`text-lg ${p.is_green ? 'text-green-400' : 'text-red-400'}`}>
                              {p.is_green ? '▲' : '▼'}
                            </span>
                            <div>
                              <span className="font-mono font-bold text-white">{p.symbol}</span>
                              <span className="text-slate-500 text-[10px] ml-1">{p.qty}x @ ${p.avg_entry?.toFixed(2)}</span>
                            </div>
                          </div>
                        </td>
                        <td className="text-right py-2 px-2 font-mono">${p.current_price?.toFixed(2)}</td>
                        <td className={`text-right py-2 px-2 font-bold ${p.is_green ? 'text-green-400' : 'text-red-400'}`}>
                          {p.unrealized_pl >= 0 ? '+' : ''}${p.unrealized_pl?.toFixed(2)}
                        </td>
                        <td className="text-right py-2 px-2">
                          <span className={`px-1.5 py-0.5 rounded text-xs font-mono ${p.is_green ? 'bg-green-500/10 text-green-400' : 'bg-red-500/10 text-red-400'}`}>
                            {p.pct >= 0 ? '+' : ''}{p.pct?.toFixed(1)}%
                          </span>
                        </td>
                        <td className="text-right py-2 px-2 text-slate-400 text-xs">${p.market_value?.toLocaleString()}</td>
                        <td className="text-center py-2 px-2">
                          <SentimentDots y={s.yahoo || 0} r={s.reddit || 0} a={s.analyst || 0} />
                        </td>
                        <td className="text-center py-2 px-2">
                          <ActionPill pct={p.pct} />
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </Card>

          {/* SENTIMENT HEATMAP */}
          <Card title="📰 Sentiment Heatmap" animate>
            <div className="grid grid-cols-5 gap-1 text-xs">
              <div className="text-slate-500 font-bold p-1">Stock</div>
              <div className="text-slate-500 text-center p-1">Yahoo</div>
              <div className="text-slate-500 text-center p-1">Reddit</div>
              <div className="text-slate-500 text-center p-1">Analyst</div>
              <div className="text-slate-500 text-center p-1 font-bold">Total</div>
              {portfolio.positions?.map((p: any) => {
                const s = sentiment[p.symbol] || {}
                return [
                  <div key={`${p.symbol}-n`} className="font-mono font-bold p-1 flex items-center">
                    <span className={`w-1.5 h-1.5 rounded-full mr-1.5 ${p.is_green ? 'bg-green-400' : 'bg-red-400'}`} />
                    {p.symbol}
                  </div>,
                  <HeatCell key={`${p.symbol}-y`} v={s.yahoo || 0} />,
                  <HeatCell key={`${p.symbol}-r`} v={s.reddit || 0} />,
                  <HeatCell key={`${p.symbol}-a`} v={s.analyst || 0} />,
                  <HeatCell key={`${p.symbol}-t`} v={s.total || 0} bold />,
                ]
              })}
            </div>
            {trumpData.headlines?.length > 0 && (
              <div className="mt-3 pt-3 border-t border-slate-700/50">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-xs">🏛️</span>
                  <span className="text-xs text-slate-400">Trump/Geo:</span>
                  <span className={`text-xs font-bold ${(trumpData.score || 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                    {trumpData.score >= 0 ? '+' : ''}{trumpData.score}/5
                  </span>
                </div>
                {trumpData.headlines.slice(0, 2).map((h: string, i: number) => (
                  <p key={i} className="text-[10px] text-slate-500 truncate pl-5">• {h}</p>
                ))}
              </div>
            )}
          </Card>
        </div>

        {/* ── RIGHT COLUMN (1/3) ── */}
        <div className="space-y-4">

          {/* LIVE ACTION FEED */}
          <Card title="⚡ Live Feed" animate>
            <div className="space-y-1 max-h-[420px] overflow-y-auto scrollbar-thin">
              {actions.length === 0 ? (
                <div className="text-center py-8">
                  <div className="text-2xl mb-2 animate-pulse">📡</div>
                  <p className="text-slate-500 text-xs">Waiting for first scan...</p>
                </div>
              ) : actions.map((a: any, i: number) => (
                <div key={i} className="flex gap-2 py-1.5 border-b border-slate-700/20 hover:bg-slate-700/20 transition-colors rounded px-1"
                  style={{ animationDelay: `${i * 30}ms` }}>
                  <span className="text-[9px] text-slate-600 w-12 shrink-0 font-mono mt-0.5">
                    {a.timestamp?.slice(11, 19)}
                  </span>
                  <div className="min-w-0">
                    <ActionTypeBadge type={a.type} />
                    <span className="text-[11px] text-slate-300 ml-1">{a.title}</span>
                    {a.detail && <p className="text-[9px] text-slate-600 mt-0.5 truncate">{a.detail}</p>}
                  </div>
                </div>
              ))}
            </div>
          </Card>

          {/* OPEN ORDERS */}
          {portfolio.open_orders?.length > 0 && (
            <Card title={`📋 Orders (${portfolio.orders_count})`} animate>
              <div className="space-y-1">
                {portfolio.open_orders.slice(0, 8).map((o: any, i: number) => (
                  <div key={i} className="flex justify-between text-xs py-1.5 border-b border-slate-700/20 hover:bg-slate-700/20 transition-colors rounded px-1">
                    <span className={`font-mono font-bold ${o.side === 'buy' ? 'text-green-400' : 'text-red-400'}`}>
                      {o.side === 'buy' ? '🟢' : '🔴'} {o.symbol}
                    </span>
                    <span className="text-slate-400">x{o.qty} @ ${o.limit_price}</span>
                  </div>
                ))}
              </div>
            </Card>
          )}

          {/* QUICK STATS */}
          <Card title="📊 Portfolio Stats" animate>
            <div className="space-y-2.5 text-xs">
              <StatRow label="Buying Power" value={`$${portfolio.buying_power?.toLocaleString()}`} />
              <StatRow label="Cash" value={`$${portfolio.cash?.toLocaleString()}`} />
              <div className="border-t border-slate-700/30 pt-2" />
              <StatRow label="Best" value={`${bestStock?.symbol} +${bestStock?.pct?.toFixed(1)}%`} color="green" />
              <StatRow label="Worst" value={`${worstStock?.symbol} ${worstStock?.pct?.toFixed(1)}%`} color="red" />
              <div className="border-t border-slate-700/30 pt-2" />
              <StatRow label="Winners" value={`${greens} stocks`} color="green" />
              <StatRow label="Losers" value={`${reds} stocks`} color="red" />
            </div>
          </Card>
        </div>
      </div>
    </div>
  )
}

/* ── COMPONENTS ── */

function Card({ title, children, animate }: { title: string; children: React.ReactNode; animate?: boolean }) {
  return (
    <div className={`bg-gradient-to-br from-slate-800 to-slate-800/80 rounded-xl p-4 border border-slate-700/60 shadow-lg shadow-black/20 ${animate ? 'animate-fade-in' : ''}`}>
      <h2 className="text-sm font-semibold text-slate-400 mb-3 flex items-center gap-2">
        {title}
      </h2>
      {children}
    </div>
  )
}

function GlowCard({ label, value, sub, glow }: { label: string; value: string; sub?: string; glow?: string }) {
  const glowMap: Record<string, string> = {
    green: 'shadow-green-500/10 border-green-500/20',
    red: 'shadow-red-500/10 border-red-500/20',
    blue: 'shadow-blue-500/10 border-blue-500/20',
  }
  const textMap: Record<string, string> = {
    green: 'text-green-400', red: 'text-red-400', blue: 'text-blue-400',
  }
  return (
    <div className={`bg-slate-800 rounded-xl p-3 border border-slate-700 text-center shadow-lg transition-all duration-300 hover:scale-[1.02] hover:shadow-xl ${glow ? glowMap[glow] || '' : ''}`}>
      <p className="text-slate-500 text-[10px] uppercase tracking-wider">{label}</p>
      <p className={`text-lg font-bold ${glow ? textMap[glow] || 'text-white' : 'text-white'}`}>{value}</p>
      {sub && <p className="text-slate-600 text-[10px]">{sub}</p>}
    </div>
  )
}

function PulsingBadge({ label, ok }: { label: string; ok: boolean }) {
  return (
    <span className={`px-2.5 py-1 rounded-full text-[10px] font-medium transition-all duration-300 ${ok ? 'bg-green-500/10 text-green-400 border border-green-500/25' : 'bg-red-500/10 text-red-400 border border-red-500/25'}`}>
      <span className={`inline-block w-1.5 h-1.5 rounded-full mr-1 ${ok ? 'bg-green-400 animate-pulse' : 'bg-red-400'}`} />
      {label}
    </span>
  )
}

function SentimentDots({ y, r, a }: { y: number; r: number; a: number }) {
  const dot = (v: number, label: string) => (
    <span title={`${label}: ${v >= 0 ? '+' : ''}${v}`}
      className={`inline-block w-2 h-2 rounded-full mx-px transition-colors ${v >= 2 ? 'bg-green-400' : v <= -2 ? 'bg-red-400' : 'bg-slate-600'}`} />
  )
  return <div className="flex justify-center gap-0.5">{dot(y, 'Yahoo')}{dot(r, 'Reddit')}{dot(a, 'Analyst')}</div>
}

function HeatCell({ v, bold }: { v: number; bold?: boolean }) {
  const bg = v >= 3 ? 'bg-green-500/40' : v >= 1 ? 'bg-green-500/15' : v <= -3 ? 'bg-red-500/40' : v <= -1 ? 'bg-red-500/15' : 'bg-slate-700/20'
  return (
    <div className={`${bg} rounded p-1 text-center transition-all duration-300 hover:brightness-125 ${bold ? 'font-bold' : ''} ${v > 0 ? 'text-green-400' : v < 0 ? 'text-red-400' : 'text-slate-500'}`}>
      {v >= 0 ? '+' : ''}{v}
    </div>
  )
}

function ActionPill({ pct }: { pct: number }) {
  const configs: Record<string, [string, string]> = {
    runner: ['RUNNER', 'bg-purple-500/20 text-purple-400 border-purple-500/30'],
    scalp: ['SCALP', 'bg-green-500/15 text-green-400 border-green-500/25'],
    hold_g: ['HOLD', 'bg-slate-600/20 text-slate-300 border-slate-600/30'],
    hold_y: ['HOLD', 'bg-yellow-500/15 text-yellow-400 border-yellow-500/25'],
    deep: ['DEEP RED', 'bg-red-500/15 text-red-400 border-red-500/25'],
  }
  const key = pct >= 5 ? 'runner' : pct >= 2 ? 'scalp' : pct >= 0 ? 'hold_g' : pct > -5 ? 'hold_y' : 'deep'
  const [text, cls] = configs[key]
  return <span className={`px-1.5 py-0.5 rounded-full text-[9px] font-medium border ${cls}`}>{text}</span>
}

function ActionTypeBadge({ type }: { type: string }) {
  const map: Record<string, string> = {
    TRADE: 'bg-green-500/15 text-green-400',
    SCAN: 'bg-blue-500/15 text-blue-400',
    DROP: 'bg-red-500/15 text-red-400',
    KILL_SWITCH: 'bg-red-500/30 text-red-300',
  }
  return <span className={`text-[9px] px-1.5 py-0.5 rounded ${map[type] || 'bg-slate-600/20 text-slate-400'}`}>{type}</span>
}

function StatRow({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="flex justify-between items-center">
      <span className="text-slate-500">{label}</span>
      <span className={color === 'green' ? 'text-green-400' : color === 'red' ? 'text-red-400' : 'text-slate-300'}>{value}</span>
    </div>
  )
}
