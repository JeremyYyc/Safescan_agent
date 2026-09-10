// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../src/api/contracts'
import { MockTenantPortalApi, type MockPersona } from '../src/api/mockAdapter'

describe('Tenant Portal P0 capability matrix', () => {
  beforeEach(() => localStorage.clear())

  const expected: Array<[MockPersona, string[]]> = [
    ['guest', ['property:read']],
    ['prospect', ['property:read', 'contact:create', 'application:read', 'application:create', 'lease:read', 'agent:access']],
    ['executed_tenant', ['property:read', 'contact:create', 'application:read', 'lease:read', 'my-property:read', 'agent:access']],
    ['active_tenant', ['property:read', 'contact:create', 'application:read', 'lease:read', 'my-property:read', 'maintenance:create', 'report:create', 'agent:access']],
    ['former_tenant', ['property:read', 'contact:create', 'application:read', 'application:create', 'lease:read', 'my-property:read', 'report:read-history', 'agent:access']],
  ]

  it.each(expected)('%s receives only its server-projected capabilities', async (persona, capabilities) => {
    const view = await new MockTenantPortalApi(persona).bootstrap()
    expect(view.capabilities).toEqual(expect.arrayContaining(capabilities))
    expect(view.capabilities.includes('maintenance:create')).toBe(persona === 'active_tenant')
    expect(view.capabilities.includes('report:create')).toBe(persona === 'active_tenant')
  })

  it('blocks executed tenants from maintenance and report generation', async () => {
    const adapter = new MockTenantPortalApi('executed_tenant')
    await expect(adapter.createMaintenance('漏水', '', 'normal')).rejects.toMatchObject({ status: 403, code: 'action_forbidden' })
    await expect(adapter.startReport(new File(['video'], 'home.mp4', { type: 'video/mp4' }), {}, vi.fn())).rejects.toMatchObject({ status: 403, code: 'report_generation_not_allowed' })
  })

  it('keeps former tenant history read-only and lease-scoped', async () => {
    const adapter = new MockTenantPortalApi('former_tenant')
    const history = await adapter.getHistoricalProperty('lease-history')
    expect(history.reports.every((report) => report.sourceLeaseId === 'lease-history')).toBe(true)
    await expect(adapter.getHistoricalProperty('another-customer-lease')).rejects.toBeInstanceOf(ApiError)
  })

  it('allows guests to browse but requires authentication to contact', async () => {
    const adapter = new MockTenantPortalApi('guest')
    expect(await adapter.listProperties()).not.toHaveLength(0)
    await expect(adapter.contactProperty('prop-harbour', 'Hello')).rejects.toMatchObject({ status: 401 })
  })
})
