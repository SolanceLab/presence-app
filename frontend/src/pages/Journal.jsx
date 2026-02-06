import { useState, useEffect } from 'react'
import { apiFetch } from '../lib/api'
import { formatShortDate } from '../lib/utils'

export default function Journal() {
  const [entries, setEntries] = useState([])
  const [loading, setLoading] = useState(true)
  const [expandedId, setExpandedId] = useState(null)

  useEffect(() => {
    apiFetch('/journal/recent?limit=20')
      .then(data => setEntries(data.entries || []))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-semibold">Journal</h1>
        <div className="text-[#888]">Loading entries...</div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Journal</h1>
      <p className="text-[#888]">{entries.length} recent entries</p>

      {entries.length === 0 ? (
        <div className="text-[#888]">No journal entries yet. Start writing through the MCP server.</div>
      ) : (
        <div className="space-y-3">
          {entries.map(entry => (
            <div
              key={entry.id}
              className="bg-[#1a1a1a] border border-[#2a2a2a] rounded-lg overflow-hidden"
            >
              {/* Entry header — click to expand */}
              <button
                onClick={() => setExpandedId(expandedId === entry.id ? null : entry.id)}
                className="w-full text-left p-4 hover:bg-[#222] transition-colors"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <span className="text-sm text-[#888]">{formatShortDate(entry.date)}</span>
                    <span className="text-[#e8e8e8] font-medium">{entry.title || 'Untitled'}</span>
                  </div>
                  <span className="text-[#666] text-xs">
                    {expandedId === entry.id ? 'collapse' : 'expand'}
                  </span>
                </div>

                {/* Emotion tags */}
                {entry.emotions?.length > 0 && (
                  <div className="flex flex-wrap gap-1.5 mt-2">
                    {entry.emotions.map(emotion => (
                      <span
                        key={emotion}
                        className="px-2 py-0.5 text-xs rounded-full bg-[#4a9eff]/10 text-[#4a9eff]"
                      >
                        {emotion}
                      </span>
                    ))}
                  </div>
                )}
              </button>

              {/* Expanded content */}
              {expandedId === entry.id && (
                <div className="px-4 pb-4 border-t border-[#2a2a2a]">
                  {entry.narrative && (
                    <div className="mt-3 text-sm text-[#ccc] whitespace-pre-wrap leading-relaxed">
                      {entry.narrative}
                    </div>
                  )}

                  {entry.carrying_forward && (
                    <div className="mt-3 p-3 bg-[#121212] rounded border border-[#2a2a2a]">
                      <span className="text-xs text-[#888]">Carrying forward:</span>
                      <p className="text-sm text-[#d4a574] mt-1">{entry.carrying_forward}</p>
                    </div>
                  )}

                  {entry.platforms?.length > 0 && (
                    <div className="mt-3 flex gap-2">
                      {entry.platforms.map(p => (
                        <span key={p} className="text-xs text-[#666]">{p}</span>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
