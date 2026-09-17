import type {
  ApplicationInput,
  ApplicationView,
  BootstrapView,
  CustomerStatus,
  InvoiceView,
  LeaseView,
  LoginInput,
  MaintenanceOrderView,
  PropertyHomeView,
  PropertyView,
  RegisterInput,
  ReportDetail,
  ReportJobView,
  ReportSummary,
  TenantPortalApi,
} from './contracts'
import { ApiError } from './contracts'

type JsonRecord = Record<string, unknown>

function record(value: unknown): JsonRecord {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return {}
  return Object.fromEntries(Object.entries(value))
}

function text(value: unknown, fallback = ''): string {
  return typeof value === 'string' || typeof value === 'number' ? String(value) : fallback
}

function optionalText(value: unknown): string | undefined {
  const result = text(value)
  return result || undefined
}

function number(value: unknown, fallback = 0): number {
  const result = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(result) ? result : fallback
}

function stringList(value: unknown): string[] {
  return Array.isArray(value) ? value.map((item) => text(item)).filter(Boolean) : []
}

function pageItems(value: unknown): unknown[] {
  if (Array.isArray(value)) return value
  const items = record(value).items
  return Array.isArray(items) ? items : []
}

function invalidResponse(field: string): ApiError {
  return new ApiError(502, 'invalid_upstream_response', `服务返回了无效的 ${field} 数据`, true)
}

function applicationStatus(value: unknown): ApplicationView['status'] {
  switch (value) {
    case 'draft': case 'submitted': case 'reviewing': case 'approved': case 'rejected':
    case 'withdrawn': case 'ineligible': case 'expired': return value
    default: throw invalidResponse('申请状态')
  }
}

function leaseStatus(value: unknown): LeaseView['status'] {
  switch (value) {
    case 'pending_signature': case 'executed': case 'active': case 'ended': case 'terminated': return value
    default: throw invalidResponse('租约状态')
  }
}

function maintenanceStatus(value: unknown): MaintenanceOrderView['status'] {
  switch (value) {
    case 'open': case 'assigned': case 'in_progress': case 'blocked': case 'completed': case 'cancelled': return value
    default: throw invalidResponse('维修状态')
  }
}

function maintenancePriority(value: unknown): MaintenanceOrderView['priority'] {
  if (value === 'low') return 'low'
  if (value === 'urgent' || value === 'high') return 'urgent'
  return 'normal'
}

function reportStatus(value: unknown): ReportSummary['status'] {
  switch (value) {
    case 'draft': return 'draft'
    case 'queued': case 'running': case 'processing': return 'processing'
    case 'active': case 'completed': return 'active'
    case 'failed': case 'cancelled': return 'failed'
    default: throw invalidResponse('报告状态')
  }
}

function jobStatus(value: unknown): ReportJobView['status'] {
  switch (value) {
    case 'queued': case 'running': case 'completed': case 'failed': return value
    case 'active': return 'completed'
    default: throw invalidResponse('报告任务状态')
  }
}

function csrfToken() {
  return document.cookie.split('; ').find((part) => part.startsWith('safescan_csrf='))?.split('=').slice(1).join('=') ?? ''
}

function mapProperty(raw: unknown): PropertyView {
  const source = record(raw)
  const attributes = record(source.attributes)
  return {
    id: text(source.id),
    reference: text(source.reference, text(source.id)),
    address: text(source.address, '房源地址暂不可用'),
    suburb: text(source.suburb, text(source.address)),
    bedrooms: number(source.bedrooms),
    bathrooms: number(source.bathrooms),
    parking: number(source.parking ?? source.parking_spaces),
    weeklyRent: number(source.weekly_rent ?? source.weeklyRent),
    currency: 'AUD',
    availability: source.availability === 'under_offer' ? 'under_offer' : 'available',
    description: text(source.description ?? attributes.description),
    features: stringList(attributes.features),
    accent: text(source.accent, 'ocean'),
  }
}

function mapPropertyReference(raw: unknown, propertyId: unknown): ApplicationView['property'] {
  const source = record(raw)
  const id = text(source.id, text(propertyId))
  const reference = text(source.reference, id)
  return {
    id,
    reference,
    address: text(source.address, reference ? `房源 ${reference}` : '房源信息暂不可用'),
    suburb: text(source.suburb, text(source.address)),
  }
}

function mapApplication(raw: unknown): ApplicationView {
  const source = record(raw)
  const id = text(source.id)
  return {
    id,
    reference: text(source.reference, id),
    property: mapPropertyReference(source.property, source.property_id),
    status: applicationStatus(source.status),
    desiredStartOn: text(source.desired_start_on ?? source.desiredStartOn),
    termMonths: number(source.term_months ?? source.termMonths),
    occupants: number(source.occupants),
    note: optionalText(source.note),
    submittedAt: optionalText(source.submitted_at ?? source.submittedAt),
    updatedAt: text(source.updated_at ?? source.updatedAt ?? source.submitted_at),
    version: number(source.version),
  }
}

function mapLease(raw: unknown): LeaseView {
  const source = record(raw)
  const document = record(source.document)
  const id = text(source.id)
  return {
    id,
    reference: text(source.reference, id),
    property: mapPropertyReference(source.property, source.property_id),
    status: leaseStatus(source.status),
    startsOn: text(source.starts_on ?? source.startsOn),
    endsOn: text(source.ends_on ?? source.endsOn),
    weeklyRent: number(source.weekly_rent ?? source.weeklyRent),
    currency: 'AUD',
    executedAt: optionalText(source.executed_at ?? source.executedAt),
    document: {
      id: text(document.id),
      version: number(document.version),
      termsDigest: text(document.terms_digest ?? document.termsDigest),
    },
  }
}

function mapInvoice(raw: unknown): InvoiceView {
  const source = record(raw)
  const reference = text(source.reference, text(source.id))
  const period = text(source.period) || [text(source.period_start), text(source.period_end)].filter(Boolean).join(' — ') || text(source.due_on)
  const rawStatus = text(source.status)
  const status: InvoiceView['status'] = rawStatus === 'paid' ? 'paid' : rawStatus === 'scheduled' ? 'scheduled' : 'due'
  return {
    id: text(source.id, reference || period),
    period,
    amount: number(source.amount),
    status,
    paidAt: optionalText(source.paid_at ?? source.paidAt),
  }
}

function mapMaintenance(raw: unknown): MaintenanceOrderView {
  const source = record(raw)
  const id = text(source.id)
  return {
    id,
    reference: text(source.reference, id),
    summary: text(source.summary),
    priority: maintenancePriority(source.priority),
    status: maintenanceStatus(source.status),
    updatedAt: text(source.updated_at ?? source.updatedAt ?? source.created_at),
  }
}

function mapReportSummary(raw: unknown): ReportSummary {
  const source = record(raw)
  const id = text(source.id)
  const validation = source.validation_passed ?? source.validationPassed
  return {
    id,
    title: text(source.title, `报告 ${id}`),
    propertyId: text(source.property_id ?? source.propertyId),
    sourceLeaseId: text(source.source_lease_id ?? source.sourceLeaseId),
    status: reportStatus(source.status),
    completedAt: optionalText(source.completed_at ?? source.completedAt),
    validationPassed: typeof validation === 'boolean' ? validation : undefined,
  }
}

function mapReportDetail(raw: unknown): ReportDetail {
  const source = record(raw)
  const payload = record(source.report)
  const regionSource = source.regions ?? source.region_info ?? payload.regions
  const regions = (Array.isArray(regionSource) ? regionSource : []).map((value) => {
    const region = record(value)
    const nameValue = region.name ?? region.region_name ?? region.regionName
    const name = Array.isArray(nameValue) ? stringList(nameValue).join(' / ') : text(nameValue, '未命名区域')
    const rawRisk = text(region.risk ?? region.risk_level ?? region.riskLevel).toLowerCase()
    const risk: ReportDetail['regions'][number]['risk'] = rawRisk === 'high' ? 'high' : rawRisk === 'medium' ? 'medium' : 'low'
    const findings = [...stringList(region.findings), ...stringList(region.generalHazards), ...stringList(region.specificHazards), ...stringList(region.potentialHazards)]
    const suggestions = [...stringList(region.suggestions), ...stringList(region.recommendations)]
    return { name, risk, findings, suggestions }
  })
  return {
    ...mapReportSummary(source),
    overview: text(source.overview ?? payload.overview ?? payload.summary),
    regions,
  }
}

function mapReportJob(raw: unknown): ReportJobView {
  const source = record(raw)
  const error = record(source.error)
  return {
    id: text(source.id),
    reportId: text(source.report_id ?? source.reportId),
    status: jobStatus(source.status),
    stage: text(source.stage),
    progressPercent: number(source.progress_percent ?? source.progressPercent),
    error: optionalText(source.error) ?? optionalText(error.message ?? error.code),
  }
}

function mapPropertyHome(raw: unknown): PropertyHomeView {
  const source = record(raw)
  return {
    lease: mapLease(source.lease),
    invoices: pageItems(source.invoices).map(mapInvoice),
    maintenance: pageItems(source.maintenance).map(mapMaintenance),
    reports: pageItems(source.reports).map(mapReportSummary),
  }
}

function mapCapabilities(scopes: unknown, authenticated: boolean): BootstrapView['capabilities'] {
  const source = new Set(Array.isArray(scopes) ? scopes.map(String) : [])
  const capabilities: BootstrapView['capabilities'] = []
  if (authenticated) capabilities.push('contact:create', 'agent:access')
  if (source.has('property:read_market')) capabilities.push('property:read')
  if (source.has('application:self:read')) capabilities.push('application:read')
  if (source.has('application:self:create')) capabilities.push('application:create')
  if (source.has('lease:self:read') || source.has('lease:self:read_history')) capabilities.push('lease:read', 'my-property:read')
  if (source.has('maintenance:self:create')) capabilities.push('maintenance:read', 'maintenance:create')
  if (source.has('report:self:read')) capabilities.push('report:read-current')
  if (source.has('report:self:create')) capabilities.push('report:create')
  if (source.has('report:self:read_history')) capabilities.push('report:read-history')
  return [...new Set(capabilities)]
}

function customerStatus(value: unknown): CustomerStatus {
  switch (value) {
    case 'prospect': case 'tenant': case 'former_tenant': return value
    default: throw invalidResponse('客户状态')
  }
}

function mapBootstrap(raw: unknown): BootstrapView {
  const data = record(raw)
  const source = record(data.customer)
  const authenticated = source.authenticated === true
  const statusVersion = number(source.status_version ?? source.statusVersion ?? data.status_version ?? data.statusVersion)
  return {
    customer: authenticated ? {
      id: text(source.id),
      username: text(source.username, 'SafeScan Customer'),
      email: text(source.email),
      status: customerStatus(source.status),
      statusVersion,
    } : null,
    capabilities: mapCapabilities(data.capabilities, authenticated),
    statusVersion,
  }
}

async function parseError(response: Response): Promise<ApiError> {
  let payload: JsonRecord = {}
  try { payload = record(await response.json()) } catch { /* empty or non-JSON error */ }
  const error = record(payload.error)
  const fallback: Record<number, string> = { 401: '登录已过期，请重新登录', 403: '当前身份不能执行此操作', 404: '没有找到该资源', 409: '数据已发生变化，请刷新后重试', 422: '请检查提交内容', 500: '服务暂时不可用', 502: '上游服务返回无效响应', 503: '服务暂时不可用' }
  return new ApiError(response.status, text(error.code, 'request_failed'), text(error.message, fallback[response.status] ?? '请求失败'), Boolean(error.retryable))
}

export class HttpTenantPortalApi implements TenantPortalApi {
  private accessToken: string | null = null
  private refreshPromise: Promise<void> | null = null

  private async refresh() {
    if (!this.refreshPromise) this.refreshPromise = (async () => {
      const response = await fetch('/api/v1/auth/refresh', { method: 'POST', credentials: 'include', headers: { 'X-CSRF-Token': csrfToken() } })
      if (!response.ok) throw await parseError(response)
      const data = record(record(await response.json()).data)
      if (data.portal !== 'tenant') throw new ApiError(403, 'wrong_portal', '此账号不属于 Tenant Portal')
      this.accessToken = text(data.access_token)
    })().finally(() => { this.refreshPromise = null })
    return this.refreshPromise
  }

  private async request(path: string, init: RequestInit = {}, retry401 = true): Promise<unknown> {
    const headers = new Headers(init.headers)
    if (!(init.body instanceof File)) headers.set('Content-Type', 'application/json')
    if (this.accessToken) headers.set('Authorization', `Bearer ${this.accessToken}`)
    let response: Response
    try { response = await fetch(path, { ...init, headers, credentials: 'include' }) } catch { throw new ApiError(0, 'network_error', '网络连接失败，请检查连接后重试', true) }
    if (response.status === 401 && retry401 && this.accessToken) { await this.refresh(); return this.request(path, init, false) }
    if (!response.ok) throw await parseError(response)
    if (response.status === 204) return undefined
    return record(await response.json()).data
  }

  async bootstrap() { return mapBootstrap(await this.request('/api/v1/tenant/bootstrap')) }
  async restoreSession() {
    try {
      await this.refresh()
    } catch (error) {
      if (error instanceof ApiError && (error.status === 401 || error.code === 'csrf_invalid' || error.code === 'wrong_portal')) {
        this.accessToken = null
        return this.bootstrap()
      }
      throw error
    }
    return this.bootstrap()
  }
  async login(input: LoginInput) {
    const payload = record(await this.request('/api/v1/auth/login', { method: 'POST', body: JSON.stringify({ email: input.email, password: input.password, remember_me: input.rememberMe ?? false }) }, false))
    if (payload.portal !== 'tenant') throw new ApiError(403, 'wrong_portal', '请前往 Staff Portal 登录')
    this.accessToken = text(payload.access_token)
    return this.bootstrap()
  }
  async register(input: RegisterInput) {
    const payload = record(await this.request('/api/v1/auth/register', { method: 'POST', headers: { 'Idempotency-Key': crypto.randomUUID() }, body: JSON.stringify({ email: input.email, username: input.username, password: input.password, accepted_terms_version: input.acceptedTermsVersion, locale: 'zh-CN' }) }, false))
    this.accessToken = text(payload.access_token)
    return this.bootstrap()
  }
  async logout() { try { await this.request('/api/v1/auth/logout', { method: 'POST', headers: { 'X-CSRF-Token': csrfToken() } }, false) } finally { this.accessToken = null } }
  async listProperties() { return pageItems(await this.request('/api/v1/tenant/properties')).map(mapProperty) }
  async getProperty(id: string) { return mapProperty(await this.request(`/api/v1/tenant/properties/${encodeURIComponent(id)}`)) }
  async contactProperty(id: string, message: string) {
    const result = record(await this.request(`/api/v1/tenant/properties/${encodeURIComponent(id)}/contact`, { method: 'POST', headers: { 'Idempotency-Key': crypto.randomUUID() }, body: JSON.stringify({ message, client_message_id: crypto.randomUUID() }) }))
    return { caseId: text(result.case_id ?? result.caseId ?? result.id) }
  }
  async createApplication(input: ApplicationInput) {
    return mapApplication(await this.request('/api/v1/tenant/applications', { method: 'POST', headers: { 'Idempotency-Key': crypto.randomUUID() }, body: JSON.stringify({ case_id: input.caseId, property_id: input.propertyId, desired_start_on: input.desiredStartOn, term_months: input.termMonths, occupants: input.occupants, note: input.note }) }))
  }
  async listApplications() { return pageItems(await this.request('/api/v1/tenant/applications')).map(mapApplication) }
  async getApplication(id: string) { return mapApplication(await this.request(`/api/v1/tenant/applications/${encodeURIComponent(id)}`)) }
  async listLeases() { return pageItems(await this.request('/api/v1/tenant/leases')).map(mapLease) }
  async getCurrentProperty() { return mapPropertyHome(await this.request('/api/v1/tenant/my-property')) }
  async getHistoricalProperty(id: string) {
    const lease = mapLease(await this.request(`/api/v1/tenant/leases/${encodeURIComponent(id)}/property`))
    const [invoices, reports] = await Promise.all([
      this.request(`/api/v1/tenant/leases/${encodeURIComponent(id)}/invoices`),
      this.request(`/api/v1/tenant/leases/${encodeURIComponent(id)}/property/reports`),
    ])
    return { lease, invoices: pageItems(invoices).map(mapInvoice), maintenance: [], reports: pageItems(reports).map(mapReportSummary) }
  }
  async createMaintenance(summary: string, description: string, priority: MaintenanceOrderView['priority']) {
    return mapMaintenance(await this.request('/api/v1/tenant/maintenance-orders', { method: 'POST', headers: { 'Idempotency-Key': crypto.randomUUID() }, body: JSON.stringify({ summary, description, priority }) }))
  }
  async getReport(id: string) { return mapReportDetail(await this.request(`/api/v1/tenant/reports/${encodeURIComponent(id)}`)) }
  async startReport(file: File, attributes: Record<string, boolean>, onProgress: (job: ReportJobView) => void) {
    const draft = record(await this.request('/api/v1/tenant/my-property/reports', { method: 'POST', headers: { 'Idempotency-Key': crypto.randomUUID() }, body: JSON.stringify({}) }))
    const reportId = text(draft.id)
    const uploaded = record(await this.request(`/api/v1/tenant/reports/${reportId}/files/videos`, { method: 'POST', headers: { 'Content-Type': file.type || 'video/mp4', 'X-File-Name': encodeURIComponent(file.name), 'Idempotency-Key': crypto.randomUUID() }, body: file }))
    let job = mapReportJob(await this.request(`/api/v1/tenant/reports/${reportId}/jobs`, { method: 'POST', headers: { 'Idempotency-Key': crypto.randomUUID() }, body: JSON.stringify({ input_file_id: text(uploaded.id), attributes }) }))
    onProgress(job)
    while (job.status === 'queued' || job.status === 'running') {
      await new Promise((resolve) => setTimeout(resolve, 1200))
      job = mapReportJob(await this.request(`/api/v1/tenant/report-jobs/${job.id}`))
      onProgress(job)
    }
    if (job.status === 'failed') throw new ApiError(500, 'report_generation_failed', job.error ?? '报告生成失败')
    return this.getReport(job.reportId)
  }
}
