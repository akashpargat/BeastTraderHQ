'use client'
import { useEffect, useState, useCallback, useMemo } from 'react'
import { authFetch } from '@/lib/api'

export default function CongressPage() {
  const [data, setData] = useState<any>(null)
  const [portfolio, setPortfolio] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [partyFilter, setPartyFilter] = useState<string>('all')
  const [sideFilter, setSideFilter] = useState<string>('all')
  const [dateRange, setDateRange] = useState<number>(30)

  const fetchData = useCallback(async () => {
    try {
      const [cRes, pRes] = await Promise.all([
        authFetch('/api/v5/congress').catch(() => null),
        authFetch('/api/portfolio').catch(() => null),
      ])
      if (cRes?.ok) setData(await cRes.json())
      if (pRes?.ok) setPortfolio(await pRes.json())
      setError('')
    } catch (e: any) {
      setError(e.message || 'Failed to load congress data')
    }
    setLoading(false)
  }, [])

  useEffect(() => {
    fetchData()
    const i = setInterval(fetchData, 300000) // 5 minutes
    return () => clearInterval(i)
  }, [fetchData])

  const heldSymbols = useMemo(() => {
    const syms = new Set<string>()
    ;(portfolio?.positions || []).forEach((p: any) => syms.add(p.symbol?.toUpperCase()))
    return syms
  }, [portfolio])

  const trades = useMemo(() => {
    const raw = data?.trades || data?.transactions || []
    const cutoff = new Date()
    cutoff.setDate(cutoff.getDate() - dateRange)

    return raw.filter((t: any) => {
      if (partyFilter !== 'all' && (t.party ?? '').toLowerCase() !== partyFilter) return false
      if (sideFilter !== 'all' && (t.type ?? t.side ?? '').toLowerCase() !== sideFilter) return false
      if (t.date || t.transaction_date) {
        const d = new Date(t.date || t.transaction_date)
        if (d < cutoff) return false
      }
      return true
    })
  }, [data, partyFilter, sideFilter, dateRange])

  if (loading) return <div className="flex items-center justify-center min-h-[50vh]"><div className="text-4xl animate-bounce">🏛️</div></div>
  if (error && !data) return <div className="bg-gray-800 rounded-lg p-6 text-center text-red-400">{error}</div>

  return (
    <div className="space-y-6 fade-in">
      <h1 className="text-2xl font-bold text-white">🏛️ Congressional Trades Tracker</h1>

      {/* Filters */}
      <div className="bg-gray-800 rounded-lg p-4 shadow-lg flex flex-wrap gap-4 items-center">
        <div>
          <label className="text-xs text-gray-400 block mb-1">Party</label>
          <select value={partyFilter} onChange={e => setPartyFilter(e.target.value)}
            className="bg-gray-700 text-white text-sm rounded px-3 py-1.5 border border-gray-600">
            <option value="all">All Parties</option>
            <option value="democrat">Democrat</option>
            <option value="republican">Republican</option>
          </select>
        </div>
        <div>
          <label className="text-xs text-gray-400 block mb-1">Side</label>
          <select value={sideFilter} onChange={e => setSideFilter(e.target.value)}
            className="bg-gray-700 text-white text-sm rounded px-3 py-1.5 border border-gray-600">
            <option value="all">Buy & Sell</option>
            <option value="buy">Buy</option>
            <option value="sell">Sell</option>
          </select>
        </div>
        <div>
          <label className="text-xs text-gray-400 block mb-1">Date Range</label>
          <select value={dateRange} onChange={e => setDateRange(Number(e.target.value))}
            className="bg-gray-700 text-white text-sm rounded px-3 py-1.5 border border-gray-600">
            <option value={7}>Last 7 days</option>
            <option value={30}>Last 30 days</option>
            <option value={90}>Last 90 days</option>
            <option value={365}>Last year</option>
          </select>
        </div>
        <div className="ml-auto text-sm text-gray-400">
          {trades.length} trades found
        </div>
      </div>

      {/* Trades Table */}
      <div className="bg-gray-800 rounded-lg p-4 shadow-lg">
        {trades.length === 0 ? (
          <div className="text-gray-500 text-center py-8">No congressional trades match your filters</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-gray-400 border-b border-white/10">
                  <th className="text-left py-2 px-3">Politician</th>
                  <th className="text-left py-2 px-3">Party</th>
                  <th className="text-left py-2 px-3">Ticker</th>
                  <th className="text-center py-2 px-3">Side</th>
                  <th className="text-right py-2 px-3">Size</th>
                  <th className="text-right py-2 px-3">Date</th>
                  <th className="text-right py-2 px-3">Filed</th>
                </tr>
              </thead>
              <tbody>
                {trades.map((t: any, i: number) => {
                  const party = (t.party ?? '').toLowerCase()
                  const side = (t.type ?? t.side ?? '').toLowerCase()
                  const ticker = (t.ticker ?? t.symbol ?? '').toUpperCase()
                  const isHeld = heldSymbols.has(ticker)
                  return (
                    <tr key={i} className={`border-b border-white/5 hover:bg-white/5 transition ${isHeld ? 'bg-yellow-900/20' : ''}`}>
                      <td className="py-2 px-3 text-white font-medium">
                        {t.politician ?? t.name ?? '—'}
                        {isHeld && <span className="ml-2 text-xs bg-yellow-800/60 text-yellow-300 px-1.5 py-0.5 rounded">HELD</span>}
                      </td>
                      <td className="py-2 px-3">
                        <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                          party === 'democrat' ? 'bg-blue-900/40 text-blue-400' :
                          party === 'republican' ? 'bg-red-900/40 text-red-400' :
                          'bg-gray-700 text-gray-400'
                        }`}>
                          {party === 'democrat' ? 'D' : party === 'republican' ? 'R' : t.party ?? '—'}
                        </span>
                      </td>
                      <td className="py-2 px-3 font-mono font-semibold text-white">{ticker || '—'}</td>
                      <td className="py-2 px-3 text-center">
                        <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                          side === 'buy' || side === 'purchase' ? 'bg-green-900/40 text-green-400' : 'bg-red-900/40 text-red-400'
                        }`}>
                          {side === 'buy' || side === 'purchase' ? 'BUY' : 'SELL'}
                        </span>
                      </td>
                      <td className="py-2 px-3 text-right text-gray-300">{t.size ?? t.amount ?? '—'}</td>
                      <td className="py-2 px-3 text-right text-gray-400">
                        {t.date || t.transaction_date ? new Date(t.date || t.transaction_date).toLocaleDateString() : '—'}
                      </td>
                      <td className="py-2 px-3 text-right text-gray-500 text-xs">
                        {t.filed_date || t.disclosure_date ? new Date(t.filed_date || t.disclosure_date).toLocaleDateString() : '—'}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
