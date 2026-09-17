export type CustomerStatus = 'prospect' | 'tenant' | 'former_tenant'
export type LeaseStatus = 'pending_signature' | 'executed' | 'active' | 'ended' | 'terminated'

export type Capability =
  | 'property:read'
  | 'contact:create'
  | 'application:read'
  | 'application:create'
  | 'lease:read'
  | 'my-property:read'
  | 'maintenance:read'
  | 'maintenance:create'
  | 'report:read-current'
  | 'report:create'
  | 'report:read-history'
  | 'agent:access'

export interface CustomerView {
  id: string
  username: string
  email: string
  status: CustomerStatus
  statusVersion: number
}

export interface BootstrapView {
  customer: CustomerView | null
  capabilities: Capability[]
  statusVersion: number
}

export interface PropertyView {
  id: string
  reference: string
  address: string
  suburb: string
  bedrooms: number
  bathrooms: number
  parking: number
  weeklyRent: number
  currency: 'AUD'
  availability: 'available' | 'under_offer'
  description: string
  features: string[]
  accent: string
}

export type ApplicationStatus = 'draft' | 'submitted' | 'reviewing' | 'approved' | 'rejected' | 'withdrawn' | 'ineligible' | 'expired'
export interface ApplicationView {
  id: string
  reference: string
  property: Pick<PropertyView, 'id' | 'reference' | 'address' | 'suburb'>
  status: ApplicationStatus
  desiredStartOn: string
  termMonths: number
  occupants: number
  note?: string
  submittedAt?: string
  updatedAt: string
  version: number
}

export interface LeaseView {
  id: string
  reference: string
  property: Pick<PropertyView, 'id' | 'reference' | 'address' | 'suburb'>
  status: LeaseStatus
  startsOn: string
  endsOn: string
  weeklyRent: number
  currency: 'AUD'
  executedAt?: string
  document: { id: string; version: number; termsDigest: string }
}

export interface InvoiceView {
  id: string
  period: string
  amount: number
  status: 'paid' | 'due' | 'scheduled'
  paidAt?: string
}

export interface MaintenanceOrderView {
  id: string
  reference: string
  summary: string
  priority: 'low' | 'normal' | 'urgent'
  status: 'open' | 'assigned' | 'in_progress' | 'blocked' | 'completed' | 'cancelled'
  updatedAt: string
}

export interface ReportSummary {
  id: string
  title: string
  propertyId: string
  sourceLeaseId: string
  status: 'draft' | 'processing' | 'active' | 'failed'
  completedAt?: string
  validationPassed?: boolean
}

export interface ReportDetail extends ReportSummary {
  overview: string
  regions: Array<{ name: string; risk: 'low' | 'medium' | 'high'; findings: string[]; suggestions: string[] }>
}

export interface PropertyHomeView {
  lease: LeaseView
  invoices: InvoiceView[]
  maintenance: MaintenanceOrderView[]
  reports: ReportSummary[]
}

export interface ReportJobView {
  id: string
  reportId: string
  status: 'queued' | 'running' | 'completed' | 'failed'
  stage: string
  progressPercent: number
  error?: string
}

export interface LoginInput { email: string; password: string; rememberMe?: boolean }
export interface RegisterInput { email: string; username: string; password: string; acceptedTermsVersion: string }
export interface ApplicationInput { propertyId: string; caseId: string; desiredStartOn: string; termMonths: number; occupants: number; note?: string }

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public retryable = false) {
    super(message)
    this.name = 'ApiError'
  }
}

export interface TenantPortalApi {
  bootstrap(): Promise<BootstrapView>
  restoreSession(): Promise<BootstrapView>
  login(input: LoginInput): Promise<BootstrapView>
  register(input: RegisterInput): Promise<BootstrapView>
  logout(): Promise<void>
  listProperties(): Promise<PropertyView[]>
  getProperty(id: string): Promise<PropertyView>
  contactProperty(id: string, message: string): Promise<{ caseId: string }>
  createApplication(input: ApplicationInput): Promise<ApplicationView>
  listApplications(): Promise<ApplicationView[]>
  getApplication(id: string): Promise<ApplicationView>
  listLeases(): Promise<LeaseView[]>
  getCurrentProperty(): Promise<PropertyHomeView>
  getHistoricalProperty(leaseId: string): Promise<PropertyHomeView>
  createMaintenance(summary: string, description: string, priority: MaintenanceOrderView['priority']): Promise<MaintenanceOrderView>
  getReport(id: string): Promise<ReportDetail>
  startReport(file: File, attributes: Record<string, boolean>, onProgress: (job: ReportJobView) => void): Promise<ReportDetail>
}
