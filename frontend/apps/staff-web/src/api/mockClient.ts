import { ROLE_PERMISSIONS } from '../permissions'
import { ApiError, type MaintenanceOrder, type MaintenancePageOptions, type MaintenancePageResult, type MaintenanceStatus, type PropertySummary, type Session, type StaffPortalClient, type StaffRole } from '../types'
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
    const assignedBuildings = [...new Map(PROPERTIES.filter((property) => session.staff.role === 'manager_admin' || property.building.id === 'building-harbour').map((property) => [property.building.id, property.building])).values()]
    return { staff: { ...session.staff, assignedBuildings, assignmentScope: session.staff.role === 'manager_admin' ? 'all' as const : 'assigned' as const }, permissions: session.permissions }
  }

  async listProperties(): Promise<PropertySummary[]> {
    await delay()
    const { staff } = this.requireSession()
    if (staff.role === 'maintainer') throw new ApiError(403, { code: 'permission_denied', message: '维修人员只能从维修工单查看房源工作上下文', retryable: false })
    if (staff.role === 'leasing_consultant') return PROPERTIES.filter((property) => property.occupancy === 'vacant' && property.building.cityId === staff.cityId)
    if (staff.role === 'property_manager') return PROPERTIES.filter((property) => property.building.id === 'building-harbour')
    return PROPERTIES
  }

  async getPropertyImage(_url: string): Promise<Blob> { return new Blob([], { type: 'image/png' }) }

  async getLeasePdf(_leaseId: string): Promise<Blob> {
    this.requireSession()
    throw new ApiError(404, { code: 'demo_document_unavailable', message: '演示模式不提供真实合同 PDF，请切换实时数据查看', retryable: false })
  }

  async listOrders() {
    await delay()
    const { staff } = this.requireSession()
    if (!['leasing_consultant', 'manager_admin'].includes(staff.role)) throw new ApiError(403, { code: 'permission_denied', message: '当前角色无法查看订单', retryable: false })
    return staff.role === 'leasing_consultant' ? ORDERS.filter((order) => order.consultant.staffCode === staff.staffCode && order.property.building.cityId === staff.cityId) : ORDERS
  }

  async listMaintenanceOrders() {
    await delay()
    const { staff } = this.requireSession()
    if (staff.role === 'leasing_consultant') throw new ApiError(403, { code: 'permission_denied', message: '当前角色无法查看维修工单', retryable: false })
    if (staff.role === 'maintainer') return this.orders.filter((order) => order.assignee?.staffCode === staff.staffCode && order.property.building.cityId === staff.cityId)
    if (staff.role === 'property_manager') return this.orders.filter((order) => order.property.building.id === 'building-harbour')
    return this.orders
  }

  async listMaintenancePage(options: MaintenancePageOptions = {}): Promise<MaintenancePageResult> {
    const orders = (await this.listMaintenanceOrders()).filter((order) => !options.status || order.status === options.status)
    const start = Number(options.cursor) || 0
    return { items: orders.slice(start, start + 50), nextCursor: start + 50 < orders.length ? String(start + 50) : undefined }
  }

  async transitionMaintenanceOrder(id: string, status: MaintenanceStatus, version: number): Promise<MaintenanceOrder> {
    await delay(260)
    const { staff } = this.requireSession()
    const index = this.orders.findIndex((order) => order.id === id)
    if (index === -1) throw new ApiError(404, { code: 'resource_not_found', message: '未找到工单', retryable: false })
    if (staff.role !== 'manager_admin' && (this.orders[index].property.building.cityId !== staff.cityId || (staff.role === 'maintainer' ? this.orders[index].assignee?.staffCode !== staff.staffCode : staff.role !== 'property_manager' || this.orders[index].property.building.id !== 'building-harbour'))) throw new ApiError(404, { code: 'resource_not_found', message: '未找到工单', retryable: false })
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
    if (!PROPERTIES.some((property) => property.id === propertyId && (staff.role === 'manager_admin' || (property.building.cityId === staff.cityId && property.building.id === 'building-harbour')))) throw new ApiError(404, { code: 'resource_not_found', message: '未找到房源', retryable: false })
    return { reportId: `report-${Date.now()}` }
  }

  async listOrderPage(cursor?: string, stage?: string, query?: string) {
    const term = query?.trim().toLowerCase()
    const orders = (await this.listOrders()).filter((order) => (!stage || order.stage === stage)
      && (!term || [order.reference, order.property.reference, order.property.room,
        order.property.building.name, order.property.building.address,
        order.customer.displayName, order.customer.email].some((value) => value?.toLowerCase().includes(term))))
    const start = Number(cursor) || 0
    return { items: orders.slice(start, start + 50), nextCursor: start + 50 < orders.length ? String(start + 50) : undefined, total: orders.length }
  }

  async getMaintenanceOrder(id: string) {
    const item = (await this.listMaintenanceOrders()).find((row) => row.id === id)
    if (!item) throw new ApiError(404, { code: 'resource_not_found', message: '未找到工单', retryable: false })
    return item
  }

  async getPropertyDetail(id: string) {
    const property = (await this.listProperties()).find((row) => row.id === id)
    if (!property) throw new ApiError(404, { code: 'resource_not_found', message: '未找到房源', retryable: false })
    const { staff } = this.requireSession()
    const leases = (staff.role === 'property_manager' ? ORDERS : await this.listOrders()).filter((row) => row.property.id === id)
    const maintenance = staff.role === 'leasing_consultant' ? [] : (await this.listMaintenanceOrders()).filter((row) => row.property.id === id)
    return { property, leases, maintenance, inspections: [], partialErrors: [], attributes: {} }
  }

}
