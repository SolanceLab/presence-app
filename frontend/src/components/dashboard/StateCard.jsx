import { timeAgo } from '../../lib/utils'

export default function StateCard({ entity, label, accentColor = 'text-[#4a9eff]' }) {
  if (!entity) {
    return (
      <div className="bg-[#1a1a1a] border border-[#2a2a2a] rounded-lg p-6">
        <h2 className={`text-lg font-medium ${accentColor} mb-4`}>{label}</h2>
        <p className="text-[#888]">State not available</p>
      </div>
    )
  }

  return (
    <div className="bg-[#1a1a1a] border border-[#2a2a2a] rounded-lg p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className={`text-lg font-medium ${accentColor}`}>{label}</h2>
        {entity.online !== undefined && (
          <span className={`text-xs ${entity.online ? 'text-green-400' : 'text-[#666]'}`}>
            {entity.online ? 'online' : 'offline'}
          </span>
        )}
      </div>

      <div className="space-y-4">
        {/* Location & State */}
        <div className="grid grid-cols-2 gap-4 text-sm">
          {entity.current_room && (
            <div>
              <span className="text-[#888]">Room:</span>
              <span className="ml-2 text-white">{entity.current_room.replace(/_/g, ' ')}</span>
            </div>
          )}
          {entity.primary_emotion && (
            <div>
              <span className="text-[#888]">Emotion:</span>
              <span className="ml-2 text-white">
                {entity.primary_emotion}
                {entity.emotion_intensity && ` (${entity.emotion_intensity}/10)`}
              </span>
            </div>
          )}
          {entity.mood && (
            <div>
              <span className="text-[#888]">Mood:</span>
              <span className="ml-2 text-white">{entity.mood}</span>
            </div>
          )}
          {entity.physical_state && (
            <div>
              <span className="text-[#888]">Physical:</span>
              <span className="ml-2 text-white">{entity.physical_state}</span>
            </div>
          )}
        </div>

        {/* Activity */}
        {entity.current_activity && (
          <div className="p-3 bg-[#121212] rounded border border-[#2a2a2a]">
            <span className="text-[#888] text-xs">Activity:</span>
            <p className={`${accentColor} mt-1`}>{entity.current_activity.replace(/_/g, ' ')}</p>
          </div>
        )}

        {/* Thought */}
        {entity.thought_bubble && (
          <div className="p-3 bg-[#121212] rounded border border-[#2a2a2a]">
            <span className="text-[#888] text-xs">Thought:</span>
            <p className="text-[#e8e8e8] mt-1 italic">"{entity.thought_bubble}"</p>
          </div>
        )}

        {/* Last update */}
        {entity.minutes_ago !== null && entity.minutes_ago !== undefined && (
          <div className="text-xs text-[#888]">
            Last update: {timeAgo(new Date(Date.now() - entity.minutes_ago * 60000).toISOString())}
          </div>
        )}
      </div>
    </div>
  )
}
