'use client'
import { useState, useRef } from 'react'

const API = 'https://api.beast-trader.com'
const API_KEY = 'beast-v3-sk-7f3a9e2b4d1c8f5e6a0b3d9c'

export default function CommandBar() {
  const [input, setInput] = useState('')
  const [output, setOutput] = useState('')
  const [preview, setPreview] = useState<any>(null)
  const [confirmToken, setConfirmToken] = useState('')
  const [loading, setLoading] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!input.trim()) return
    setLoading(true)
    setOutput('')

    // If we have a confirm token, this is step 2
    if (confirmToken) {
      try {
        const res = await fetch(`${API}/api/order`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-API-Key': API_KEY },
          body: JSON.stringify({ confirm_token: confirmToken })
        })
        const data = await res.json()
        if (data.executed) {
          setOutput(`✅ ${data.message}`)
        } else {
          setOutput(`❌ ${data.error || 'Execution failed'}`)
        }
      } catch (e) {
        setOutput('❌ Connection failed')
      }
      setConfirmToken('')
      setPreview(null)
      setInput('')
      setLoading(false)
      return
    }

    // Step 1: Parse and preview
    try {
      const res = await fetch(`${API}/api/order`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-API-Key': API_KEY },
        body: JSON.stringify({ command: input })
      })
      const data = await res.json()
      if (data.error) {
        setOutput(`❌ ${data.error}`)
      } else if (data.preview) {
        setPreview(data.preview)
        setConfirmToken(data.confirm_token)
        setOutput(`⚡ Preview: ${data.message}\n   Press ENTER to confirm or ESC to cancel`)
        setInput('CONFIRM')
      }
    } catch (e) {
      setOutput('❌ Connection failed')
    }
    setLoading(false)
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      setConfirmToken('')
      setPreview(null)
      setOutput('Cancelled')
      setInput('')
    }
  }

  return (
    <div className="flex items-center gap-3">
      <span className="text-green-400 font-mono text-sm">beast $</span>
      <form onSubmit={handleSubmit} className="flex-1 flex items-center gap-2">
        <input
          ref={inputRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="/buy NVDA 3 @210 | /sell AMD 5 | /cancel ID | /kill | /status"
          className="flex-1 bg-transparent border-none outline-none text-green-300 font-mono text-sm placeholder-slate-600"
          autoFocus
        />
        {loading && <span className="text-yellow-400 animate-pulse text-sm">⏳</span>}
      </form>
      {output && (
        <span className={`text-sm font-mono ${output.startsWith('✅') ? 'text-green-400' : output.startsWith('❌') ? 'text-red-400' : 'text-yellow-300'}`}>
          {output}
        </span>
      )}
      {/* Kill switch button */}
      <button
        onClick={async () => {
          const res = await fetch(`${API}/api/kill`, {
            method: 'POST',
            headers: { 'X-API-Key': API_KEY }
          })
          const data = await res.json()
          setOutput(data.message || 'Kill switch activated')
        }}
        className="px-2 py-1 bg-red-900/50 border border-red-700 rounded text-red-400 text-xs hover:bg-red-800 transition"
        title="Emergency: Stop all trading"
      >
        🛑 KILL
      </button>
    </div>
  )
}
