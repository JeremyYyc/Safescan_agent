import { ROLE_PERMISSIONS } from '../permissions'
import { ApiError, type MaintenanceOrder, type MaintenanceStatus, type PropertySummary, type Session, type StaffPortalClient, type StaffRole } from '../types'
import { DEMO_PASSWORDS, MAINTENANCE_ORDERS, MOCK_STAFF, ORDERS, PROPERTIES, STAFF_ACCOUNTS } from './mockData'

const MOCK_COOKIE = 'safescan_mock_staff'
const delay = (milliseconds = 180) => new Promise((resolve) => window.setTimeout(resolve, milliseconds))

function roleForEmail(email: string): StaffRole | undefined {
  return (Object.keys(MOCK_STAFF) as StaffRole[]).find(
    (role) => MOCK_STAFF[role].email.toLocaleLowerCase() === email.trim().toLocaleLowerCase(),
  )
}

function currentMockRole(): StaffRole | undefined {
  const match = document.cookie.split('; ').find((item) => item.startsWith(`${MOCK_COOKIE}=`))
  const role = match?.split('=')[1] as StaffRole | undefined
  return role && role in MOCK_STAFF ? role : undefined
}

function sessionForRole(role: StaffRole): Session {
  return {
    accessToken: `mock-access-${role}`,
    expiresIn: 900,
    staff: MOCK_STAFF[role],
    permissions: ROLE_PERMISSIONS[role],
  }
}

export class MockStaffPortalClient implements StaffPortalClient {
  private token: string | null = null
  private orders = MAINTENANCE_ORDERS.map((order) => ({ ...order }))
  private unauthorizedHandler: (() => void) | null = null

  setAccessToken(token: string | null) { this.token = token }
  setUnauthorizedHandler(handler: (() => void) | null) { this.unauthorizedHandler = handler }

  private requireSession(): Session {
    const role = currentMockRole()
    if (!role || !this.token) {
      this.unauthorizedHandler?.()
      throw new ApiError(401, { code: 'session_inactive', message: '登录状态已失效', retryable: false })
    }
    return sessionForRole(role)
  }

  async login(input: { email: string; password: string }) {
    await delay(320)
    const role = roleForEmail(input.email)
    if (!role || DEMO_PASSWORDS[role] !== input.password) {
      throw new ApiError(401, { code: 'invalid_credentials', message: '邮箱或密码不正确', retryable: false })
    }
    document.cookie = `${MOCK_COOKIE}=${role}; Path=/staff; SameSite=Lax`
    return sessionForRole(role)
  }

  async refresh() {
    await delay(120)
    const role = currentMockRole()
    if (!role) throw new ApiError(401, { code: 'invalid_refresh_token', message: '请重新登录', retryable: false })
    return sessionForRole(role)
  }

  async logout() {
    await delay(80)
    document.cookie = `${MOCK_COOKIE}=; Path=/staff; Max-Age=0; SameSite=Lax`
    this.token = null
  }

  async bootstrap() {
    await delay()
    const session = this.requireSession()
    return { staff: session.staff, permissions: session.permissions }
  }

  async listProperties(): Promise<PropertySummary[]> {
    await delay()
    const { staff } = this.requireSession()
    if (staff.role === 'maintainer') return PROPERTIES
      .filter((property) => this.orders.some((order) => order.property.id === property.id && order.assignee?.staffCode === staff.staffCode))
      .map(({ id, reference, building, room, bedrooms, bathrooms, weeklyRent, currency, occupancy, listingStatus, openMaintenance, reports }) => ({
        id, reference, building, room, bedrooms, bathrooms, weeklyRent, currency, occupancy, listingStatus, openMaintenance, reports,
      }))
    if (staff.role === 'leasing_consultant') return PROPERTIES.filter((property) => property.occupancy === 'vacant')
    if (staff.role === 'property_manager') return PROPERTIES.filter((property) => property.building.id === 'building-harbour')
    return PROPERTIES
  }

  async listOrders() {
    await delay()
    const { staff } = this.requireSession()
    if (!['leasing_consultant', 'manager_admin'].includes(staff.role)) throw new ApiError(403, { code: 'permission_denied', message: '当前角色无法查看订单', retryable: false })
    return staff.role === 'leasing_consultant' ? ORDERS.filter((order) => order.consultant.staffCode === staff.staffCode) : ORDERS
  }

  async listMaintenanceOrders() {
    await delay()
    const { staff } = this.requireSession()
    if (staff.role === 'leasing_consultant') throw new ApiError(403, { code: 'permission_denied', message: '当前角色无法查看维修工单', retryable: false })
    if (staff.role === 'maintainer') return this.orders.filter((order) => order.assignee?.staffCode === staff.staffCode)
    if (staff.role === 'property_manager') return this.orders.filter((order) => order.property.building.id === 'building-harbour')
    return this.orders
  }

  async transitionMaintenanceOrder(id: string, status: MaintenanceStatus, version: number): Promise<MaintenanceOrder> {
    await delay(260)
    this.requireSession()
    const index = this.orders.findIndex((order) => order.id === id)
    if (index === -1) throw new ApiError(404, { code: 'resource_not_found', message: '未找到工单', retryable: false })
    if (this.orders[index].version !== version) throw new ApiError(409, { code: 'version_conflict', message: '工单已被其他员工更新，请刷新后重试', retryable: true })
    this.orders[index] = { ...this.orders[index], status, version: version + 1, updatedAt: new Date().toISOString() }
    return this.orders[index]
  }

  async listStaff() {
    await delay()
    const { staff } = this.requireSession()
    if (staff.role !== 'manager_admin') throw new ApiError(403, { code: 'permission_denied', message: '仅 Manager Admin 可查看员工账号', retryable: false })
    return STAFF_ACCOUNTS
  }

  async createPropertyReport(propertyId: string) {
    await delay(420)
    const { staff } = this.requireSession()
    if (!['property_manager', 'manager_admin'].includes(staff.role)) throw new ApiError(403, { code: 'report_generation_not_allowed', message: '当前角色无法创建视频报告', retryable: false })
    if (!PROPERTIES.some((property) => property.id === propertyId)) throw new ApiError(404, { code: 'resource_not_found', message: '未找到房源', retryable: false })
    return { reportId: `report-${Date.now()}` }
  }
}
