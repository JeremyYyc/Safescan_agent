import { ROLE_PERMISSIONS } from '../permissions'
import type {
  MaintenanceOrder,
  OrderSummary,
  PropertySummary,
  StaffAccount,
  StaffIdentity,
  StaffRole,
} from '../types'

export const MOCK_STAFF: Record<StaffRole, StaffIdentity> = {
  leasing_consultant: {
    id: 'staff-lc-001', displayName: 'Ethan Carter', email: 'EthanSafescan@outlook.com', staffCode: 'LC001', role: 'leasing_consultant',
  },
  property_manager: {
    id: 'staff-pm-001', displayName: 'Noah Mitchell', email: 'NoahSafescan@outlook.com', staffCode: 'PM001', role: 'property_manager',
  },
  maintainer: {
    id: 'staff-mt-001', displayName: 'Daniel Cooper', email: 'DanielSafescan@outlook.com', staffCode: 'MT001', role: 'maintainer',
  },
  manager_admin: {
    id: 'staff-ma-001', displayName: 'Charlotte Morgan', email: 'CharlotteSafescan@outlook.com', staffCode: 'MA001', role: 'manager_admin',
  },
}

export const DEMO_PASSWORDS: Record<StaffRole, string> = {
  leasing_consultant: 'staffEthanCarter123456',
  property_manager: 'staffNoahMitchell123456',
  maintainer: 'staffDanielCooper123456',
  manager_admin: 'staffCharlotteMorgan123456',
}

const harbour = { id: 'building-harbour', name: 'Harbour Heights', address: '18 Bay Street, Sydney NSW' }
const park = { id: 'building-park', name: 'Parkline Residences', address: '42 Albert Road, Melbourne VIC' }
const river = { id: 'building-river', name: 'Riverside Court', address: '7 River Walk, Brisbane QLD' }

export const PROPERTIES: PropertySummary[] = [
  { id: 'property-hh-1204', reference: 'PROP-HH-1204', building: harbour, room: '1204', bedrooms: 2, bathrooms: 2, weeklyRent: 780, currency: 'AUD', occupancy: 'vacant', listingStatus: 'marketing', openMaintenance: 0, reports: 1 },
  { id: 'property-hh-0802', reference: 'PROP-HH-0802', building: harbour, room: '0802', bedrooms: 1, bathrooms: 1, weeklyRent: 630, currency: 'AUD', occupancy: 'occupied', listingStatus: 'private', tenant: { displayName: 'Mia Chen', email: 'mia.chen@example.com' }, lease: { reference: 'LS-2026-0188', status: 'active', endsOn: '2027-04-30' }, billing: { paid: 7560, open: 630, overdue: 0 }, openMaintenance: 1, reports: 2 },
  { id: 'property-pr-1507', reference: 'PROP-PR-1507', building: park, room: '1507', bedrooms: 3, bathrooms: 2, weeklyRent: 910, currency: 'AUD', occupancy: 'reserved', listingStatus: 'private', tenant: { displayName: 'Lucas Martin', email: 'lucas.martin@example.com' }, lease: { reference: 'LS-2026-0201', status: 'executed', endsOn: '2027-08-31' }, billing: { paid: 0, open: 0, overdue: 0 }, openMaintenance: 0, reports: 0 },
  { id: 'property-pr-0305', reference: 'PROP-PR-0305', building: park, room: '0305', bedrooms: 2, bathrooms: 1, weeklyRent: 690, currency: 'AUD', occupancy: 'vacant', listingStatus: 'marketing', openMaintenance: 0, reports: 0 },
  { id: 'property-rc-0601', reference: 'PROP-RC-0601', building: river, room: '0601', bedrooms: 2, bathrooms: 2, weeklyRent: 720, currency: 'AUD', occupancy: 'occupied', listingStatus: 'private', tenant: { displayName: 'Ava Wilson', email: 'ava.wilson@example.com' }, lease: { reference: 'LS-2025-0094', status: 'active', endsOn: '2026-12-15' }, billing: { paid: 12960, open: 1440, overdue: 720 }, openMaintenance: 2, reports: 3 },
]

export const ORDERS: OrderSummary[] = [
  { id: 'order-001', reference: 'ORD-2026-0241', stage: 'pending_signature', property: PROPERTIES[0], customer: { displayName: 'Amelia Wong', email: 'amelia.wong@example.com', phone: '+61 4•• ••• 218' }, consultant: { displayName: 'Ethan Carter', staffCode: 'LC001' }, startsOn: '2026-10-01', endsOn: '2027-09-30', weeklyRent: 780, status: '等待租客签署', contract: { documentId: 'DOC-9C11', version: 2, digest: 'sha256:8e21…b19a', companySignedAt: '2026-09-08T04:15:00Z' } },
  { id: 'order-002', reference: 'ORD-2026-0236', stage: 'application', property: PROPERTIES[3], customer: { displayName: 'Jack Thompson', email: 'jack.thompson@example.com', phone: '+61 4•• ••• 664' }, consultant: { displayName: 'Ethan Carter', staffCode: 'LC001' }, startsOn: '2026-10-15', endsOn: '2027-10-14', weeklyRent: 690, status: '申请审核中' },
  { id: 'order-003', reference: 'LS-2026-0188', stage: 'executed', property: PROPERTIES[1], customer: { displayName: 'Mia Chen', email: 'mia.chen@example.com', phone: '+61 4•• ••• 110' }, consultant: { displayName: 'Ethan Carter', staffCode: 'LC001' }, startsOn: '2026-05-01', endsOn: '2027-04-30', weeklyRent: 630, status: '租约生效中', contract: { documentId: 'DOC-7A81', version: 1, digest: 'sha256:fa70…2d51', tenantSignedAt: '2026-04-18T10:10:00Z', companySignedAt: '2026-04-19T03:20:00Z' } },
  { id: 'order-004', reference: 'LS-2025-0094', stage: 'executed', property: PROPERTIES[4], customer: { displayName: 'Ava Wilson', email: 'ava.wilson@example.com', phone: '+61 4•• ••• 902' }, consultant: { displayName: 'Sophia Reed', staffCode: 'LC004' }, startsOn: '2025-12-16', endsOn: '2026-12-15', weeklyRent: 720, status: '租约生效中', contract: { documentId: 'DOC-3B18', version: 1, digest: 'sha256:19bb…73c0', tenantSignedAt: '2025-11-29T07:42:00Z', companySignedAt: '2025-11-29T09:05:00Z' } },
]

export const MAINTENANCE_ORDERS: MaintenanceOrder[] = [
  { id: 'maintenance-001', reference: 'WO-2026-0148', status: 'assigned', priority: 'urgent', version: 3, summary: '浴室天花板持续渗水', description: '淋浴使用后天花板灯具附近出现水滴，需要尽快检查。', property: PROPERTIES[1], tenant: { displayName: 'Mia Chen', email: 'mia.chen@example.com', phone: '+61 4•• ••• 110' }, assignee: { displayName: 'Daniel Cooper', staffCode: 'MT001' }, updatedAt: '2026-09-09T07:32:00Z' },
  { id: 'maintenance-002', reference: 'WO-2026-0142', status: 'in_progress', priority: 'medium', version: 5, summary: '空调制冷效果较弱', description: '客厅空调运行 30 分钟后温度仍未下降。', property: PROPERTIES[4], tenant: { displayName: 'Ava Wilson', email: 'ava.wilson@example.com', phone: '+61 4•• ••• 902' }, assignee: { displayName: 'Grace Turner', staffCode: 'MT002' }, updatedAt: '2026-09-08T11:20:00Z' },
  { id: 'maintenance-003', reference: 'WO-2026-0131', status: 'blocked', priority: 'high', version: 4, summary: '厨房灶具点火异常', description: '已确认零件型号，等待供应商到货。', property: PROPERTIES[4], tenant: { displayName: 'Ava Wilson', email: 'ava.wilson@example.com', phone: '+61 4•• ••• 902' }, assignee: { displayName: 'Daniel Cooper', staffCode: 'MT001' }, updatedAt: '2026-09-07T05:45:00Z' },
]

const staffSeeds: Array<[string, string, string, StaffRole]> = [
  ['LC001', 'Ethan Carter', 'EthanSafescan@outlook.com', 'leasing_consultant'],
  ['LC002', 'Olivia Bennett', 'OliviaSafescan@outlook.com', 'leasing_consultant'],
  ['LC003', 'Liam Foster', 'LiamSafescan@outlook.com', 'leasing_consultant'],
  ['LC004', 'Sophia Reed', 'SophiaSafescan@outlook.com', 'leasing_consultant'],
  ['PM001', 'Noah Mitchell', 'NoahSafescan@outlook.com', 'property_manager'],
  ['PM002', 'Emma Collins', 'EmmaSafescan@outlook.com', 'property_manager'],
  ['PM003', 'James Parker', 'JamesSafescan@outlook.com', 'property_manager'],
  ['PM004', 'Ava Richardson', 'AvaSafescan@outlook.com', 'property_manager'],
  ['MT001', 'Daniel Cooper', 'DanielSafescan@outlook.com', 'maintainer'],
  ['MT002', 'Grace Turner', 'GraceSafescan@outlook.com', 'maintainer'],
  ['MT003', 'Henry Walker', 'HenrySafescan@outlook.com', 'maintainer'],
  ['MA001', 'Charlotte Morgan', 'CharlotteSafescan@outlook.com', 'manager_admin'],
]

export const STAFF_ACCOUNTS: StaffAccount[] = staffSeeds.map(([staffCode, displayName, email, role]) => ({
  id: `staff-${staffCode.toLowerCase()}`,
  staffCode,
  displayName,
  email,
  role,
  employmentStatus: 'active',
  permissions: ROLE_PERMISSIONS[role],
}))
