import {
  ApiError,
  type ApiErrorShape,
  type BootstrapData,
  type LoginInput,
  type MaintenanceOrder,
  type MaintenanceStatus,
  type OrderSummary,
  type PropertySummary,
  type Session,
  type StaffAccount,
  type StaffIdentity,
  type StaffPortalClient,
  type StaffRole,
} from '../types'

interface Envelope<T> { data: T }
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
      displayName: text(staff.display_name ?? staff.displayName ?? user.username),
      email: text(user.email ?? staff.email),
      staffCode: text(staff.staff_code ?? staff.staffCode),
      role: role(staffRole.code ?? staff.role),
    },
  }
}

function normalizeBootstrap(value: unknown): BootstrapData {
  const data = record(value)
  const staff = record(data.staff)
  const identity: StaffIdentity = {
    id: text(staff.id),
    displayName: text(staff.display_name ?? staff.displayName),
    email: text(staff.email),
    staffCode: text(staff.staff_code ?? staff.staffCode),
    role: role(record(staff.role).code ?? staff.role),
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
    headers.set('Accept', 'application/json')
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

  async listProperties(): Promise<PropertySummary[]> {
    return pageItems((await this.request<Envelope<unknown>>('/api/v1/staff/properties')).data)
  }

  async listOrders(): Promise<OrderSummary[]> {
    return pageItems((await this.request<Envelope<unknown>>('/api/v1/staff/orders')).data)
  }

  async listMaintenanceOrders(): Promise<MaintenanceOrder[]> {
    return pageItems((await this.request<Envelope<unknown>>('/api/v1/staff/maintenance-orders')).data)
  }

  async transitionMaintenanceOrder(id: string, status: MaintenanceStatus, version: number): Promise<MaintenanceOrder> {
    return camelize((await this.request<Envelope<unknown>>(`/api/v1/staff/maintenance-orders/${id}/transitions`, {
      method: 'POST',
      headers: { 'Idempotency-Key': crypto.randomUUID() },
      body: JSON.stringify({ to_status: status, version }),
    })).data)
  }

  async listStaff(): Promise<StaffAccount[]> {
    return pageItems((await this.request<Envelope<unknown>>('/api/v1/staff/admin/staff')).data)
  }

  async createPropertyReport(propertyId: string): Promise<{ reportId: string }> {
    const report = camelize<{ id: string }>((await this.request<Envelope<unknown>>(`/api/v1/staff/properties/${propertyId}/reports`, {
      method: 'POST', headers: { 'Idempotency-Key': crypto.randomUUID() }, body: JSON.stringify({}),
    })).data)
    return { reportId: report.id }
  }
}
