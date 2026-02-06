import { useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { APP_NAME } from '../lib/config'

export default function Login() {
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)
  const { login, authenticated } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()

  const from = location.state?.from || '/'

  if (authenticated) {
    navigate(from, { replace: true })
    return null
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError(null)
    setLoading(true)

    try {
      await login(password)
      navigate(from, { replace: true })
    } catch (err) {
      setError(err.message)
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-[#121212] flex items-center justify-center p-4">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <h1 className="text-2xl font-semibold tracking-wide text-[#e8e8e8]">{APP_NAME}</h1>
          <div className="flex items-center justify-center gap-2 mt-2">
            <span className="w-2 h-2 rounded-full bg-[#4a9eff] animate-pulse" />
            <span className="text-sm text-[#888]">online</span>
          </div>
        </div>

        <div className="bg-[#1a1a1a] border border-[#2a2a2a] rounded-lg p-6">
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Password"
                autoFocus
                className="w-full bg-[#121212] border border-[#2a2a2a] rounded-md px-4 py-3 text-sm text-[#e8e8e8] placeholder-[#666] focus:outline-none focus:border-[#4a9eff]/50 transition-colors"
              />
            </div>

            {error && (
              <p className="text-red-400/80 text-sm">{error}</p>
            )}

            <button
              type="submit"
              disabled={loading || !password}
              className={`w-full py-3 rounded-md text-sm font-medium transition-colors ${
                loading || !password
                  ? 'bg-[#2a2a2a] text-[#666] cursor-not-allowed'
                  : 'bg-[#4a9eff]/20 text-[#4a9eff] border border-[#4a9eff]/40 hover:bg-[#4a9eff]/30'
              }`}
            >
              {loading ? 'Verifying...' : 'Enter'}
            </button>
          </form>
        </div>
      </div>
    </div>
  )
}
