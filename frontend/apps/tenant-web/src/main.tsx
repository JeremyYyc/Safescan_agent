import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider } from './auth'
import { AppShell, AuthPage, ProtectedRoute, ReportReadRoute } from './components'
import { AgentPage, ApplicationDetailPage, ApplicationsPage, HistoricalPropertyPage, MyPropertyPage, NewApplicationPage, NewReportPage, ProfilePage, PropertiesPage, PropertyDetailPage, ReportDetailPage } from './pages'
import './style.css'

function App() {
  return <Routes>
    <Route path="login" element={<AuthPage mode="login" />} />
    <Route path="register" element={<AuthPage mode="register" />} />
    <Route element={<AppShell />}>
      <Route index element={<Navigate to="properties" replace />} />
      <Route path="properties" element={<PropertiesPage />} />
      <Route path="properties/:id" element={<PropertyDetailPage />} />
      <Route element={<ProtectedRoute capability="application:read" />}><Route path="applications" element={<ApplicationsPage />} /><Route path="applications/:id" element={<ApplicationDetailPage />} /></Route>
      <Route element={<ProtectedRoute capability="application:create" />}><Route path="applications/new" element={<NewApplicationPage />} /></Route>
      <Route element={<ProtectedRoute capability="my-property:read" />}><Route path="my-property" element={<MyPropertyPage />} /><Route path="leases/:leaseId/property" element={<HistoricalPropertyPage />} /></Route>
      <Route element={<ProtectedRoute capability="report:create" />}><Route path="reports/new" element={<NewReportPage />} /></Route>
      <Route element={<ReportReadRoute />}><Route path="reports/:id" element={<ReportDetailPage />} /></Route>
      <Route element={<ProtectedRoute />}><Route path="profile" element={<ProfilePage />} /><Route path="agent" element={<AgentPage />} /></Route>
      <Route path="*" element={<Navigate to="properties" replace />} />
    </Route>
  </Routes>
}

createRoot(document.getElementById('root')!).render(<StrictMode><BrowserRouter basename="/tenant" future={{ v7_startTransition: true, v7_relativeSplatPath: true }}><AuthProvider><App /></AuthProvider></BrowserRouter></StrictMode>)
