import { ApiError } from '../types'
import { RealStaffPortalClient } from './realClient'

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('RealStaffPortalClient', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('unwraps BFF pages and camelizes their items', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({
      data: {
        items: [{
          id: 'property-1',
          reference: 'P-001',
          address: 'Unit 1, Harbour Street',
          building: null,
          attributes: { room_number: '1' },
          status: 'marketing',
          listing_visibility: 'public',
          weekly_rent: 680,
          open_maintenance: 2,
        }],
        next_cursor: null,
        total: 1,
      },
      meta: { correlation_id: 'corr-1', partial_errors: [] },
    }))
    vi.stubGlobal('fetch', fetchMock)

    const client = new RealStaffPortalClient()
    client.setAccessToken('access-token')
    const properties = await client.listProperties()

    expect(properties).toEqual([expect.objectContaining({
      id: 'property-1',
      building: expect.objectContaining({
        id: 'unassigned:property-1',
        name: 'Unit 1, Harbour Street',
      }),
      room: '1',
      occupancy: 'vacant',
      listingStatus: 'marketing',
      weeklyRent: 680,
      openMaintenance: 2,
    })])
    expect(new Headers(fetchMock.mock.calls[0][1].headers).get('Authorization')).toBe('Bearer access-token')
  })

  it('maps the real leasing service lease projection into a complete order summary', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({
      data: {
        items: [{
          id: 'lease-1',
          reference: 'LS-2026-001',
          application_id: 'application-1',
          property: {
            id: 'property-1',
            reference: 'PROP-HH-1204',
            address: '1204, 18 Bay Street, Sydney NSW',
          },
          starts_on: '2026-10-01',
          ends_on: '2027-09-30',
          weekly_rent: '780.00',
          currency: 'AUD',
          status: 'pending_signature',
          document: { id: 'document-1', version: 2, terms_digest: 'sha256:abc123' },
          tenant_signers: [{ subject_id: 'subject-1', status: 'signed', signed_at: '2026-09-12T03:00:00Z' }],
          company_signed_at: '2026-09-12T04:00:00Z',
          version: 3,
        }],
        next_cursor: null,
      },
    })))

    const orders = await new RealStaffPortalClient().listOrders()

    expect(orders).toEqual([{
      id: 'lease-1',
      reference: 'LS-2026-001',
      stage: 'pending_signature',
      property: {
        id: 'property-1',
        reference: 'PROP-HH-1204',
        room: '—',
        building: {
          id: 'unassigned:property-1',
          name: '1204, 18 Bay Street, Sydney NSW',
          address: '1204, 18 Bay Street, Sydney NSW',
        },
      },
      customer: { displayName: '租客信息未提供', email: '—', phone: '—' },
      consultant: { displayName: '未分配顾问', staffCode: '—' },
      startsOn: '2026-10-01',
      endsOn: '2027-09-30',
      weeklyRent: 780,
      status: 'pending_signature',
      contract: {
        documentId: 'document-1',
        version: 2,
        digest: 'sha256:abc123',
        tenantSignedAt: '2026-09-12T03:00:00Z',
        companySignedAt: '2026-09-12T04:00:00Z',
      },
    }])
  })

  it('maps the real maintenance projection without assuming expanded property or staff records', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({
      data: {
        items: [{
          id: 'maintenance-1',
          reference: 'WO-2026-0148',
          property: { id: 'property-1' },
          lease_id: 'lease-1',
          summary: '浴室天花板持续渗水',
          description: null,
          priority: 'normal',
          status: 'assigned',
          reported_by: { subject_id: 'subject-1' },
          assigned_staff: { id: 'staff-1' },
          version: 3,
          updated_at: '2026-09-09T07:32:00Z',
        }],
      },
    })))

    const orders = await new RealStaffPortalClient().listMaintenanceOrders()

    expect(orders).toEqual([expect.objectContaining({
      id: 'maintenance-1',
      priority: 'medium',
      status: 'assigned',
      description: '未提供问题描述',
      property: expect.objectContaining({
        id: 'property-1',
        building: expect.objectContaining({ name: '房源信息未提供' }),
      }),
      tenant: { displayName: '报修租客信息未提供', email: '—', phone: '—' },
      assignee: { displayName: '已分派员工', staffCode: '—' },
      updatedAt: '2026-09-09T07:32:00Z',
    })])
  })

  it('maps the real Identity staff-admin projection and nested role', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({
      data: {
        items: [{
          id: 'staff-1',
          staff_code: 'PM001',
          display_name: 'Noah Mitchell',
          email: 'noah@example.com',
          employment_status: 'active',
          role: { code: 'property_manager', name: 'Property Manager' },
          permissions: ['property:manage_assigned'],
        }],
      },
    })))

    await expect(new RealStaffPortalClient().listStaff()).resolves.toEqual([{
      id: 'staff-1',
      staffCode: 'PM001',
      displayName: 'Noah Mitchell',
      email: 'noah@example.com',
      role: 'property_manager',
      employmentStatus: 'active',
      permissions: ['property:manage_assigned'],
    }])
  })

  it('uses bootstrap capabilities as the effective permission set', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({
      data: {
        staff: {
          id: 'staff-1',
          display_name: 'Noah Mitchell',
          role: 'property_manager',
          permissions: ['property:manage_assigned'],
        },
        capabilities: ['property:manage_assigned', 'report:generate_assigned'],
        menu: [],
      },
      meta: { correlation_id: 'corr-2', partial_errors: [] },
    })))

    const bootstrap = await new RealStaffPortalClient().bootstrap()

    expect(bootstrap.staff).toMatchObject({
      username: 'Noah Mitchell',
      displayName: 'Noah Mitchell',
      email: '',
      staffCode: '',
      role: 'property_manager',
      roleName: '',
    })
    expect(bootstrap.permissions).toEqual(['property:manage_assigned', 'report:generate_assigned'])
  })

  it('maps the current Staff BFF bootstrap identity contract', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({
      data: {
        staff: {
          id: 'staff-1',
          display_name: 'NoahManager',
          username: 'NoahManager',
          email: 'noah@example.com',
          staff_code: 'PM-001',
          role: 'property_manager',
          role_name: 'Property Manager',
          permissions: ['report:generate_assigned'],
        },
        capabilities: ['report:generate_assigned'],
        menu: [],
      },
    })))

    const bootstrap = await new RealStaffPortalClient().bootstrap()

    expect(bootstrap.staff).toMatchObject({
      id: 'staff-1',
      username: 'NoahManager',
      displayName: 'NoahManager',
      email: 'noah@example.com',
      staffCode: 'PM-001',
      role: 'property_manager',
      roleName: 'Property Manager',
    })
  })

  it('maps the Identity username separately from the staff display name', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({
      data: {
        access_token: 'staff-token',
        expires_in: 900,
        portal: 'staff',
        user: {
          id: 'user-1',
          username: 'NoahMitchell',
          email: 'NoahSafescan@outlook.com',
          staff: {
            id: 'staff-1',
            staff_code: 'PM001',
            display_name: 'Noah Mitchell',
            role: { code: 'property_manager', name: 'Property Manager' },
          },
        },
        scopes: ['property:manage_assigned'],
      },
    })))

    const session = await new RealStaffPortalClient().login({ email: 'NoahSafescan@outlook.com', password: 'secret' })

    expect(session.staff).toMatchObject({
      username: 'NoahMitchell',
      displayName: 'Noah Mitchell',
      email: 'NoahSafescan@outlook.com',
      staffCode: 'PM001',
      roleName: 'Property Manager',
    })
  })

  it('sends the frozen maintenance transition request shape', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({
      data: { id: 'order-1', status: 'in_progress', version: 4, updated_at: '2026-09-09T12:00:00Z' },
      meta: { correlation_id: 'corr-3', partial_errors: [] },
    }))
    vi.stubGlobal('fetch', fetchMock)

    const updated = await new RealStaffPortalClient().transitionMaintenanceOrder('order-1', 'in_progress', 3)
    const [, init] = fetchMock.mock.calls[0]

    expect(JSON.parse(init.body as string)).toEqual({ to_status: 'in_progress', version: 3 })
    expect(new Headers(init.headers).get('Idempotency-Key')).toBeTruthy()
    expect(updated).toMatchObject({ id: 'order-1', status: 'in_progress', updatedAt: '2026-09-09T12:00:00Z' })
  })

  it('returns the report id without inventing a job before video upload', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({
      data: { id: 'report-1', property_id: 'property-1', status: 'draft' },
      meta: { correlation_id: 'corr-4', partial_errors: [] },
    }, 201)))

    await expect(new RealStaffPortalClient().createPropertyReport('property-1'))
      .resolves.toEqual({ reportId: 'report-1' })
  })

  it('normalizes BFF correlation and field error names', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({
      error: {
        status: 422,
        code: 'validation_failed',
        message: '请求字段无效',
        correlation_id: 'corr-error',
        retryable: false,
        details: {},
        field_errors: [{ field: 'to_status', reason: '不允许的状态' }],
      },
    }, 422)))

    const error = await new RealStaffPortalClient().listStaff().catch((reason) => reason)

    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({
      status: 422,
      error: {
        code: 'validation_failed',
        requestId: 'corr-error',
        fieldErrors: [{ field: 'to_status', reason: '不允许的状态' }],
      },
    })
  })

  it('rejects a tenant identity response before entering the staff portal', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({
      data: {
        access_token: 'tenant-token',
        expires_in: 900,
        portal: 'tenant',
        user: { id: 'customer-1', email: 'customer@example.com' },
        scopes: [],
      },
    })))

    await expect(new RealStaffPortalClient().login({ email: 'customer@example.com', password: 'secret' }))
      .rejects.toMatchObject({ status: 403, error: { code: 'staff_portal_required' } })
  })
})
