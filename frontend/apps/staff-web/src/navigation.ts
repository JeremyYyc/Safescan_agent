import { CAPABILITIES, hasAnyPermission } from './permissions'
import type { Permission, StaffRole } from './types'

export type StaffNavigationItem = {
  to: string
  label: string
  description: string
  permissions: readonly Permission[]
  icon: 'properties' | 'orders' | 'maintenance' | 'staff' | 'agent'
}

const NAVIGATION_ITEMS: readonly StaffNavigationItem[] = [
  { to: '/properties', label: '房源信息', description: '房间与租赁概览', permissions: CAPABILITIES.viewProperties, icon: 'properties' },
  { to: '/orders', label: '我的订单', description: '申请、待签与合同', permissions: CAPABILITIES.viewOrders, icon: 'orders' },
  { to: '/maintenance', label: '维修工单', description: '分派与处理进度', permissions: CAPABILITIES.viewMaintenance, icon: 'maintenance' },
  { to: '/admin/staff', label: '员工账号与权限', description: 'P0 只读', permissions: CAPABILITIES.viewStaff, icon: 'staff' },
  { to: '/agent', label: 'Agent', description: '功能即将上线', permissions: CAPABILITIES.useAgent, icon: 'agent' },
]

export function ordersLabel(role: StaffRole): string {
  return role === 'manager_admin' ? '租房订单' : '我的订单'
}

export function staffNavigation(role: StaffRole, permissions: readonly Permission[]): StaffNavigationItem[] {
  return NAVIGATION_ITEMS
    .filter((item) => hasAnyPermission(permissions, item.permissions))
    .map((item) => item.to === '/orders' ? { ...item, label: ordersLabel(role) } : item)
}

export function defaultStaffPath(role: StaffRole): string {
  return role === 'maintainer' ? '/maintenance' : '/properties'
}

export function postLoginPath(role: StaffRole, requested?: string): string {
  if (!requested || requested === '/login' || (role === 'maintainer' && requested === '/properties')) {
    return defaultStaffPath(role)
  }
  return requested
}
