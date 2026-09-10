import type { ApplicationInput, ApplicationView, BootstrapView, LeaseView, LoginInput, MaintenanceOrderView, PropertyHomeView, PropertyView, RegisterInput, ReportDetail, ReportJobView, TenantPortalApi } from './contracts'
import { ApiError } from './contracts'

type Envelope<T> = { data: T }

function csrfToken() {
  return document.cookie.split('; ').find((part) => part.startsWith('csrf_token='))?.split('=').slice(1).join('=') ?? ''
}

function mapProperty(raw: Record<string, unknown>): PropertyView {
  const attributes = (raw.attributes ?? {}) as Record<string, unknown>
  return { id: String(raw.id), reference: String(raw.reference), address: String(raw.address), suburb: String(raw.suburb ?? raw.address), bedrooms: Number(raw.bedrooms), bathrooms: Number(raw.bathrooms), parking: Number(raw.parking ?? 0), weeklyRent: Number(raw.weekly_rent), currency: 'AUD', availability: raw.availability === 'under_offer' ? 'under_offer' : 'available', description: String(raw.description ?? ''), features: Array.isArray(attributes.features) ? attributes.features.map(String) : [], accent: 'ocean' }
}

async function parseError(response: Response): Promise<ApiError> {
  let payload: { error?: { code?: string; message?: string; retryable?: boolean } } = {}
  try { payload = await response.json() } catch { /* empty or non-JSON error */ }
  const fallback: Record<number, string> = { 401: '登录已过期，请重新登录', 403: '当前身份不能执行此操作', 404: '没有找到该资源', 409: '数据已发生变化，请刷新后重试', 422: '请检查提交内容', 500: '服务暂时不可用' }
  return new ApiError(response.status, payload.error?.code ?? 'request_failed', payload.error?.message ?? fallback[response.status] ?? '请求失败', payload.error?.retryable)
}

export class HttpTenantPortalApi implements TenantPortalApi {
  private accessToken: string | null = null
  private refreshPromise: Promise<void> | null = null

  private async refresh() {
    if (!this.refreshPromise) this.refreshPromise = (async () => {
      const response = await fetch('/api/v1/auth/refresh', { method: 'POST', credentials: 'include', headers: { 'X-CSRF-Token': csrfToken() } })
      if (!response.ok) throw await parseError(response)
      const payload = await response.json() as Envelope<{ access_token: string; portal: string }>
      if (payload.data.portal !== 'tenant') throw new ApiError(403, 'wrong_portal', '此账号不属于 Tenant Portal')
      this.accessToken = payload.data.access_token
    })().finally(() => { this.refreshPromise = null })
    return this.refreshPromise
  }

  private async request<T>(path: string, init: RequestInit = {}, retry401 = true): Promise<T> {
    const headers = new Headers(init.headers)
    if (!(init.body instanceof File)) headers.set('Content-Type', 'application/json')
    if (this.accessToken) headers.set('Authorization', `Bearer ${this.accessToken}`)
    let response: Response
    try { response = await fetch(path, { ...init, headers, credentials: 'include' }) } catch { throw new ApiError(0, 'network_error', '网络连接失败，请检查连接后重试', true) }
    if (response.status === 401 && retry401 && this.accessToken) { await this.refresh(); return this.request(path, init, false) }
    if (!response.ok) throw await parseError(response)
    if (response.status === 204) return undefined as T
    const payload = await response.json() as Envelope<T>
    return payload.data
  }

  bootstrap() { return this.request<BootstrapView>('/api/v1/tenant/bootstrap') }
  async restoreSession() { try { await this.refresh() } catch (error) { if (error instanceof ApiError && error.status === 401) { this.accessToken = null; return this.bootstrap() } throw error } return this.bootstrap() }
  async login(input: LoginInput) { const payload = await this.request<{ access_token: string; portal: string }>('/api/v1/auth/login', { method: 'POST', body: JSON.stringify({ email: input.email, password: input.password, remember_me: input.rememberMe ?? false }) }, false); if (payload.portal !== 'tenant') throw new ApiError(403, 'wrong_portal', '请前往 Staff Portal 登录'); this.accessToken = payload.access_token; return this.bootstrap() }
  async register(input: RegisterInput) { const payload = await this.request<{ access_token: string; portal: string }>('/api/v1/auth/register', { method: 'POST', headers: { 'Idempotency-Key': crypto.randomUUID() }, body: JSON.stringify({ email: input.email, username: input.username, password: input.password, accepted_terms_version: input.acceptedTermsVersion, locale: 'zh-CN' }) }, false); this.accessToken = payload.access_token; return this.bootstrap() }
  async logout() { try { await this.request('/api/v1/auth/logout', { method: 'POST', headers: { 'X-CSRF-Token': csrfToken() } }, false) } finally { this.accessToken = null } }
  async listProperties() { const raw = await this.request<Record<string, unknown>[]>('/api/v1/tenant/properties'); return raw.map(mapProperty) }
  async getProperty(id: string) { return mapProperty(await this.request<Record<string, unknown>>(`/api/v1/tenant/properties/${encodeURIComponent(id)}`)) }
  contactProperty(id: string, message: string) { return this.request<{ caseId: string }>(`/api/v1/tenant/properties/${encodeURIComponent(id)}/contact`, { method: 'POST', headers: { 'Idempotency-Key': crypto.randomUUID() }, body: JSON.stringify({ message, client_message_id: crypto.randomUUID() }) }) }
  createApplication(input: ApplicationInput) { return this.request<ApplicationView>('/api/v1/tenant/applications', { method: 'POST', headers: { 'Idempotency-Key': crypto.randomUUID() }, body: JSON.stringify({ case_id: input.caseId, property_id: input.propertyId, desired_start_on: input.desiredStartOn, term_months: input.termMonths, occupants: input.occupants, note: input.note }) }) }
  listApplications() { return this.request<ApplicationView[]>('/api/v1/tenant/applications') }
  getApplication(id: string) { return this.request<ApplicationView>(`/api/v1/tenant/applications/${encodeURIComponent(id)}`) }
  listLeases() { return this.request<LeaseView[]>('/api/v1/tenant/leases') }
  getCurrentProperty() { return this.request<PropertyHomeView>('/api/v1/tenant/my-property') }
  getHistoricalProperty(id: string) { return this.request<PropertyHomeView>(`/api/v1/tenant/leases/${encodeURIComponent(id)}/property`) }
  createMaintenance(summary: string, description: string, priority: MaintenanceOrderView['priority']) { return this.request<MaintenanceOrderView>('/api/v1/tenant/maintenance-orders', { method: 'POST', headers: { 'Idempotency-Key': crypto.randomUUID() }, body: JSON.stringify({ summary, description, priority }) }) }
  getReport(id: string) { return this.request<ReportDetail>(`/api/v1/tenant/reports/${encodeURIComponent(id)}`) }
  async startReport(file: File, attributes: Record<string, boolean>, onProgress: (job: ReportJobView) => void) {
    const draft = await this.request<{ id: string }>('/api/v1/tenant/my-property/reports', { method: 'POST', headers: { 'Idempotency-Key': crypto.randomUUID() }, body: JSON.stringify({}) })
    const uploaded = await this.request<{ id: string }>(`/api/v1/tenant/reports/${draft.id}/files/videos`, { method: 'POST', headers: { 'Content-Type': file.type || 'video/mp4', 'X-File-Name': encodeURIComponent(file.name), 'Idempotency-Key': crypto.randomUUID() }, body: file })
    let job = await this.request<ReportJobView>(`/api/v1/tenant/reports/${draft.id}/jobs`, { method: 'POST', headers: { 'Idempotency-Key': crypto.randomUUID() }, body: JSON.stringify({ input_file_id: uploaded.id, attributes }) })
    onProgress(job)
    while (job.status === 'queued' || job.status === 'running') { await new Promise((resolve) => setTimeout(resolve, 1200)); job = await this.request<ReportJobView>(`/api/v1/tenant/report-jobs/${job.id}`); onProgress(job) }
    if (job.status === 'failed') throw new ApiError(500, 'report_generation_failed', job.error ?? '报告生成失败')
    return this.getReport(job.reportId)
  }
}
