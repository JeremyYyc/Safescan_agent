// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { HttpTenantPortalApi } from '../src/api/httpAdapter'

describe('HttpTenantPortalApi', () => {
  afterEach(() => {
    document.cookie = 'safescan_csrf=; Max-Age=0; Path=/'
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('unwraps the BFF property page before mapping real properties', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
      data: {
        items: [{
          id: 'property-1',
          reference: 'P-001',
          address: 'Unit 1, Harbour Street',
          bedrooms: 2,
          bathrooms: '1.0',
          weekly_rent: '650.00',
          status: 'marketing',
          availability: 'available',
          attributes: { features: ['balcony'] },
        }],
        next_cursor: null,
      },
    }), { status: 200, headers: { 'Content-Type': 'application/json' } })))

    await expect(new HttpTenantPortalApi().listProperties()).resolves.toEqual([
      expect.objectContaining({
        id: 'property-1',
        reference: 'P-001',
        weeklyRent: 650,
        availability: 'available',
      }),
    ])
  })

  it('unwraps paginated applications and maps the snake_case DTO', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
      data: {
        items: [{
          id: 'application-1',
          reference: 'APP-001',
          property_id: 'property-1',
          status: 'submitted',
          desired_start_on: '2026-10-01',
          term_months: 12,
          occupants: 2,
          note: 'Near public transport',
          submitted_at: '2026-09-15T01:00:00Z',
          updated_at: '2026-09-15T02:00:00Z',
          version: 3,
        }],
        next_cursor: null,
      },
    }), { status: 200, headers: { 'Content-Type': 'application/json' } })))

    await expect(new HttpTenantPortalApi().listApplications()).resolves.toEqual([{
      id: 'application-1',
      reference: 'APP-001',
      property: {
        id: 'property-1',
        reference: 'property-1',
        address: '房源 property-1',
        suburb: '',
      },
      status: 'submitted',
      desiredStartOn: '2026-10-01',
      termMonths: 12,
      occupants: 2,
      note: 'Near public transport',
      submittedAt: '2026-09-15T01:00:00Z',
      updatedAt: '2026-09-15T02:00:00Z',
      version: 3,
    }])
  })

  it('maps application mutations and details instead of asserting the wire DTO', async () => {
    const response = () => new Response(JSON.stringify({
      data: {
        id: 'application-2', reference: 'APP-002', property_id: 'property-2', status: 'draft',
        desired_start_on: '2026-11-01', term_months: 6, occupants: 1,
        updated_at: '2026-09-16T01:00:00Z', version: 1,
      },
    }), { status: 200, headers: { 'Content-Type': 'application/json' } })
    vi.stubGlobal('fetch', vi.fn().mockImplementation(response))
    const api = new HttpTenantPortalApi()

    await expect(api.createApplication({
      caseId: 'case-2', propertyId: 'property-2', desiredStartOn: '2026-11-01', termMonths: 6, occupants: 1,
    })).resolves.toMatchObject({ desiredStartOn: '2026-11-01', termMonths: 6, updatedAt: '2026-09-16T01:00:00Z' })
    await expect(api.getApplication('application-2')).resolves.toMatchObject({ id: 'application-2', property: { id: 'property-2' } })
  })

  it('unwraps lease pages and maps nested lease document fields', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
      data: { items: [{
        id: 'lease-1', reference: 'LEASE-001', status: 'active',
        property: { id: 'property-1', reference: 'P-001', address: '1 Harbour Street' },
        starts_on: '2026-09-01', ends_on: '2027-08-31', weekly_rent: '720.00', currency: 'AUD',
        executed_at: '2026-08-20T01:00:00Z',
        document: { id: 'document-1', version: 2, terms_digest: 'sha256:terms' },
      }] },
    }), { status: 200, headers: { 'Content-Type': 'application/json' } })))

    await expect(new HttpTenantPortalApi().listLeases()).resolves.toEqual([
      expect.objectContaining({
        id: 'lease-1', status: 'active', startsOn: '2026-09-01', weeklyRent: 720,
        document: { id: 'document-1', version: 2, termsDigest: 'sha256:terms' },
      }),
    ])
  })

  it('maps paginated invoice, maintenance, and report sections in my-property', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
      data: {
        lease: {
          id: 'lease-1', reference: 'LEASE-001', status: 'active',
          property: { id: 'property-1', reference: 'P-001', address: '1 Harbour Street' },
          starts_on: '2026-09-01', ends_on: '2027-08-31', weekly_rent: '720.00',
          document: { id: 'document-1', version: 2, terms_digest: 'sha256:terms' },
        },
        invoices: { items: [{ reference: 'INV-001', period_start: '2026-09-01', period_end: '2026-09-30', amount: '2880.00', status: 'open' }] },
        maintenance: { items: [{ id: 'order-1', reference: 'WO-001', summary: 'Leak', priority: 'high', status: 'in_progress', updated_at: '2026-09-16T02:00:00Z' }] },
        reports: { items: [{ id: 'report-1', title: 'Move-in report', property_id: 'property-1', source_lease_id: 'lease-1', status: 'active', completed_at: '2026-09-15T02:00:00Z' }] },
      },
    }), { status: 200, headers: { 'Content-Type': 'application/json' } })))

    await expect(new HttpTenantPortalApi().getCurrentProperty()).resolves.toMatchObject({
      lease: { id: 'lease-1', startsOn: '2026-09-01' },
      invoices: [{ id: 'INV-001', amount: 2880, status: 'due' }],
      maintenance: [{ id: 'order-1', priority: 'urgent', status: 'in_progress', updatedAt: '2026-09-16T02:00:00Z' }],
      reports: [{ id: 'report-1', propertyId: 'property-1', sourceLeaseId: 'lease-1', status: 'active' }],
    })
  })

  it('composes a historical property from lease, invoice, and lease-scoped report endpoints', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ data: {
        id: 'lease-old', reference: 'LEASE-OLD', status: 'ended',
        property: { id: 'property-old', reference: 'P-OLD', address: '9 History Lane' },
        starts_on: '2025-01-01', ends_on: '2025-12-31', weekly_rent: '500.00',
        document: { id: 'document-old', version: 1, terms_digest: 'sha256:old' },
      } }), { status: 200, headers: { 'Content-Type': 'application/json' } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ data: { items: [{ reference: 'INV-OLD', period_start: '2025-12-01', period_end: '2025-12-31', amount: '2000.00', status: 'paid' }] } }), { status: 200, headers: { 'Content-Type': 'application/json' } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ data: { items: [{ id: 'report-old', title: 'History report', property_id: 'property-old', source_lease_id: 'lease-old', status: 'active' }] } }), { status: 200, headers: { 'Content-Type': 'application/json' } }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(new HttpTenantPortalApi().getHistoricalProperty('lease-old')).resolves.toMatchObject({
      lease: { id: 'lease-old', status: 'ended' },
      invoices: [{ id: 'INV-OLD', status: 'paid' }],
      maintenance: [],
      reports: [{ id: 'report-old', sourceLeaseId: 'lease-old' }],
    })
    expect(fetchMock).toHaveBeenCalledTimes(3)
  })

  it('uses the Identity CSRF cookie when refreshing a real session', async () => {
    document.cookie = 'safescan_csrf=csrf-value; Path=/'
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({
        data: { access_token: 'tenant-token', portal: 'tenant' },
      }), { status: 200, headers: { 'Content-Type': 'application/json' } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        data: { customer: null, capabilities: ['property:read'], status_version: 0 },
      }), { status: 200, headers: { 'Content-Type': 'application/json' } }))
    vi.stubGlobal('fetch', fetchMock)

    await new HttpTenantPortalApi().restoreSession()

    expect(new Headers(fetchMock.mock.calls[0][1].headers).get('X-CSRF-Token')).toBe('csrf-value')
  })

  it('treats another Portal refresh session as an anonymous Tenant session', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({
        data: { access_token: 'staff-token', portal: 'staff' },
      }), { status: 200, headers: { 'Content-Type': 'application/json' } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        data: { customer: null, capabilities: ['property:read'], status_version: 0 },
      }), { status: 200, headers: { 'Content-Type': 'application/json' } }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(new HttpTenantPortalApi().restoreSession()).resolves.toMatchObject({ customer: null })
  })

  it('normalizes the BFF guest projection and maps domain scopes to UI capabilities', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
      data: {
        customer: { authenticated: false, username: null, status: null, status_version: 0 },
        capabilities: ['property:read_market'],
      },
    }), { status: 200, headers: { 'Content-Type': 'application/json' } })))

    await expect(new HttpTenantPortalApi().bootstrap()).resolves.toEqual({
      customer: null,
      capabilities: ['property:read'],
      statusVersion: 0,
    })
  })
})
