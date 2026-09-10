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
