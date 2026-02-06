import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

export default function ProtectedRoute({ children }) {
  const { authenticated, checking } = useAuth()
  const location = useLocation()

  if (checking) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="text-[#888] text-sm">Verifying...</div>
      </div>
    )
  }

  if (!authenticated) {
    return <Navigate to="/login" state={{ from: location.pathname }} replace />
  }

  return children
}
