import { DEMO_PASSWORDS, MOCK_STAFF } from './mockData'
import { MockStaffPortalClient } from './mockClient'

describe('MockStaffPortalClient', () => {
  beforeEach(() => { document.cookie = 'safescan_mock_staff=; Path=/staff; Max-Age=0' })

  it('uses the same auth and client interface while restoring a cookie-backed mock session', async () => {
    const client = new MockStaffPortalClient()
    const session = await client.login({ email: MOCK_STAFF.property_manager.email, password: DEMO_PASSWORDS.property_manager })
    client.setAccessToken(session.accessToken)
    expect((await client.refresh()).staff.role).toBe('property_manager')
    expect((await client.bootstrap()).permissions).toContain('report:generate_assigned')
  })

  it('projects private tenant details away from leasing consultants', async () => {
    const client = new MockStaffPortalClient()
    const session = await client.login({ email: MOCK_STAFF.leasing_consultant.email, password: DEMO_PASSWORDS.leasing_consultant })
    client.setAccessToken(session.accessToken)
    const properties = await client.listProperties()
    expect(properties.every((property) => property.occupancy === 'vacant')).toBe(true)
    expect(properties.every((property) => property.tenant === undefined)).toBe(true)
    const orders = await client.listOrders()
    expect(orders.some((order) => order.stage === 'pending_signature' && order.contract)).toBe(true)
    expect(orders.some((order) => order.stage === 'executed' && order.contract)).toBe(true)
  })

  it('limits maintainers to their assigned work orders', async () => {
    const client = new MockStaffPortalClient()
    const session = await client.login({ email: MOCK_STAFF.maintainer.email, password: DEMO_PASSWORDS.maintainer })
    client.setAccessToken(session.accessToken)
    const orders = await client.listMaintenanceOrders()
    expect(orders.length).toBeGreaterThan(0)
    expect(orders.every((order) => order.assignee?.staffCode === session.staff.staffCode)).toBe(true)
    const workContext = await client.listProperties()
    expect(workContext.every((property) => property.tenant === undefined && property.lease === undefined)).toBe(true)
  })

  it('rejects video report creation for roles without the permission', async () => {
    const client = new MockStaffPortalClient()
    const session = await client.login({ email: MOCK_STAFF.leasing_consultant.email, password: DEMO_PASSWORDS.leasing_consultant })
    client.setAccessToken(session.accessToken)
    await expect(client.createPropertyReport('property-hh-1204')).rejects.toMatchObject({ status: 403 })
  })

  it('creates a draft report without inventing a job before video upload', async () => {
    const client = new MockStaffPortalClient()
    const session = await client.login({ email: MOCK_STAFF.property_manager.email, password: DEMO_PASSWORDS.property_manager })
    client.setAccessToken(session.accessToken)

    await expect(client.createPropertyReport('property-hh-1204')).resolves.toEqual({
      reportId: expect.stringMatching(/^report-/),
    })
  })
})
