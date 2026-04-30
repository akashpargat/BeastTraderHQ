'use client'
import { useEffect, useState, useCallback } from 'react'
import { authFetch } from '../../lib/api'

export default function BlueChipsPage() {
  const [chips, setChips] = useState<any[]>([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [adding, setAdding] = useState(false)
  const [form, setForm] = useState({ symbol: '', name: '', sector: 'tech', tier: 2, max_loss_pct: -10, notes: '' })

  const fetchData = useCallback(async () => {
    try {
      const res = await authFetch('/api/v4/blue-chips')
      if (res.ok) { setChips(await res.json()); setError('') }
      else setError(`API error: ${res.status}`)
    } catch (e: any) { setError(e.message) }
    setLoading(false)
  }, [])

  useEffect(() => { fetchData() }, [fetchData])

  const handleAdd = async () => {
    if (!form.symbol) return
    try {
      const res = await authFetch('/api/v4/blue-chips', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form)
      })
      if (res.ok) { setAdding(false); setForm({ symbol: '', name: '', sector: 'tech', tier: 2, max_loss_pct: -10, notes: '' }); fetchData() }
    } catch (e: any) { setError(e.message) }
  }

  const handleDelete = async (symbol: string) => {
    if (!confirm(`Remove ${symbol} from blue chips?`)) return
    try {
      await authFetch(`/api/v4/blue-chips/${symbol}`, { method: 'DELETE' })
      fetchData()
    } catch (e: any) { setError(e.message) }
  }

  if (loading) return <div className="flex items-center justify-center min-h-[50vh]"><div className="text-4xl animate-bounce">🦍</div></div>

  const tier1 = chips.filter((c: any) => c?.tier === 1)
  const tier2 = chips.filter((c: any) => c?.tier === 2)

  return (
    <div className="fade-in space-y-6">
      <div className="flex justify-between items-center">
        <h1 className="text-2xl font-bold">💎 Blue Chips ({chips.length})</h1>
        <button onClick={() => setAdding(!adding)} className="px-4 py-2 bg-[#00ff88]/20 text-[#00ff88] rounded-lg hover:bg-[#00ff88]/30 transition">
          {adding ? 'Cancel' : '+ Add Stock'}
        </button>
      </div>
      {error && <div className="glass p-3 text-red-400 text-sm">{error}</div>}

      {adding && (
        <div className="glass p-4 space-y-3">
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            <input placeholder="Symbol (e.g. HOOD)" value={form.symbol} onChange={e => setForm({...form, symbol: e.target.value.toUpperCase()})} className="bg-white/5 border border-white/10 rounded px-3 py-2 text-white" />
            <input placeholder="Name" value={form.name} onChange={e => setForm({...form, name: e.target.value})} className="bg-white/5 border border-white/10 rounded px-3 py-2 text-white" />
            <select value={form.sector} onChange={e => setForm({...form, sector: e.target.value})} className="bg-white/5 border border-white/10 rounded px-3 py-2 text-white">
              {['tech','semi','finance','consumer','health','energy','defense','media','auto','fintech'].map(s => <option key={s} value={s}>{s}</option>)}
            </select>
            <select value={form.tier} onChange={e => setForm({...form, tier: Number(e.target.value)})} className="bg-white/5 border border-white/10 rounded px-3 py-2 text-white">
              <option value={1}>Tier 1 — Never sell at loss</option>
              <option value={2}>Tier 2 — Cut at max loss</option>
            </select>
            <input type="number" placeholder="Max loss %" value={form.max_loss_pct} onChange={e => setForm({...form, max_loss_pct: Number(e.target.value)})} className="bg-white/5 border border-white/10 rounded px-3 py-2 text-white" />
            <button onClick={handleAdd} className="px-4 py-2 bg-[#00ff88] text-black font-bold rounded hover:bg-[#00ff88]/80 transition">Save</button>
          </div>
        </div>
      )}

      <div className="glass p-4">
        <h2 className="text-lg font-semibold mb-3 text-yellow-400">👑 Tier 1 — Never Sell At Loss ({tier1.length})</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-2">
          {tier1.map((c: any) => (
            <div key={c.symbol} className="glass p-3 text-center group relative">
              <div className="font-mono font-bold text-lg">{c.symbol}</div>
              <div className="text-xs text-gray-400">{c.name || c.sector}</div>
              <div className="text-xs text-yellow-400/60">{c.sector}</div>
              <button onClick={() => handleDelete(c.symbol)} className="absolute top-1 right-1 opacity-0 group-hover:opacity-100 text-red-400 text-xs transition">✕</button>
            </div>
          ))}
        </div>
      </div>

      <div className="glass p-4">
        <h2 className="text-lg font-semibold mb-3 text-blue-400">🛡️ Tier 2 — Cut At Max Loss ({tier2.length})</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead><tr className="text-gray-400 border-b border-white/10">
              <th className="text-left py-2 px-3">Symbol</th>
              <th className="text-left py-2 px-3">Name</th>
              <th className="text-left py-2 px-3">Sector</th>
              <th className="text-right py-2 px-3">Max Loss</th>
              <th className="text-right py-2 px-3">Notes</th>
              <th className="text-right py-2 px-3"></th>
            </tr></thead>
            <tbody>
              {tier2.map((c: any) => (
                <tr key={c.symbol} className="border-b border-white/5 hover:bg-white/5">
                  <td className="py-2 px-3 font-mono font-bold">{c.symbol}</td>
                  <td className="py-2 px-3 text-gray-300">{c.name || '—'}</td>
                  <td className="py-2 px-3 text-gray-400">{c.sector || '—'}</td>
                  <td className="py-2 px-3 text-right text-red-400">{c.max_loss_pct}%</td>
                  <td className="py-2 px-3 text-right text-gray-500 text-xs">{(c.notes || '').slice(0, 30)}</td>
                  <td className="py-2 px-3 text-right">
                    <button onClick={() => handleDelete(c.symbol)} className="text-red-400 hover:text-red-300 text-xs">Remove</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
