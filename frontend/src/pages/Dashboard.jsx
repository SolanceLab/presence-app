import { useState, useEffect } from 'react'
import { apiFetch } from '../lib/api'
import { ENTITY_NAMES, ENTITY_COLORS } from '../lib/config'
import EntityTabs from '../components/dashboard/EntityTabs'
import StateCard from '../components/dashboard/StateCard'

export default function Dashboard() {
  const [activeTab, setActiveTab] = useState('primary')
  const [state, setState] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [lastUpdated, setLastUpdated] = useState(null)

  const fetchState = async () => {
    try {
      const data = await apiFetch('/state/combined')
      setState(data)
      setLastUpdated(new Date())
    } catch (err) {
      setError(err.message)
    }
    setLoading(false)
  }

  useEffect(() => {
    fetchState()
    const interval = setInterval(fetchState, 30000)
    return () => clearInterval(interval)
  }, [])

  if (loading) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-semibold">Dashboard</h1>
        <div className="text-[#888]">Loading state...</div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-semibold">Dashboard</h1>
        <div className="text-red-400">Error: {error}</div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Dashboard</h1>
        {lastUpdated && (
          <span className="text-sm text-[#888]">
            Updated: {lastUpdated.toLocaleTimeString()}
          </span>
        )}
      </div>

      <p className="text-[#888]">Live state — refreshes every 30 seconds</p>

      {/* Connection status */}
      <div className="flex items-center gap-2 text-sm">
        <span className={`w-2 h-2 rounded-full ${state?.primary ? 'bg-green-500' : 'bg-red-500'}`} />
        <span className="text-[#888]">API {state?.primary ? 'connected' : 'disconnected'}</span>
      </div>

      {/* Entity tabs */}
      <EntityTabs activeTab={activeTab} onTabChange={setActiveTab} />

      {/* Entity display */}
      {activeTab === 'primary' && (
        <StateCard
          entity={state?.primary}
          label={ENTITY_NAMES.primary}
          accentColor={ENTITY_COLORS.primary.text}
        />
      )}

      {activeTab === 'partner' && (
        <StateCard
          entity={state?.partner}
          label={ENTITY_NAMES.partner}
          accentColor={ENTITY_COLORS.partner.text}
        />
      )}
    </div>
  )
}
