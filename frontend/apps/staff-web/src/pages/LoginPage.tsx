import { useState, type FormEvent } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'
import { getApiMode } from '../api/client'
import { MOCK_STAFF, DEMO_PASSWORDS } from '../api/mockData'
import { useAuth } from '../auth/authContext'
import { defaultStaffPath, postLoginPath } from '../navigation'
import { ROLE_LABELS } from '../permissions'
import { ApiError, type StaffRole } from '../types'

const DEMO_ROLES: StaffRole[] = ['leasing_consultant', 'property_manager', 'maintainer', 'manager_admin']

export function LoginPage() {
  const { status, session, login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [email, setEmail] = useState(MOCK_STAFF.property_manager.email)
  const [password, setPassword] = useState(DEMO_PASSWORDS.property_manager)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  if (status === 'authenticated' && session) return <Navigate to={defaultStaffPath(session.staff.role)} replace />

  const selectDemoRole = (role: StaffRole) => {
    setEmail(MOCK_STAFF[role].email)
    setPassword(DEMO_PASSWORDS[role])
    setError('')
  }

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setSubmitting(true)
    setError('')
    try {
      const authenticatedSession = await login({ email, password })
      const requested = (location.state as { from?: string } | null)?.from
      navigate(postLoginPath(authenticatedSession.staff.role, requested), { replace: true })
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : '登录失败，请稍后重试')
    } finally {
      setSubmitting(false)
    }
  }

  return <div className="login-page">
    <section className="login-story">
      <div className="brand light"><span className="brand-shield">S</span><div><strong>SafeScan</strong><small>Property intelligence</small></div></div>
      <div className="story-copy"><p className="eyebrow">统一运营视图</p><h1>让每一处房产，<br />都处于清晰掌控。</h1><p>房源、租约、维修与安全报告集中于一个员工工作台。</p></div>
      <div className="trust-row"><span>✓ 权限隔离</span><span>✓ 同源安全访问</span><span>✓ 全程可追溯</span></div>
    </section>
    <section className="login-panel">
      <div className="login-card">
        <p className="eyebrow">STAFF PORTAL</p><h2>欢迎回来</h2><p className="muted">使用员工账号登录 SafeScan 工作台</p>
        {getApiMode() === 'mock' ? <div className="demo-picker"><span>快速选择演示角色</span><div>{DEMO_ROLES.map((role) => <button type="button" key={role} className={email === MOCK_STAFF[role].email ? 'selected' : ''} onClick={() => selectDemoRole(role)}>{ROLE_LABELS[role]}</button>)}</div></div> : null}
        <form onSubmit={submit}>
          <label>员工邮箱<input type="email" autoComplete="username" value={email} onChange={(event) => setEmail(event.target.value)} required /></label>
          <label>密码<input type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} required /></label>
          {error ? <div className="form-error" role="alert">{error}</div> : null}
          <button className="button primary wide" disabled={submitting}>{submitting ? '正在验证…' : '安全登录'}</button>
        </form>
        <p className="login-note">访问即表示您同意遵守 SafeScan 员工信息安全规范。</p>
      </div>
    </section>
  </div>
}
