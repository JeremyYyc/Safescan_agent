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
          display_image_urls: ['/api/v1/staff/properties/property-1/images/image-1'],
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
      coverImageUrl: '/api/v1/staff/properties/property-1/images/image-1',
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

describe('lease PDFs and portfolio scopes', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('uses the authenticated PDF endpoint and preserves binary contents', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response('%PDF-1.7 example', { headers: { 'Content-Type': 'application/pdf' } }))
    vi.stubGlobal('fetch', fetchMock)
    const client = new RealStaffPortalClient()
    client.setAccessToken('private-token')
    const pdf = await client.getLeasePdf('lease-1')
    expect(await pdf.text()).toBe('%PDF-1.7 example')
    expect(fetchMock.mock.calls[0][0]).toBe('/api/v1/staff/leases/lease-1/document/pdf')
    expect(new Headers(fetchMock.mock.calls[0][1].headers).get('Authorization')).toBe('Bearer private-token')
  })

  it('maps real assigned regions and upcoming leases', async () => {
    vi.stubGlobal('fetch', vi.fn()
      .mockResolvedValueOnce(jsonResponse({ data: { staff: { role: 'property_manager', assigned_buildings: [{ id: 'b1', name: 'Harbour House', address: 'Sydney NSW' }], assignment_scope: 'assigned' } } }))
      .mockResolvedValueOnce(jsonResponse({ data: { items: [{ id: 'p1', status: 'reserved', current_lease: { id: 'lease-1', reference: 'L-1', status: 'executed', ends_on: '2027-10-01' } }] } })))
    const client = new RealStaffPortalClient()
    expect((await client.bootstrap()).staff.assignedBuildings?.[0].address).toBe('Sydney NSW')
    expect((await client.listProperties())[0]).toMatchObject({ occupancy: 'reserved', lease: { id: 'lease-1', reference: 'L-1' } })
  })
})

describe('full portfolio pagination', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('loads subsequent pages and deduplicates records at page boundaries', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ data: { items: [{ id: 'p1', status: 'marketing' }], next_cursor: 'page-2' } }))
      .mockResolvedValueOnce(jsonResponse({ data: { items: [{ id: 'p1', status: 'marketing' }, { id: 'p2', status: 'occupied' }], next_cursor: null } }))
    vi.stubGlobal('fetch', fetchMock)
    expect((await new RealStaffPortalClient().listProperties()).map((item) => item.id)).toEqual(['p1', 'p2'])
    expect(fetchMock.mock.calls[1][0]).toBe('/api/v1/staff/properties?limit=100&cursor=page-2')
  })

  it('fails visibly when an upstream cursor stops advancing', async () => {
    vi.stubGlobal('fetch', vi.fn().mockImplementation(() => Promise.resolve(jsonResponse({ data: { items: [{ id: 'lease-1' }], next_cursor: 'same-page' } }))))
    await expect(new RealStaffPortalClient().listOrders()).rejects.toMatchObject({ error: { code: 'invalid_pagination' } })
  })
})

describe('maintenance server pagination', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('requests only one 50-item page and preserves the next cursor and expanded context', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ data: {
      items: [{ id: 'm1', property: { id: 'p1', reference: 'P-1', attributes: { room_number: '101' }, building: { id: 'b1', name: 'Harbour House', address: 'Sydney NSW' } }, assigned_staff: { id: 's1', display_name: 'Daniel Cooper', staff_code: 'MT001' }, status: 'assigned' }],
      next_cursor: 'second-page',
    } }))
    vi.stubGlobal('fetch', fetchMock)
    const page = await new RealStaffPortalClient().listMaintenancePage({ status: 'assigned', cursor: 'first-page' })
    expect(fetchMock).toHaveBeenCalledOnce()
    expect(fetchMock.mock.calls[0][0]).toBe('/api/v1/staff/maintenance-orders?limit=50&status=assigned&cursor=first-page')
    expect(page.nextCursor).toBe('second-page')
    expect(page.items[0].property).toMatchObject({ room: '101', building: { name: 'Harbour House' } })
    expect(page.items[0].assignee).toEqual({ displayName: 'Daniel Cooper', staffCode: 'MT001' })
  })
  it('loads staff photos with bearer authentication and rejects foreign URLs', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response('photo', { headers: { 'Content-Type': 'image/png' } }))
    vi.stubGlobal('fetch', fetchMock)
    const client = new RealStaffPortalClient()
    client.setAccessToken('image-token')
    const image = await client.getPropertyImage('/api/v1/staff/properties/p1/images/i1')
    expect(image.type).toBe('image/png')
    expect(new Headers(fetchMock.mock.calls[0][1].headers).get('Authorization')).toBe('Bearer image-token')
    await expect(client.getPropertyImage('https://example.com/photo.jpg')).rejects.toThrow('房源图片地址无效')
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

})

describe('property history and city projections', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('normalizes historical inspections, maintenance events and field provenance without dropping the protected image', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ data: {
      property: { id: 'p1', reference: 'P-1', city_id: 'perth', status: 'occupied', display_image_urls: ['/api/v1/staff/properties/p1/images/photo'], floor_area_sqm: '81.5', parking_spaces: 1, attributes: { is_synthetic: true, field_sources: { floor_area_sqm: { origin: 'simulated' } } } },
      leases: { items: [{ id: 'l1', property: { id: 'p1' }, status: 'active', document: { id: 'doc1', version: 1, terms_digest: 'sha256:terms' } }], next_cursor: 'more-leases', total: 101 },
      maintenance: { items: [{ id: 'm1', status: 'completed', timeline: [{ sequence_no: 1, message: '维修完成', occurred_at: '2026-09-01T00:00:00Z', to_status: 'completed' }] }], next_cursor: 'more-maintenance', total: 150 },
      inspections: { items: [{ id: 'i1', kind: 'move_out', status: 'completed', inspected_at: '2026-09-02T00:00:00Z', source_lease_id: 'l1', findings: [{ area: '厨房', description: '水龙头已修复', severity: 'low', work_order_id: 'm1' }] }] },
    }, meta: { partial_errors: [{ component: 'reports' }] } })))
    const detail = await new RealStaffPortalClient().getPropertyDetail('p1')
    expect(detail.property).toMatchObject({ building: { cityId: 'perth' }, floorAreaSqm: 81.5, parkingSpaces: 1, isSynthetic: true, coverImageUrl: '/api/v1/staff/properties/p1/images/photo' })
    expect(detail.leases[0].contract?.documentId).toBe('doc1')
    expect(detail).toMatchObject({ leaseHistoryNextCursor: 'more-leases', leaseHistoryTotal: 101, maintenanceHistoryNextCursor: 'more-maintenance', maintenanceHistoryTotal: 150 })
    expect(detail.maintenance[0].timeline?.[0].toStatus).toBe('completed')
    expect(detail.inspections[0].findings[0].workOrderId).toBe('m1')
    expect(detail.attributes.fieldSources).toEqual({ floorAreaSqm: { origin: 'simulated' } })
    expect(detail.partialErrors).toEqual(['reports'])
  })

  it('requests one server-filtered order page and keeps its total and next cursor', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ data: { items: [{ id: 'l1', status: 'ended' }], total: 129, next_cursor: 'older-orders' } }))
    vi.stubGlobal('fetch', fetchMock)
    const page = await new RealStaffPortalClient().listOrderPage('current-orders', 'ended')
    const url = new URL(fetchMock.mock.calls[0][0], 'http://localhost')
    expect(url.searchParams.get('limit')).toBe('50')
    expect(url.searchParams.get('cursor')).toBe('current-orders')
    expect(url.searchParams.get('status')).toBe('ended,terminated,cancelled,expired')
    expect(page).toMatchObject({ total: 129, nextCursor: 'older-orders' })
    expect(fetchMock).toHaveBeenCalledOnce()
  })
})
