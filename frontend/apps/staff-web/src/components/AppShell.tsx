import { useState, type ComponentType, type SVGProps } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { getApiMode } from '../api/client'
import { useAuth } from '../auth/authContext'
import { CAPABILITIES, hasAnyPermission, ROLE_LABELS } from '../permissions'
import type { Permission } from '../types'
import { BellIcon, BuildingIcon, LogoutIcon, OrdersIcon, SparkIcon, UsersIcon, WrenchIcon } from './Icons'

type NavItem = {
  to: string
  label: string
  description: string
  permissions: readonly Permission[]
  icon: ComponentType<SVGProps<SVGSVGElement>>
}

const NAV_ITEMS: NavItem[] = [
  { to: '/properties', label: '房源信息', description: '房间与租赁概览', permissions: [...CAPABILITIES.viewProperties, ...CAPABILITIES.viewWorkPropertyContext], icon: BuildingIcon },
  { to: '/orders', label: '我的订单', description: '申请、待签与合同', permissions: CAPABILITIES.viewOrders, icon: OrdersIcon },
  { to: '/maintenance', label: '维修工单', description: '分派与处理进度', permissions: CAPABILITIES.viewMaintenance, icon: WrenchIcon },
  { to: '/admin/staff', label: '员工账号与权限', description: 'P0 只读', permissions: CAPABILITIES.viewStaff, icon: UsersIcon },
  { to: '/agent', label: 'Agent', description: '功能即将上线', permissions: CAPABILITIES.useAgent, icon: SparkIcon },
]

export function AppShell() {
  const { session, logout } = useAuth()
  const navigate = useNavigate()
  const [profileOpen, setProfileOpen] = useState(false)
  if (!session) return null
  const initials = session.staff.displayName.split(' ').map((part) => part[0]).join('').slice(0, 2)
  const visibleItems = NAV_ITEMS.filter((item) => hasAnyPermission(session.permissions, item.permissions))

  const handleLogout = async () => {
    await logout()
    navigate('/login', { replace: true })
  }

  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand"><span className="brand-shield">S</span><div><strong>SafeScan</strong><small>Staff Portal</small></div></div>
      <nav aria-label="员工工作台导航">
        <p className="nav-heading">工作台</p>
        {visibleItems.map(({ to, label, description, icon: Icon }) => <NavLink key={to} to={to} className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>
          <Icon /><span><strong>{label}</strong><small>{description}</small></span>
        </NavLink>)}
      </nav>
      <div className="sidebar-foot"><span className="status-dot" />系统服务正常 <small>SafeScan P0</small></div>
    </aside>
    <div className="workspace">
      <header className="topbar">
        <div><strong>员工工作台</strong><span className={`mode-badge ${getApiMode()}`}>{getApiMode() === 'mock' ? '演示模式' : '实时数据'}</span></div>
        <div className="topbar-actions">
          <button className="icon-button" aria-label="通知"><BellIcon /><span className="notification-dot" /></button>
          <div className="profile-menu">
            <button className="profile-trigger" aria-expanded={profileOpen} onClick={() => setProfileOpen((open) => !open)}>
              <span className="avatar">{initials}</span><span><strong>{session.staff.displayName}</strong><small>{ROLE_LABELS[session.staff.role]}</small></span>
            </button>
            {profileOpen ? <div className="profile-popover">
              <div><strong>{session.staff.displayName}</strong><small>{session.staff.email}</small><small>{session.staff.staffCode}</small></div>
              <NavLink to="/profile" onClick={() => setProfileOpen(false)}>个人资料</NavLink>
              <button onClick={handleLogout}><LogoutIcon />退出登录</button>
            </div> : null}
          </div>
        </div>
      </header>
      <main className="page"><Outlet /></main>
    </div>
  </div>
}
