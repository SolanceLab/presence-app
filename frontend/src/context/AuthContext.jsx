import { createContext, useContext, useState, useEffect } from 'react'
import { getToken, setToken, clearToken, apiFetch } from '../lib/api'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8787'
const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [authenticated, setAuthenticated] = useState(false)
  const [checking, setChecking] = useState(true)

  useEffect(() => {
    const token = getToken()
    if (!token) {
      setChecking(false)
      return
    }

    apiFetch('/auth/verify')
      .then(() => {
        setAuthenticated(true)
        setChecking(false)
      })
      .catch(() => {
        clearToken()
        setAuthenticated(false)
        setChecking(false)
      })
  }, [])

  const login = async (password) => {
    const response = await fetch(`${API_URL}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password }),
    })

    if (!response.ok) {
      const data = await response.json().catch(() => ({}))
      throw new Error(data.error || 'Login failed')
    }

    const data = await response.json()
    setToken(data.token)
    setAuthenticated(true)
  }

  const logout = () => {
    clearToken()
    setAuthenticated(false)
  }

  return (
    <AuthContext.Provider value={{ authenticated, checking, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be inside AuthProvider')
  return context
}
