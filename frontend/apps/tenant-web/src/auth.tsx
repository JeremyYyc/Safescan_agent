import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { api, isMockMode, MockTenantPortalApi, type MockPersona } from './api'
import type { BootstrapView, Capability, LoginInput, RegisterInput } from './api/contracts'

interface AuthValue {
  bootstrap: BootstrapView | null
  loading: boolean
  isMockMode: boolean
  has: (capability: Capability) => boolean
  login: (input: LoginInput) => Promise<void>
  register: (input: RegisterInput) => Promise<void>
  logout: () => Promise<void>
  setMockPersona: (persona: MockPersona) => Promise<void>
}

const AuthContext = createContext<AuthValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [bootstrap, setBootstrap] = useState<BootstrapView | null>(null)
  const [loading, setLoading] = useState(true)

  const restore = useCallback(async () => {
    try { setBootstrap(await api.restoreSession()) } finally { setLoading(false) }
  }, [])
  useEffect(() => { void restore() }, [restore])

  const value = useMemo<AuthValue>(() => ({
    bootstrap,
    loading,
    isMockMode,
    has: (capability) => bootstrap?.capabilities.includes(capability) ?? false,
    login: async (input) => { setBootstrap(await api.login(input)) },
    register: async (input) => { setBootstrap(await api.register(input)) },
    logout: async () => { await api.logout(); setBootstrap(await api.bootstrap()) },
    setMockPersona: async (persona) => { if (api instanceof MockTenantPortalApi) { api.setPersona(persona); setBootstrap(await api.bootstrap()) } },
  }), [bootstrap, loading])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth must be used inside AuthProvider')
  return value
}
