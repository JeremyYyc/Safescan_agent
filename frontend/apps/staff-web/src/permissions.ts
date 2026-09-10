import type { Permission, StaffRole } from './types'

export const ROLE_LABELS: Record<StaffRole, string> = {
  leasing_consultant: 'Leasing Consultant',
  property_manager: 'Property Manager',
  maintainer: 'Maintainer',
  manager_admin: 'Manager Admin',
}

const LEASING_PERMISSIONS: Permission[] = [
  'property:read_market',
  'prospect:manage',
  'application:manage',
  'lease:prepare',
  'lease:execute',
  'agent:staff:use',
]

const PROPERTY_MANAGER_PERMISSIONS: Permission[] = [
  'building:read_assigned',
  'property:manage_assigned',
  'lease:manage_active_assigned',
  'maintenance:assign_assigned',
  'maintenance:update_assigned',
  'report:read_assigned',
  'report:generate_assigned',
  'agent:staff:use',
]

const MAINTAINER_PERMISSIONS: Permission[] = [
  'work_order:read_assigned',
  'work_order:update_assigned',
  'work_order:evidence_write',
  'property:read_work_context',
  'report:read_work_context',
  'agent:staff:use',
]

const ADMIN_PERMISSIONS: Permission[] = [
  ...LEASING_PERMISSIONS,
  ...PROPERTY_MANAGER_PERMISSIONS,
  ...MAINTAINER_PERMISSIONS,
  'building:read_all',
  'property:read_all',
  'prospect:manage_all',
  'application:manage_all',
  'lease:manage_all',
  'maintenance:manage_all',
  'report:read_all',
  'report:generate_all',
  'iam:user:read',
  'iam:user:status_manage',
  'iam:staff:create',
  'iam:staff:read',
  'iam:staff:employment_manage',
  'iam:staff:role_manage',
  'iam:audit:read',
  'rbac:read',
  'rbac:manage',
  'scope:manage',
]

export const ROLE_PERMISSIONS: Record<StaffRole, Permission[]> = {
  leasing_consultant: LEASING_PERMISSIONS,
  property_manager: PROPERTY_MANAGER_PERMISSIONS,
  maintainer: MAINTAINER_PERMISSIONS,
  manager_admin: [...new Set(ADMIN_PERMISSIONS)],
}

export const CAPABILITIES = {
  viewProperties: ['property:read_market', 'property:manage_assigned', 'property:read_all'] as Permission[],
  viewWorkPropertyContext: ['property:read_work_context'] as Permission[],
  viewOrders: ['prospect:manage', 'lease:manage_all'] as Permission[],
  viewMaintenance: ['maintenance:update_assigned', 'work_order:read_assigned', 'maintenance:manage_all'] as Permission[],
  viewStaff: ['iam:staff:read', 'rbac:read'] as Permission[],
  createReport: ['report:generate_assigned', 'report:generate_all'] as Permission[],
  useAgent: ['agent:staff:use'] as Permission[],
} as const

export function hasAnyPermission(permissions: readonly Permission[], required: readonly Permission[]): boolean {
  const granted = new Set(permissions)
  return required.some((permission) => granted.has(permission))
}

export function hasAllPermissions(permissions: readonly Permission[], required: readonly Permission[]): boolean {
  const granted = new Set(permissions)
  return required.every((permission) => granted.has(permission))
}
