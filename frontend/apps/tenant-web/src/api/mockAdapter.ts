import type { ApplicationInput, ApplicationView, BootstrapView, Capability, CustomerStatus, LeaseView, PropertyHomeView, PropertyView, ReportDetail, ReportJobView, TenantPortalApi } from './contracts'
import { ApiError } from './contracts'

export type MockPersona = 'guest' | 'prospect' | 'executed_tenant' | 'active_tenant' | 'former_tenant'
const PERSONA_KEY = 'safescan.mock.persona.v1'

const properties: PropertyView[] = [
  { id: 'prop-harbour', reference: 'P-1001', address: '18 Harbour Street', suburb: 'Pyrmont NSW', bedrooms: 2, bathrooms: 1, parking: 1, weeklyRent: 720, currency: 'AUD', availability: 'available', description: '明亮的海港两居室，步行可达轻轨和海滨步道。', features: ['海港景观', '安全门禁', '空调', '宠物友好'], accent: 'ocean' },
  { id: 'prop-park', reference: 'P-1008', address: '7 Park Lane', suburb: 'Zetland NSW', bedrooms: 1, bathrooms: 1, parking: 0, weeklyRent: 590, currency: 'AUD', availability: 'available', description: '安静内庭一居室，带阳台与共享屋顶花园。', features: ['朝北阳台', '屋顶花园', '健身房'], accent: 'sage' },
  { id: 'prop-garden', reference: 'P-1012', address: '42 Garden Avenue', suburb: 'Chatswood NSW', bedrooms: 3, bathrooms: 2, parking: 2, weeklyRent: 980, currency: 'AUD', availability: 'under_offer', description: '适合家庭的三居住宅，靠近学校、车站和公园。', features: ['双车位', '储物间', '学区'], accent: 'sand' },
]

const applicationSeed: ApplicationView[] = [
  { id: 'app-001', reference: 'APP-202609-001', property: properties[0], status: 'reviewing', desiredStartOn: '2026-10-01', termMonths: 12, occupants: 2, note: '希望安排工作日下午看房。', submittedAt: '2026-09-07T09:30:00Z', updatedAt: '2026-09-09T02:12:00Z', version: 3 },
  { id: 'app-legacy', reference: 'APP-202512-018', property: properties[1], status: 'rejected', desiredStartOn: '2026-01-15', termMonths: 6, occupants: 1, updatedAt: '2025-12-20T01:00:00Z', version: 4 },
]

const leaseFor = (status: LeaseView['status'], historic = false): LeaseView => ({
  id: historic ? 'lease-history' : 'lease-current', reference: historic ? 'L-2025-044' : 'L-2026-091', property: historic ? properties[1] : properties[0], status,
  startsOn: historic ? '2025-01-10' : status === 'executed' ? '2026-10-01' : '2026-08-01', endsOn: historic ? '2025-12-31' : '2027-07-31', weeklyRent: historic ? 560 : 720, currency: 'AUD', executedAt: historic ? '2025-01-03T04:20:00Z' : '2026-07-28T06:00:00Z', document: { id: historic ? 'doc-history' : 'doc-current', version: 1, termsDigest: 'sha256:9f6d…a43c' },
})

const report: ReportDetail = { id: 'report-001', title: '入住安全检查报告', propertyId: 'prop-harbour', sourceLeaseId: 'lease-current', status: 'active', completedAt: '2026-08-04T11:20:00Z', validationPassed: true, overview: '整体状况良好。厨房烟雾报警器和阳台门锁需要关注。', regions: [{ name: '厨房', risk: 'medium', findings: ['烟雾报警器距灶台较近', '地面无明显绊倒风险'], suggestions: ['确认报警器测试记录', '烹饪时保持通风'] }, { name: '客厅与阳台', risk: 'low', findings: ['采光良好', '阳台门锁工作正常'], suggestions: ['定期检查门锁'] }] }

function capabilities(persona: MockPersona): Capability[] {
  const common: Capability[] = ['property:read']
  if (persona === 'guest') return common
  common.push('contact:create', 'application:read', 'lease:read', 'agent:access')
  if (persona === 'prospect' || persona === 'former_tenant') common.push('application:create')
  if (persona === 'executed_tenant') common.push('my-property:read')
  if (persona === 'active_tenant') common.push('my-property:read', 'maintenance:read', 'maintenance:create', 'report:read-current', 'report:create')
  if (persona === 'former_tenant') common.push('my-property:read', 'maintenance:read', 'report:read-history')
  return common
}

const statusFor = (persona: MockPersona): CustomerStatus => persona === 'former_tenant' ? 'former_tenant' : persona === 'prospect' ? 'prospect' : 'tenant'

export class MockTenantPortalApi implements TenantPortalApi {
  private applications = [...applicationSeed]
  private persona: MockPersona

  constructor(persona?: MockPersona) {
    this.persona = persona ?? (localStorage.getItem(PERSONA_KEY) as MockPersona | null) ?? 'guest'
  }

  setPersona(persona: MockPersona) { this.persona = persona; localStorage.setItem(PERSONA_KEY, persona) }
  private view(): BootstrapView {
    if (this.persona === 'guest') return { customer: null, capabilities: capabilities(this.persona), statusVersion: 0 }
    return { customer: { id: 'customer-demo', username: this.persona === 'prospect' ? 'Alex Chen' : 'Mia Zhang', email: `${this.persona}@demo.safescan.local`, status: statusFor(this.persona), statusVersion: 4 }, capabilities: capabilities(this.persona), statusVersion: 4 }
  }
  async bootstrap() { return this.view() }
  async restoreSession() { return this.view() }
  async login(input: { email: string }) {
    const persona: MockPersona = input.email.includes('former') ? 'former_tenant' : input.email.includes('executed') ? 'executed_tenant' : input.email.includes('active') || input.email.includes('tenant') ? 'active_tenant' : 'prospect'
    this.setPersona(persona); return this.view()
  }
  async register() { this.setPersona('prospect'); return this.view() }
  async logout() { this.setPersona('guest') }
  async listProperties() { return properties }
  async getProperty(id: string) { const item = properties.find((p) => p.id === id); if (!item) throw new ApiError(404, 'resource_not_found', '没有找到该房源'); return item }
  async contactProperty(id: string, message: string) { if (!this.view().customer) throw new ApiError(401, 'authentication_required', '请先登录'); if (!message.trim()) throw new ApiError(422, 'validation_error', '请填写留言'); return { caseId: `case-${id}` } }
  async createApplication(input: ApplicationInput) { if (!capabilities(this.persona).includes('application:create')) throw new ApiError(403, 'customer_not_eligible_for_lease', '当前身份不能创建申请'); const property = await this.getProperty(input.propertyId); const item: ApplicationView = { ...input, id: `app-${Date.now()}`, reference: `APP-DEMO-${this.applications.length + 1}`, property, status: 'submitted', submittedAt: new Date().toISOString(), updatedAt: new Date().toISOString(), version: 1 }; this.applications.unshift(item); return item }
  async listApplications() { return this.applications }
  async getApplication(id: string) { const item = this.applications.find((a) => a.id === id); if (!item) throw new ApiError(404, 'resource_not_found', '没有找到该申请'); return item }
  async listLeases() { if (this.persona === 'prospect') return []; if (this.persona === 'former_tenant') return [leaseFor('ended', true)]; if (this.persona === 'executed_tenant') return [leaseFor('executed')]; return [leaseFor('active'), leaseFor('ended', true)] }
  private home(lease: LeaseView, historical = false): PropertyHomeView { return { lease, invoices: historical ? [{ id: 'inv-old', period: '2025-12', amount: 2240, status: 'paid', paidAt: '2025-12-02' }] : [{ id: 'inv-1', period: '2026-09', amount: 2880, status: 'paid', paidAt: '2026-09-01' }, { id: 'inv-2', period: '2026-10', amount: 2880, status: 'scheduled' }], maintenance: lease.status === 'active' || historical ? [{ id: 'maint-1', reference: 'M-2041', summary: '浴室水龙头滴水', priority: 'normal', status: historical ? 'completed' : 'assigned', updatedAt: '2026-09-08T08:00:00Z' }] : [], reports: lease.status === 'active' || historical ? [{ ...report, sourceLeaseId: lease.id, propertyId: lease.property.id }] : [] } }
  async getCurrentProperty() { if (this.persona === 'executed_tenant') return this.home(leaseFor('executed')); if (this.persona === 'active_tenant') return this.home(leaseFor('active')); throw new ApiError(404, 'resource_not_found', '当前没有租住房产') }
  async getHistoricalProperty(leaseId: string) { if (leaseId !== 'lease-history') throw new ApiError(404, 'resource_not_found', '没有找到历史租约'); return this.home(leaseFor('ended', true), true) }
  async createMaintenance(summary: string, _description: string, priority: 'low' | 'normal' | 'urgent') { if (!capabilities(this.persona).includes('maintenance:create')) throw new ApiError(403, 'action_forbidden', '租约生效后才可报修'); return { id: `maint-${Date.now()}`, reference: 'M-DEMO-NEW', summary, priority, status: 'open' as const, updatedAt: new Date().toISOString() } }
  async getReport(id: string) { if (!capabilities(this.persona).includes('report:read-current') && !capabilities(this.persona).includes('report:read-history')) throw new ApiError(404, 'resource_not_found', '没有找到报告'); if (id !== report.id) throw new ApiError(404, 'resource_not_found', '没有找到报告'); return { ...report, sourceLeaseId: this.persona === 'former_tenant' ? 'lease-history' : 'lease-current', propertyId: this.persona === 'former_tenant' ? 'prop-park' : 'prop-harbour' } }
  async startReport(file: File, _attributes: Record<string, boolean>, onProgress: (job: ReportJobView) => void) { if (!capabilities(this.persona).includes('report:create')) throw new ApiError(403, 'report_generation_not_allowed', '只有有效租约的 Tenant 可以生成报告'); if (!file.type.startsWith('video/')) throw new ApiError(422, 'unsupported_media_type', '请选择视频文件'); const steps = [['uploading_video', 12], ['extracting_frames', 35], ['scene_understanding', 62], ['writing_report', 86], ['complete', 100]] as const; for (const [stage, progressPercent] of steps) { onProgress({ id: 'job-demo', reportId: report.id, status: progressPercent === 100 ? 'completed' : 'running', stage, progressPercent }); await new Promise((resolve) => setTimeout(resolve, 220)) } return report }
}

export const mockPersonaLabels: Record<MockPersona, string> = { guest: '访客', prospect: 'Prospect', executed_tenant: 'Tenant · 待入住', active_tenant: 'Tenant · Active', former_tenant: 'Former Tenant' }
