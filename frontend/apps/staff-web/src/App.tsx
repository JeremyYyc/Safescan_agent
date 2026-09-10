import { Navigate, Route, Routes } from 'react-router-dom'
import { useAuth } from './auth/authContext'
import { AppShell } from './components/AppShell'
import { PermissionRoute, ProtectedRoute } from './components/PermissionRoute'
import { CAPABILITIES } from './permissions'
import { AgentPage } from './pages/AgentPage'
import { LoginPage } from './pages/LoginPage'
import { MaintenancePage } from './pages/MaintenancePage'
import { OrdersPage } from './pages/OrdersPage'
import { ProfilePage } from './pages/ProfilePage'
import { PropertiesPage } from './pages/PropertiesPage'
import { StaffAdminPage } from './pages/StaffAdminPage'
import { ForbiddenPage, NotFoundPage } from './pages/StatusPage'
import { defaultStaffPath } from './navigation'

function DefaultStaffRoute() {
  const { session } = useAuth()
  return <Navigate to={session ? defaultStaffPath(session.staff.role) : '/login'} replace />
}

export function App() {
  return <Routes>
    <Route path="/login" element={<LoginPage />} />
    <Route element={<ProtectedRoute />}>
      <Route element={<AppShell />}>
        <Route index element={<DefaultStaffRoute />} />
        <Route element={<PermissionRoute required={CAPABILITIES.viewProperties} />}><Route path="properties" element={<PropertiesPage />} /></Route>
        <Route element={<PermissionRoute required={CAPABILITIES.viewOrders} />}><Route path="orders" element={<OrdersPage />} /></Route>
        <Route element={<PermissionRoute required={CAPABILITIES.viewMaintenance} />}><Route path="maintenance" element={<MaintenancePage />} /></Route>
        <Route element={<PermissionRoute required={CAPABILITIES.viewStaff} />}><Route path="admin/staff" element={<StaffAdminPage />} /></Route>
        <Route element={<PermissionRoute required={CAPABILITIES.useAgent} />}><Route path="agent" element={<AgentPage />} /></Route>
        <Route path="profile" element={<ProfilePage />} />
        <Route path="forbidden" element={<ForbiddenPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Route>
  </Routes>
}
