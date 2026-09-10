export type StaffRole =
  | 'leasing_consultant'
  | 'property_manager'
  | 'maintainer'
  | 'manager_admin'

export type Permission =
  | 'property:read_market'
  | 'prospect:manage'
  | 'application:manage'
  | 'lease:prepare'
  | 'lease:execute'
  | 'building:read_assigned'
  | 'property:manage_assigned'
  | 'lease:manage_active_assigned'
  | 'maintenance:assign_assigned'
  | 'maintenance:update_assigned'
  | 'work_order:read_assigned'
  | 'work_order:update_assigned'
  | 'work_order:evidence_write'
  | 'property:read_work_context'
  | 'report:read_work_context'
  | 'report:read_assigned'
  | 'report:generate_assigned'
  | 'agent:staff:use'
  | 'building:read_all'
  | 'property:read_all'
  | 'prospect:manage_all'
  | 'application:manage_all'
  | 'lease:manage_all'
  | 'maintenance:manage_all'
  | 'report:read_all'
  | 'report:generate_all'
  | 'iam:user:read'
  | 'iam:user:status_manage'
  | 'iam:staff:create'
  | 'iam:staff:read'
  | 'iam:staff:employment_manage'
  | 'iam:staff:role_manage'
  | 'iam:audit:read'
  | 'rbac:read'
  | 'rbac:manage'
  | 'scope:manage'

export interface StaffIdentity {
  id: string
  username: string
  displayName: string
  email: string
  staffCode: string
  role: StaffRole
  roleName?: string
}

export interface Session {
  accessToken: string
  expiresIn: number
  staff: StaffIdentity
  permissions: Permission[]
}

export interface Building {
  id: string
  name: string
  address: string
}

export interface PropertySummary {
  id: string
  reference: string
  building: Building
  room: string
  bedrooms: number
  bathrooms: number
  weeklyRent: number
  currency: string
  occupancy: 'vacant' | 'reserved' | 'occupied'
  listingStatus: 'marketing' | 'private'
  tenant?: { displayName: string; email: string }
  lease?: { reference: string; status: string; endsOn: string }
  billing?: { paid: number; open: number; overdue: number }
  openMaintenance: number
  reports: number
  coverImageUrl?: string
}

export interface ContractSummary {
  documentId: string
  version: number
  digest: string
  tenantSignedAt?: string
  companySignedAt?: string
}

export interface OrderSummary {
  id: string
  reference: string
  stage: 'application' | 'pending_signature' | 'executed' | 'ended'
  property: Pick<PropertySummary, 'id' | 'reference' | 'room' | 'building'>
  customer: { displayName: string; email: string; phone: string }
  consultant: { displayName: string; staffCode: string }
  startsOn: string
  endsOn: string
  weeklyRent: number
  status: string
  contract?: ContractSummary
}

export type MaintenanceStatus = 'open' | 'assigned' | 'in_progress' | 'blocked' | 'completed' | 'cancelled'

export interface MaintenanceOrder {
  id: string
  reference: string
  status: MaintenanceStatus
  priority: 'low' | 'medium' | 'high' | 'urgent'
  version: number
  summary: string
  description: string
  property: Pick<PropertySummary, 'id' | 'reference' | 'room' | 'building'>
  tenant: { displayName: string; email: string; phone: string }
  assignee?: { displayName: string; staffCode: string }
  updatedAt: string
}

export interface StaffAccount {
  id: string
  staffCode: string
  displayName: string
  email: string
  role: StaffRole
  employmentStatus: 'active' | 'suspended' | 'ended'
  permissions: Permission[]
}

export interface BootstrapData {
  staff: StaffIdentity
  permissions: Permission[]
}

export interface ApiErrorShape {
  code: string
  message: string
  requestId?: string
  retryable: boolean
  details?: Record<string, unknown>
  fieldErrors?: Array<{ field: string; reason: string }>
}

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly error: ApiErrorShape,
  ) {
    super(error.message)
    this.name = 'ApiError'
  }
}

export interface LoginInput {
  email: string
  password: string
}

export interface StaffPortalClient {
  login(input: LoginInput): Promise<Session>
  refresh(): Promise<Session>
  logout(): Promise<void>
  bootstrap(): Promise<BootstrapData>
  listProperties(): Promise<PropertySummary[]>
  listOrders(): Promise<OrderSummary[]>
  listMaintenanceOrders(): Promise<MaintenanceOrder[]>
  transitionMaintenanceOrder(id: string, status: MaintenanceStatus, version: number): Promise<MaintenanceOrder>
  listStaff(): Promise<StaffAccount[]>
  createPropertyReport(propertyId: string): Promise<{ reportId: string }>
  setAccessToken(token: string | null): void
  setUnauthorizedHandler(handler: (() => void) | null): void
}
