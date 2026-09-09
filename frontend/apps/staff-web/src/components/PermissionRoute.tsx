import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '../auth/authContext'
import { hasAnyPermission } from '../permissions'
import type { Permission } from '../types'

export function ProtectedRoute() {
  const { status } = useAuth()
  const location = useLocation()
  if (status === 'restoring') return <div className="app-loading"><span className="brand-shield">S</span><p>正在恢复安全会话…</p></div>
  if (status === 'anonymous') return <Navigate to="/login" replace state={{ from: location.pathname }} />
  return <Outlet />
}

export function PermissionRoute({ required }: { required: readonly Permission[] }) {
  const { session } = useAuth()
  return session && hasAnyPermission(session.permissions, required) ? <Outlet /> : <Navigate to="/forbidden" replace />
}
