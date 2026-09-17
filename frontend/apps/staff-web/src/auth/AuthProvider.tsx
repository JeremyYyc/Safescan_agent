import { useCallback, useEffect, useMemo, useState, type PropsWithChildren } from 'react'
import { staffPortalClient } from '../api/client'
import type { LoginInput, Session } from '../types'
import { AuthContext, type AuthStatus } from './authContext'
import { mergeBootstrap } from './session'

export function AuthProvider({ children }: PropsWithChildren) {
  const [status, setStatus] = useState<AuthStatus>('restoring')
  const [session, setSession] = useState<Session | null>(null)

  const clearSession = useCallback(() => {
    staffPortalClient.setAccessToken(null)
    setSession(null)
    setStatus('anonymous')
  }, [])

  useEffect(() => {
    staffPortalClient.setUnauthorizedHandler(clearSession)
    let active = true
    staffPortalClient.refresh().then((restored) => {
      if (!active) return
      staffPortalClient.setAccessToken(restored.accessToken)
      return staffPortalClient.bootstrap().then((bootstrap) => {
        if (!active) return
        setSession(mergeBootstrap(restored, bootstrap))
        setStatus('authenticated')
      })
    }).catch(() => {
      if (active) clearSession()
    })
    return () => {
      active = false
      staffPortalClient.setUnauthorizedHandler(null)
    }
  }, [clearSession])

  const login = useCallback(async (input: LoginInput) => {
    const nextSession = await staffPortalClient.login(input)
    staffPortalClient.setAccessToken(nextSession.accessToken)
    try {
      const bootstrap = await staffPortalClient.bootstrap()
      const authenticatedSession = mergeBootstrap(nextSession, bootstrap)
      setSession(authenticatedSession)
      setStatus('authenticated')
      return authenticatedSession
    } catch (error) {
      staffPortalClient.setAccessToken(null)
      throw error
    }
  }, [])

  const logout = useCallback(async () => {
    try {
      await staffPortalClient.logout()
    } finally {
      clearSession()
    }
  }, [clearSession])

  const value = useMemo(() => ({ status, session, login, logout }), [status, session, login, logout])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
