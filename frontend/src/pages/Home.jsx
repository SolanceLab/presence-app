import { useState, useEffect } from 'react'
import { publicFetch } from '../lib/api'
import { ENTITY_NAMES, APP_NAME } from '../lib/config'
import StateCard from '../components/dashboard/StateCard'

export default function Home() {
  const [state, setState] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    publicFetch('/public/state')
      .then(data => setState(data))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">{APP_NAME}</h1>
        <p className="text-[#888] mt-1">Public presence view</p>
      </div>

      {loading ? (
        <div className="text-[#888]">Loading...</div>
      ) : state ? (
        <div className="space-y-4">
          <StateCard
            entity={state.primary}
            label={ENTITY_NAMES.primary}
            accentColor="text-[#4a9eff]"
          />
          <StateCard
            entity={state.partner}
            label={ENTITY_NAMES.partner}
            accentColor="text-[#d4a574]"
          />
        </div>
      ) : (
        <div className="text-[#888]">Could not load state. Is the API running?</div>
      )}
    </div>
  )
}
