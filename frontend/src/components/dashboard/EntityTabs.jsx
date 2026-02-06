import { ENTITY_NAMES, ENTITY_COLORS } from '../../lib/config'

const ENTITIES = [
  { id: 'primary', label: ENTITY_NAMES.primary, activeClass: ENTITY_COLORS.primary.active },
  { id: 'partner', label: ENTITY_NAMES.partner, activeClass: ENTITY_COLORS.partner.active },
]

const INACTIVE_CLASS = 'text-[#888] border-[#2a2a2a] hover:text-[#ccc] hover:border-[#444]'

export default function EntityTabs({ activeTab, onTabChange }) {
  return (
    <div className="flex gap-2">
      {ENTITIES.map(entity => (
        <button
          key={entity.id}
          onClick={() => onTabChange(entity.id)}
          className={`px-4 py-2 rounded-lg text-sm font-medium border transition-colors ${
            activeTab === entity.id ? entity.activeClass : INACTIVE_CLASS
          }`}
        >
          {entity.label}
        </button>
      ))}
    </div>
  )
}
