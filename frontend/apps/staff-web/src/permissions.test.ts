import { CAPABILITIES, hasAnyPermission, ROLE_PERMISSIONS } from './permissions'

describe('P0 permission matrix', () => {
  it('shows each role only the capabilities in the frozen matrix', () => {
    expect(hasAnyPermission(ROLE_PERMISSIONS.leasing_consultant, CAPABILITIES.viewProperties)).toBe(true)
    expect(hasAnyPermission(ROLE_PERMISSIONS.leasing_consultant, CAPABILITIES.viewOrders)).toBe(true)
    expect(hasAnyPermission(ROLE_PERMISSIONS.leasing_consultant, CAPABILITIES.viewMaintenance)).toBe(false)
    expect(hasAnyPermission(ROLE_PERMISSIONS.leasing_consultant, CAPABILITIES.createReport)).toBe(false)

    expect(hasAnyPermission(ROLE_PERMISSIONS.property_manager, CAPABILITIES.viewProperties)).toBe(true)
    expect(hasAnyPermission(ROLE_PERMISSIONS.property_manager, CAPABILITIES.viewMaintenance)).toBe(true)
    expect(hasAnyPermission(ROLE_PERMISSIONS.property_manager, CAPABILITIES.createReport)).toBe(true)
    expect(hasAnyPermission(ROLE_PERMISSIONS.property_manager, CAPABILITIES.viewOrders)).toBe(false)

    expect(hasAnyPermission(ROLE_PERMISSIONS.maintainer, CAPABILITIES.viewWorkPropertyContext)).toBe(true)
    expect(hasAnyPermission(ROLE_PERMISSIONS.maintainer, CAPABILITIES.viewProperties)).toBe(false)
    expect(hasAnyPermission(ROLE_PERMISSIONS.maintainer, CAPABILITIES.viewMaintenance)).toBe(true)
    expect(hasAnyPermission(ROLE_PERMISSIONS.maintainer, CAPABILITIES.createReport)).toBe(false)

    expect(hasAnyPermission(ROLE_PERMISSIONS.manager_admin, CAPABILITIES.viewStaff)).toBe(true)
    expect(hasAnyPermission(ROLE_PERMISSIONS.manager_admin, CAPABILITIES.viewOrders)).toBe(true)
    expect(hasAnyPermission(ROLE_PERMISSIONS.manager_admin, CAPABILITIES.createReport)).toBe(true)
  })

  it('gives the Agent placeholder to every active staff role', () => {
    for (const permissions of Object.values(ROLE_PERMISSIONS)) {
      expect(hasAnyPermission(permissions, CAPABILITIES.useAgent)).toBe(true)
    }
  })
})
