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
      weeklyRent: 680,
      openMaintenance: 2,
    })])
    expect(new Headers(fetchMock.mock.calls[0][1].headers).get('Authorization')).toBe('Bearer access-token')
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
