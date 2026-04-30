'use client'
import { useEffect, useState, useCallback } from 'react'
import { authFetch } from '../../lib/api'

export default function NotificationsPage() {
  const [data, setData] = useState<any>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  const fetchData = useCallback(async () => {
    try {
      const res = await authFetch('/api/v4/notifications?unread=false&limit=50')
      if (res.ok) { setData(await res.json()); setError('') }
      else setError(`API error: ${res.status}`)
    } catch (e: any) { setError(e.message) }
    setLoading(false)
  }, [])

  useEffect(() => { fetchData(); const i = setInterval(fetchData, 15000); return () => clearInterval(i) }, [fetchData])

  const markAllRead = async () => {
    try {
      await authFetch('/api/v4/notifications/read', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({})
      })
      fetchData()
    } catch (e: any) { setError(e.message) }
  }

  if (loading) return <div className="flex items-center justify-center min-h-[50vh]"><div className="text-4xl animate-bounce">🦍</div></div>

  const notifications = data?.notifications || []
  const unread = data?.unread_count ?? 0

  const severityColor: Record<string, string> = {
    success: 'border-l-[#00ff88] bg-[#00ff88]/5',
    warning: 'border-l-yellow-400 bg-yellow-400/5',
    error: 'border-l-[#ff4444] bg-[#ff4444]/5',
    info: 'border-l-blue-400 bg-blue-400/5',
  }

  const severityIcon: Record<string, string> = {
    success: '✅', warning: '⚠️', error: '❌', info: 'ℹ️',
  }

  return (
    <div className="fade-in space-y-6">
      <div className="flex justify-between items-center">
        <h1 className="text-2xl font-bold">🔔 Notifications ({unread} unread)</h1>
        {unread > 0 && (
          <button onClick={markAllRead} className="px-4 py-2 bg-white/10 text-gray-300 rounded-lg hover:bg-white/20 transition text-sm">
            Mark all read
          </button>
        )}
      </div>

      {notifications.length === 0 ? (
        <div className="glass p-12 text-center text-gray-500"><div className="text-4xl mb-2">🔕</div>No notifications</div>
      ) : (
        <div className="space-y-2">
          {notifications.map((n: any, i: number) => (
            <div key={i} className={`glass p-4 border-l-4 ${severityColor[n?.severity] || severityColor.info} ${!n?.is_read ? 'ring-1 ring-white/10' : 'opacity-70'}`}>
              <div className="flex items-center justify-between mb-1">
                <div className="flex items-center gap-2">
                  <span>{severityIcon[n?.severity] || 'ℹ️'}</span>
                  <span className="font-semibold">{n?.title || '—'}</span>
                  {n?.symbol && <span className="font-mono text-xs bg-white/10 px-2 py-0.5 rounded">{n.symbol}</span>}
                </div>
                <span className="text-xs text-gray-500">{n?.created_at ? new Date(n.created_at).toLocaleString() : ''}</span>
              </div>
              {n?.body && <p className="text-sm text-gray-400 whitespace-pre-line">{n.body}</p>}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
