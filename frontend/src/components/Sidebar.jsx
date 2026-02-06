import { NavLink, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { APP_NAME } from '../lib/config'

const navItems = [
  { path: '/', label: 'Home', requiresAuth: false },
  { path: '/dashboard', label: 'Dashboard', requiresAuth: true },
  { path: '/journal', label: 'Journal', requiresAuth: true },
]

export default function Sidebar({ isOpen, onClose }) {
  const { authenticated, logout } = useAuth()
  const navigate = useNavigate()

  const handleLogout = () => {
    logout()
    onClose()
    navigate('/')
  }

  return (
    <>
      {isOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-40 lg:hidden"
          onClick={onClose}
        />
      )}

      <aside className={`
        fixed top-0 left-0 h-full w-64 bg-[#1a1a1a] border-r border-[#2a2a2a] z-50
        transform transition-transform duration-200 ease-in-out
        lg:translate-x-0 lg:static
        ${isOpen ? 'translate-x-0' : '-translate-x-full'}
      `}>
        <div className="p-6 border-b border-[#2a2a2a]">
          <h1 className="text-xl font-semibold tracking-wide">{APP_NAME}</h1>
          <div className="flex items-center gap-2 mt-1">
            <span className="w-2 h-2 rounded-full bg-[#4a9eff] animate-pulse" />
            <span className="text-sm text-[#888]">online</span>
          </div>
        </div>

        <nav className="p-4 pb-20">
          <ul className="space-y-1">
            {navItems.map((item) => {
              const locked = item.requiresAuth && !authenticated

              if (locked) {
                return (
                  <li key={item.path}>
                    <span className="block px-4 py-3 rounded-lg text-[#444] cursor-not-allowed">
                      {item.label}
                    </span>
                  </li>
                )
              }

              return (
                <li key={item.path}>
                  <NavLink
                    to={item.path}
                    onClick={onClose}
                    className={({ isActive }) => `
                      block px-4 py-3 rounded-lg transition-colors
                      ${isActive
                        ? 'bg-[#2a2a2a] text-white'
                        : 'text-[#888] hover:text-white hover:bg-[#222]'
                      }
                    `}
                  >
                    {item.label}
                  </NavLink>
                </li>
              )
            })}
          </ul>
        </nav>

        <div className="absolute bottom-0 left-0 right-0 p-4 border-t border-[#2a2a2a]">
          {authenticated ? (
            <button
              onClick={handleLogout}
              className="flex items-center gap-2 text-[#888] hover:text-white transition-colors"
            >
              <span className="text-sm">Logout</span>
            </button>
          ) : (
            <NavLink
              to="/login"
              onClick={onClose}
              className="flex items-center gap-2 text-[#888] hover:text-[#4a9eff] transition-colors"
            >
              <span className="text-sm">Login</span>
            </NavLink>
          )}
        </div>
      </aside>
    </>
  )
}
