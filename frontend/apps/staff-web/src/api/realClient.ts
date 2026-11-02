import {
  ApiError,
  type ApiErrorShape,
  type BootstrapData,
  type LoginInput,
  type MaintenanceOrder,
  type MaintenancePageOptions,
  type MaintenancePageResult,
  type MaintenanceStatus,
  type OrderSummary,
  type PropertySummary,
  type PropertyDetail,
  type ResultPage,
  type Session,
  type StaffAccount,
  type StaffIdentity,
  type StaffPortalClient,
  type StaffRole,
} from '../types'

interface Envelope<T> { data: T; meta?: { partial_errors?: unknown[] } }
interface Page<T> { items: T[] }
type JsonRecord = Record<string, unknown>

function record(value: unknown): JsonRecord { return value && typeof value === 'object' ? value as JsonRecord : {} }
function text(value: unknown): string { return typeof value === 'string' ? value : '' }
function number(value: unknown): number { return typeof value === 'number' ? value : Number(value) || 0 }
function role(value: unknown): StaffRole { return text(value) as StaffRole }
function camelize<T>(value: unknown): T {
  if (Array.isArray(value)) return value.map((item) => camelize(item)) as T
  if (!value || typeof value !== 'object') return value as T
  return Object.fromEntries(Object.entries(value as JsonRecord).map(([key, item]) => [
    key.replace(/_([a-z])/g, (_, letter: string) => letter.toUpperCase()),
    camelize(item),
  ])) as T
}

function normalizeSession(value: unknown): Session {
  const data = record(value)
  const portal = text(data.portal)
  if (portal && portal !== 'staff') {
    throw new ApiError(403, {
      code: 'staff_portal_required',
      message: '该账号不能登录员工端',
      retryable: false,
    })
  }
  const user = record(data.user)
  const staff = record(user.staff ?? data.staff)
  const staffRole = record(staff.role)
  const permissions = (data.scopes ?? data.permissions ?? []) as Session['permissions']
  return {
    accessToken: text(data.access_token ?? data.accessToken),
    expiresIn: number(data.expires_in ?? data.expiresIn),
    permissions,
    staff: {
      id: text(staff.id ?? user.id),
      username: text(user.username ?? staff.username ?? staff.display_name ?? staff.displayName),
      displayName: text(staff.display_name ?? staff.displayName ?? user.username),
      email: text(user.email ?? staff.email),
      staffCode: text(staff.staff_code ?? staff.staffCode),
      cityId: text(staff.city_id ?? staff.cityId) || undefined,
      role: role(staffRole.code ?? staff.role),
      roleName: text(staffRole.name ?? staff.role_name ?? staff.roleName),
    },
  }
}

function normalizeBootstrap(value: unknown): BootstrapData {
  const data = record(value)
  const staff = record(data.staff)
  const identity: StaffIdentity = {
    id: text(staff.id),
    username: text(staff.username ?? staff.user_name ?? staff.display_name ?? staff.displayName),
    displayName: text(staff.display_name ?? staff.displayName),
    email: text(staff.email),
    staffCode: text(staff.staff_code ?? staff.staffCode),
    cityId: text(staff.city_id ?? staff.cityId) || undefined,
    role: role(record(staff.role).code ?? staff.role),
    roleName: text(staff.role_name ?? staff.roleName ?? record(staff.role).name),
    assignedBuildings: camelize<StaffIdentity['assignedBuildings']>(staff.assigned_buildings ?? []),
    assignmentScope: text(staff.assignment_scope || 'assigned') as StaffIdentity['assignmentScope'],
  }
  return {
    staff: identity,
    permissions: (data.capabilities ?? staff.permissions ?? data.permissions ?? []) as BootstrapData['permissions'],
  }
}

function pageItems<T>(value: unknown): T[] {
  const page = camelize<Page<T>>(value)
  return Array.isArray(page.items) ? page.items : []
}

function normalizedRecord(value: unknown): JsonRecord {
  return record(camelize<JsonRecord>(value))
}

function normalizedPropertyContext(value: unknown): OrderSummary['property'] {
  const property = normalizedRecord(value)
  const building = record(property.building)
  const attributes = record(property.attributes)
  const propertyId = text(property.id) || 'unknown-property'
  const address = text(building.address ?? property.address) || '地址未提供'
  return {
    id: propertyId,
    reference: text(property.reference) || '—',
    room: text(property.room ?? attributes.roomNumber) || '—',
    building: {
      id: text(building.id) || `unassigned:${propertyId}`,
      cityId: text(building.cityId ?? property.cityId) || undefined,
      name: text(building.name) || (address !== '地址未提供' ? address : '房源信息未提供'),
      address,
    },
  }
}

function orderStage(value: unknown): OrderSummary['stage'] {
  const status = text(value)
  if (status === 'pending_signature') return 'pending_signature'
  if (status === 'executed' || status === 'active') return 'executed'
  if (['ended', 'terminated', 'cancelled', 'expired'].includes(status)) return 'ended'
  return 'application'
}

function normalizeOrder(value: unknown): OrderSummary {
  const data = normalizedRecord(value)
  const customer = record(data.customer ?? data.tenant)
  const consultant = record(data.consultant ?? data.assignedConsultant)
  const document = record(data.document ?? data.contract)
  const signers = Array.isArray(data.tenantSigners) ? data.tenantSigners.map(record) : []
  const primarySigner = signers[0] ?? {}
  const status = text(data.status ?? data.stage)
  const id = text(data.id) || text(data.reference) || 'unknown-order'

  return {
    id,
    reference: text(data.reference) || '未编号订单',
    stage: orderStage(data.stage ?? data.status),
    property: normalizedPropertyContext(data.property),
    customer: {
      displayName: text(customer.displayName ?? customer.name) || '租客信息未提供',
      email: text(customer.email) || '—',
      phone: text(customer.phone) || '—',
    },
    consultant: {
      displayName: text(consultant.displayName ?? consultant.name) || '未分配顾问',
      staffCode: text(consultant.staffCode) || '—',
    },
    startsOn: text(data.startsOn) || '—',
    endsOn: text(data.endsOn) || '—',
    weeklyRent: number(data.weeklyRent),
    status: status || '状态未提供',
    contract: Object.keys(document).length ? {
      documentId: text(document.documentId ?? document.id ?? document.reference) || '未编号合同',
      version: number(document.version),
      digest: text(document.digest ?? document.termsDigest) || '摘要未提供',
      tenantSignedAt: text(document.tenantSignedAt ?? primarySigner.signedAt) || undefined,
      companySignedAt: text(document.companySignedAt ?? data.companySignedAt) || undefined,
    } : undefined,
  }
}

function maintenanceStatus(value: unknown): MaintenanceStatus {
  const status = text(value)
  return ['open', 'assigned', 'in_progress', 'blocked', 'completed', 'cancelled'].includes(status)
    ? status as MaintenanceStatus
    : 'open'
}

function maintenancePriority(value: unknown): MaintenanceOrder['priority'] {
  const priority = text(value)
  if (priority === 'normal') return 'medium'
  return ['low', 'medium', 'high', 'urgent'].includes(priority)
    ? priority as MaintenanceOrder['priority']
    : 'medium'
}

function normalizeMaintenanceOrder(value: unknown): MaintenanceOrder {
  const data = normalizedRecord(value)
  const tenant = record(data.tenant ?? data.reportedBy)
  const assignedStaff = record(data.assignee ?? data.assignedStaff)
  const assignedStaffId = text(assignedStaff.id)
  const id = text(data.id) || text(data.reference) || 'unknown-maintenance-order'

  return {
    id,
    reference: text(data.reference) || '未编号工单',
    status: maintenanceStatus(data.status),
    priority: maintenancePriority(data.priority),
    version: number(data.version),
    summary: text(data.summary) || '未提供工单摘要',
    description: text(data.description) || '未提供问题描述',
    property: normalizedPropertyContext(data.property),
    tenant: {
      displayName: text(tenant.displayName ?? tenant.name) || '报修租客信息未提供',
      email: text(tenant.email) || '—',
      phone: text(tenant.phone) || '—',
    },
    assignee: Object.keys(assignedStaff).length ? {
      displayName: text(assignedStaff.displayName ?? assignedStaff.name) || '已分派员工',
      staffCode: text(assignedStaff.staffCode) || (assignedStaffId ? '—' : '未提供'),
    } : undefined,
    updatedAt: text(data.updatedAt ?? data.createdAt) || '1970-01-01T00:00:00.000Z',
    timeline: Array.isArray(data.timeline) ? data.timeline as MaintenanceOrder['timeline'] : undefined,
  }
}

function normalizeStaffAccount(value: unknown): StaffAccount {
  const data = normalizedRecord(value)
  const staffRole = record(data.role)
  const roleCode = text(staffRole.code ?? data.role) as StaffRole
  const employmentStatus = text(data.employmentStatus)
  return {
    id: text(data.id) || text(data.reference) || 'unknown-staff',
    staffCode: text(data.staffCode) || '—',
    cityId: text(data.cityId) || undefined,
    displayName: text(data.displayName ?? data.username) || '未命名员工',
    email: text(data.email) || '—',
    role: roleCode || 'leasing_consultant',
    employmentStatus: ['active', 'suspended', 'ended'].includes(employmentStatus)
      ? employmentStatus as StaffAccount['employmentStatus']
      : 'active',
    permissions: Array.isArray(data.permissions) ? data.permissions as StaffAccount['permissions'] : [],
  }
}

function normalizeProperty(value: unknown): PropertySummary {
  const data = normalizedRecord(value)
  const attributes = record(data.attributes)
  const sourceBuilding = record(data.building)
  const status = text(data.status)
  const currentLease = record(data.currentLease)
  const propertyId = text(data.id)
  const address = text(sourceBuilding.address ?? data.address)
  const buildingName = text(sourceBuilding.name) || address || '未分配楼宇'
  const occupancy: PropertySummary['occupancy'] = status === 'occupied' || currentLease.status === 'active'
    ? 'occupied'
    : ['under_offer', 'reserved'].includes(status) || ['executed', 'pending_signature'].includes(text(currentLease.status)) ? 'reserved' : 'vacant'
  return {
    id: propertyId,
    reference: text(data.reference),
    building: {
      id: text(sourceBuilding.id ?? data.buildingId) || `unassigned:${propertyId}`,
      cityId: text(data.cityId ?? sourceBuilding.cityId) || undefined,
      name: buildingName,
      address,
    },
    room: text(data.room ?? attributes.roomNumber) || '—',
    bedrooms: number(data.bedrooms),
    bathrooms: number(data.bathrooms),
    weeklyRent: number(data.weeklyRent),
    currency: text(data.currency) || 'AUD',
    occupancy,
    listingStatus: text(data.listingVisibility) === 'public' ? 'marketing' : 'private',
    openMaintenance: number(data.openMaintenance),
    reports: number(data.reports),
    coverImageUrl: Array.isArray(data.displayImageUrls) ? text(data.displayImageUrls[0]) || undefined : undefined,
    floorAreaSqm: data.floorAreaSqm == null ? undefined : number(data.floorAreaSqm),
    parkingSpaces: data.parkingSpaces == null ? undefined : number(data.parkingSpaces),
    isSynthetic: attributes.isSynthetic === true,
    lease: text(currentLease.id) ? { id: text(currentLease.id), reference: text(currentLease.reference), status: text(currentLease.status), endsOn: text(currentLease.endsOn) } : undefined,
  }
}

function getCookie(name: string): string | undefined {
  return document.cookie.split('; ').find((part) => part.startsWith(`${name}=`))?.split('=').slice(1).join('=')
}

function csrfHeaders(): HeadersInit {
  const csrf = getCookie('safescan_csrf')
  return csrf ? { 'X-CSRF-Token': decodeURIComponent(csrf) } : {}
}

async function apiError(response: Response): Promise<ApiError> {
  let error: ApiErrorShape = { code: 'unexpected_error', message: '请求未能完成，请稍后重试', retryable: response.status >= 500 }
  try {
    const body = await response.json() as { error?: unknown }
    const source = record(body.error)
    if (source.code && source.message) {
      error = {
        code: text(source.code),
        message: text(source.message),
        requestId: text(source.correlation_id ?? source.requestId) || undefined,
        retryable: Boolean(source.retryable),
        details: record(source.details),
        fieldErrors: camelize<ApiErrorShape['fieldErrors']>(source.field_errors ?? source.fieldErrors),
      }
    }
  } catch {
    // Preserve the safe fallback when an upstream returns non-JSON.
  }
  return new ApiError(response.status, error)
}

export class RealStaffPortalClient implements StaffPortalClient {
  private token: string | null = null
  private refreshRequest: Promise<Session> | null = null
  private unauthorizedHandler: (() => void) | null = null

  setAccessToken(token: string | null) { this.token = token }
  setUnauthorizedHandler(handler: (() => void) | null) { this.unauthorizedHandler = handler }

  private async request<T>(path: string, init: RequestInit = {}, retry401 = true): Promise<T> {
    const headers = new Headers(init.headers)
    if (!headers.has('Accept')) headers.set('Accept', 'application/json')
    if (init.body) headers.set('Content-Type', 'application/json')
    if (this.token) headers.set('Authorization', `Bearer ${this.token}`)

    let response: Response
    try {
      response = await fetch(path, { ...init, headers, credentials: 'include' })
    } catch {
      throw new ApiError(0, { code: 'network_error', message: '无法连接服务器，请检查网络后重试', retryable: true })
    }

    if (response.status === 401 && retry401 && path !== '/api/v1/auth/refresh') {
      try {
        await this.refresh()
        return this.request<T>(path, init, false)
      } catch {
        this.unauthorizedHandler?.()
        throw new ApiError(401, { code: 'session_inactive', message: '登录已过期，请重新登录', retryable: false })
      }
    }
    if (!response.ok) throw await apiError(response)
    if (response.status === 204) return undefined as T
    if (headers.get('Accept') === 'application/pdf') {
      if (!response.headers.get('Content-Type')?.includes('application/pdf')) throw new ApiError(502, { code: 'invalid_pdf', message: '合同文档响应格式不正确', retryable: true })
      return response.blob() as Promise<T>
    }
    if (headers.get('Accept') === 'image/*') {
      if (!response.headers.get('Content-Type')?.startsWith('image/')) throw new ApiError(502, { code: 'invalid_image', message: '房源图片响应格式不正确', retryable: true })
      return response.blob() as Promise<T>
    }
    return response.json() as Promise<T>
  }

  async login(input: LoginInput): Promise<Session> {
    const response = await this.request<Envelope<unknown>>('/api/v1/auth/login', {
      method: 'POST',
      body: JSON.stringify({ ...input, remember_me: false, device_label: 'SafeScan Staff Web' }),
    }, false)
    return normalizeSession(response.data)
  }

  refresh(): Promise<Session> {
    if (!this.refreshRequest) {
      this.refreshRequest = this.request<Envelope<unknown>>('/api/v1/auth/refresh', {
        method: 'POST', headers: csrfHeaders(),
      }, false).then((response) => {
        const session = normalizeSession(response.data)
        this.token = session.accessToken
        return session
      }).finally(() => { this.refreshRequest = null })
    }
    return this.refreshRequest
  }

  async logout(): Promise<void> {
    try {
      await this.request<void>('/api/v1/auth/logout', { method: 'POST', headers: csrfHeaders() }, false)
    } finally {
      this.token = null
    }
  }

  async bootstrap(): Promise<BootstrapData> {
    return normalizeBootstrap((await this.request<Envelope<unknown>>('/api/v1/staff/bootstrap')).data)
  }

  private async allItems(path: string): Promise<unknown[]> {
    const items = new Map<string, unknown>()
    let cursor: string | undefined
    const seenCursors = new Set<string>()
    do {
      const params = new URLSearchParams({ limit: '100' })
      if (cursor) params.set('cursor', cursor)
      const response = await this.request<Envelope<unknown>>(`${path}?${params}`)
      const page = normalizedRecord(response.data)
      for (const item of pageItems<unknown>(page)) {
        const id = text(record(item).id)
        items.set(id || `unidentified:${items.size}`, item)
      }
      cursor = text(page.nextCursor) || undefined
      if (cursor && seenCursors.has(cursor)) throw new ApiError(502, { code: 'invalid_pagination', message: '列表分页加载异常，请刷新后重试', retryable: true })
      if (cursor) seenCursors.add(cursor)
    } while (cursor)
    return [...items.values()]
  }

  async listProperties(): Promise<PropertySummary[]> {
    return (await this.allItems('/api/v1/staff/properties')).map(normalizeProperty)
  }

  async getPropertyDetail(id: string): Promise<PropertyDetail> {
    const response = await this.request<Envelope<unknown> & { meta?: { partial_errors?: Array<{ component: string }> } }>(`/api/v1/staff/properties/${encodeURIComponent(id)}`)
    const data = normalizedRecord(response.data)
    const leasePage = normalizedRecord(data.leases)
    const maintenancePage = normalizedRecord(data.maintenance ?? data.openMaintenance)
    return {
      property: normalizeProperty(data.property),
      leaseHistoryNextCursor: text(leasePage.nextCursor) || undefined,
      leaseHistoryTotal: typeof leasePage.total === 'number' ? leasePage.total : undefined,
      maintenanceHistoryNextCursor: text(maintenancePage.nextCursor) || undefined,
      maintenanceHistoryTotal: typeof maintenancePage.total === 'number' ? maintenancePage.total : undefined,
      leases: pageItems<unknown>(data.leases).map(normalizeOrder),
      maintenance: pageItems<unknown>(data.maintenance ?? data.openMaintenance).map(normalizeMaintenanceOrder),
      inspections: pageItems<PropertyDetail['inspections'][number]>(data.inspections),
      attributes: record(record(data.property).attributes),
      partialErrors: response.meta?.partial_errors?.map((error) => text(record(error).component)).filter(Boolean) ?? [],
    }
  }

  async getMaintenanceOrder(id: string): Promise<MaintenanceOrder> {
    return normalizeMaintenanceOrder((await this.request<Envelope<unknown>>(`/api/v1/staff/maintenance-orders/${encodeURIComponent(id)}`)).data)
  }

  async listOrderPage(cursor?: string, stage?: string): Promise<ResultPage<OrderSummary>> {
    const statuses: Record<string, string> = { application: 'draft', pending_signature: 'pending_signature', executed: 'executed,active', ended: 'ended,terminated,cancelled,expired' }
    const params = new URLSearchParams({ limit: '50' })
    if (cursor) params.set('cursor', cursor)
    if (stage && statuses[stage]) params.set('status', statuses[stage])
    const page = normalizedRecord((await this.request<Envelope<unknown>>(`/api/v1/staff/orders?${params}`)).data)
    return { items: pageItems<unknown>(page).map(normalizeOrder), nextCursor: text(page.nextCursor) || undefined, total: typeof page.total === 'number' ? page.total : undefined }
  }

  async getLeasePdf(leaseId: string): Promise<Blob> {
    return this.request<Blob>(`/api/v1/staff/leases/${encodeURIComponent(leaseId)}/document/pdf`, { headers: { Accept: 'application/pdf' } })
  }

  async getPropertyImage(url: string): Promise<Blob> {
    if (!/^\/api\/v1\/staff\/properties\/[^/?#]+\/images\/[^/?#]+$/.test(url)) throw new Error('房源图片地址无效')
    return this.request<Blob>(url, { headers: { Accept: 'image/*' } })
  }

  async listOrders(): Promise<OrderSummary[]> {
    return (await this.allItems('/api/v1/staff/orders')).map(normalizeOrder)
  }

  async listMaintenanceOrders(): Promise<MaintenanceOrder[]> {
    return (await this.listMaintenancePage()).items
  }

  async listMaintenancePage(options: MaintenancePageOptions = {}): Promise<MaintenancePageResult> {
    const params = new URLSearchParams({ limit: '50' })
    if (options.status) params.set('status', options.status)
    if (options.cursor) params.set('cursor', options.cursor)
    const response = await this.request<Envelope<unknown>>(`/api/v1/staff/maintenance-orders?${params}`)
    const page = normalizedRecord(response.data)
    return { items: pageItems<unknown>(page).map(normalizeMaintenanceOrder), nextCursor: text(page.nextCursor) || undefined, contextUnavailable: Boolean(response.meta?.partial_errors?.length) }
  }

  async transitionMaintenanceOrder(id: string, status: MaintenanceStatus, version: number): Promise<MaintenanceOrder> {
    return normalizeMaintenanceOrder((await this.request<Envelope<unknown>>(`/api/v1/staff/maintenance-orders/${id}/transitions`, {
      method: 'POST',
      headers: { 'Idempotency-Key': crypto.randomUUID() },
      body: JSON.stringify({ to_status: status, version }),
    })).data)
  }

  async listStaff(): Promise<StaffAccount[]> {
    const items = pageItems<unknown>((await this.request<Envelope<unknown>>('/api/v1/staff/admin/staff')).data)
    return items.map(normalizeStaffAccount)
  }

  async createPropertyReport(propertyId: string): Promise<{ reportId: string }> {
    const report = camelize<{ id: string }>((await this.request<Envelope<unknown>>(`/api/v1/staff/properties/${propertyId}/reports`, {
      method: 'POST', headers: { 'Idempotency-Key': crypto.randomUUID() }, body: JSON.stringify({}),
    })).data)
    return { reportId: report.id }
  }
}
