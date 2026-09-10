import { type FormEvent, type ReactNode, useState } from 'react'
import { NavLink, Navigate, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from './auth'
import { ApiError, type ApplicationStatus, type Capability, type LeaseStatus } from './api/contracts'
import { mockPersonaLabels, type MockPersona } from './api'

export const formatMoney = (value: number) => new Intl.NumberFormat('zh-CN', { style: 'currency', currency: 'AUD', maximumFractionDigits: 0 }).format(value)
export const formatDate = (value?: string) => value ? new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium' }).format(new Date(value)) : '—'

export const statusLabels: Record<ApplicationStatus | LeaseStatus | string, string> = {
  draft: '草稿', submitted: '已提交', reviewing: '审核中', approved: '已批准', rejected: '未通过', withdrawn: '已撤回', ineligible: '已失效', expired: '已过期', pending_signature: '待签署', executed: '待入住', active: '租约有效', ended: '已结束', terminated: '已终止', paid: '已支付', due: '待支付', scheduled: '已排期', open: '已提交', assigned: '已分派', in_progress: '处理中', blocked: '等待处理', completed: '已完成', cancelled: '已取消', processing: '生成中', failed: '失败', tenant: 'Tenant', prospect: 'Prospect', former_tenant: 'Former Tenant',
  available: '可申请', under_offer: '申请处理中', low: '低风险', medium: '中风险', high: '高风险',
}

export function StatusPill({ status }: { status: string }) { return <span className={`status status-${status}`}>{statusLabels[status] ?? status}</span> }

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const apiError = error instanceof ApiError ? error : new ApiError(500, 'unexpected_error', error instanceof Error ? error.message : '发生未知错误')
  const title = apiError.status === 0 ? '网络连接失败' : apiError.status === 401 ? '登录已过期' : apiError.status === 403 ? '没有操作权限' : apiError.status === 404 ? '内容不存在' : apiError.status === 409 ? '状态已发生变化' : apiError.status === 422 ? '提交内容有误' : '服务暂时不可用'
  return <div className="state-card error-state" role="alert"><span className="state-icon">!</span><div><h3>{title}</h3><p>{apiError.message}</p><small>{apiError.code}</small></div>{onRetry ? <button className="button secondary" onClick={onRetry}>重试</button> : null}</div>
}

export function LoadingState({ label = '正在加载…' }: { label?: string }) { return <div className="loading" role="status"><span /><span /><span /> {label}</div> }
export function EmptyState({ title, description, action }: { title: string; description: string; action?: ReactNode }) { return <div className="state-card empty-state"><span className="state-icon">⌂</span><h3>{title}</h3><p>{description}</p>{action}</div> }

const navItems: Array<{ to: string; label: string; icon: string; capability?: Capability }> = [
  { to: '/properties', label: '房源信息', icon: '⌂', capability: 'property:read' },
  { to: '/applications', label: '我的申请', icon: '□', capability: 'application:read' },
  { to: '/my-property', label: '我的房子', icon: '◇', capability: 'my-property:read' },
  { to: '/agent', label: 'Agent', icon: '✦', capability: 'agent:access' },
]

export function AppShell() {
  const { bootstrap, has, logout, isMockMode, setMockPersona } = useAuth()
  const [mobileOpen, setMobileOpen] = useState(false)
  const navigate = useNavigate()
  const customer = bootstrap?.customer
  const selectable = Object.entries(mockPersonaLabels) as Array<[MockPersona, string]>
  const currentPersona: MockPersona = !customer ? 'guest' : customer.status === 'prospect' ? 'prospect' : customer.status === 'former_tenant' ? 'former_tenant' : has('report:create') ? 'active_tenant' : 'executed_tenant'
  return <div className="app-shell">
    <header className="topbar"><button className="mobile-menu" aria-label="打开导航" onClick={() => setMobileOpen((value) => !value)}>☰</button><NavLink to="/properties" className="brand"><span className="brand-mark">S</span><span>SafeScan</span></NavLink><div className="topbar-actions">{isMockMode ? <label className="demo-select"><span>演示身份</span><select aria-label="演示身份" value={currentPersona} onChange={(event) => void setMockPersona(event.target.value as MockPersona)}>{selectable.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label> : null}{customer ? <><NavLink to="/profile" className="user-menu"><span className="avatar">{customer.username.slice(0, 1)}</span><span><b>{customer.username}</b><small>{statusLabels[customer.status]}</small></span></NavLink><button className="text-button" onClick={() => void logout().then(() => navigate('/properties'))}>退出</button></> : <><NavLink className="text-button" to="/login">登录</NavLink><NavLink className="button compact" to="/register">注册</NavLink></>}</div></header>
    <aside className={`sidebar ${mobileOpen ? 'open' : ''}`}><nav aria-label="主导航">{navItems.filter((item) => !item.capability || has(item.capability)).map((item) => <NavLink key={item.to} to={item.to} onClick={() => setMobileOpen(false)} className={({ isActive }) => isActive ? 'active' : ''}><span>{item.icon}</span>{item.label}</NavLink>)}</nav><div className="sidebar-help"><span>?</span><div><b>需要帮助？</b><small>联系真人客服</small></div></div></aside>
    <main className="content"><Outlet /></main>
  </div>
}

export function ProtectedRoute({ capability }: { capability?: Capability }) {
  const { bootstrap, loading, has } = useAuth()
  const location = useLocation()
  if (loading) return <LoadingState label="正在恢复登录状态…" />
  if (!bootstrap?.customer) return <Navigate to="/login" state={{ from: location.pathname }} replace />
  if (capability && !has(capability)) return <ErrorState error={new ApiError(403, 'action_forbidden', 'BFF 未授予当前页面能力')} />
  return <Outlet />
}

export function ReportReadRoute() {
  const { bootstrap, loading, has } = useAuth()
  if (loading) return <LoadingState label="正在恢复登录状态…" />
  if (!bootstrap?.customer) return <Navigate to="/login" replace />
  if (!has('report:read-current') && !has('report:read-history')) return <ErrorState error={new ApiError(404, 'resource_not_found', '没有找到报告')} />
  return <Outlet />
}

export function PageHeader({ eyebrow, title, description, action }: { eyebrow?: string; title: string; description?: string; action?: ReactNode }) { return <header className="page-header"><div>{eyebrow ? <span className="eyebrow">{eyebrow}</span> : null}<h1>{title}</h1>{description ? <p>{description}</p> : null}</div>{action}</header> }

export function AuthPage({ mode }: { mode: 'login' | 'register' }) {
  const { login, register } = useAuth(); const navigate = useNavigate(); const location = useLocation(); const [error, setError] = useState<unknown>(); const [busy, setBusy] = useState(false)
  async function submit(event: FormEvent<HTMLFormElement>) { event.preventDefault(); setBusy(true); setError(undefined); const data = new FormData(event.currentTarget); try { if (mode === 'login') await login({ email: String(data.get('email')), password: String(data.get('password')), rememberMe: Boolean(data.get('remember')) }); else await register({ email: String(data.get('email')), username: String(data.get('username')), password: String(data.get('password')), acceptedTermsVersion: '2026-09' }); const from = (location.state as { from?: string } | null)?.from; navigate(from ?? '/properties', { replace: true }) } catch (caught) { setError(caught) } finally { setBusy(false) } }
  return <div className="auth-wrap"><section className="auth-story"><NavLink to="/properties" className="brand light"><span className="brand-mark">S</span><span>SafeScan</span></NavLink><div><span className="eyebrow">安心租住，从看见开始</span><h1>让每一次入住，<br />都有清晰的答案。</h1><p>浏览可信房源、跟进申请、管理租约，并用视频报告了解家的安全状况。</p></div><blockquote>“从申请到入住，我始终知道下一步该做什么。”<footer>— SafeScan Tenant</footer></blockquote></section><section className="auth-panel"><form className="auth-card" onSubmit={submit}><span className="eyebrow">{mode === 'login' ? '欢迎回来' : '创建客户账号'}</span><h2>{mode === 'login' ? '登录 Tenant Portal' : '开始寻找你的新家'}</h2><p>{mode === 'login' ? '使用注册邮箱继续。演示模式可用 prospect@example.com、executed@example.com、active@example.com 或 former@example.com。' : '注册后身份固定为 Prospect，身份由服务端管理。'}</p>{error ? <ErrorState error={error} /> : null}{mode === 'register' ? <label>姓名<input name="username" required autoComplete="name" placeholder="你的姓名" /></label> : null}<label>邮箱<input name="email" type="email" required autoComplete="email" placeholder="name@example.com" /></label><label>密码<input name="password" type="password" minLength={8} required autoComplete={mode === 'login' ? 'current-password' : 'new-password'} placeholder="至少 8 位" /></label>{mode === 'login' ? <label className="check"><input name="remember" type="checkbox" /> 在此设备保持登录</label> : <label className="check"><input type="checkbox" required /> 我同意服务条款与隐私说明</label>}<button className="button full" disabled={busy}>{busy ? '请稍候…' : mode === 'login' ? '登录' : '注册并继续'}</button><p className="switch-auth">{mode === 'login' ? '还没有账号？' : '已经有账号？'} <NavLink to={mode === 'login' ? '/register' : '/login'}>{mode === 'login' ? '立即注册' : '返回登录'}</NavLink></p><NavLink to="/properties" className="guest-link">先以访客身份浏览房源 →</NavLink></form></section></div>
}
