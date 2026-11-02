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
    expect(orders.every((order) => order.property.id && order.property.building.name)).toBe(true)
    await expect(client.listProperties()).rejects.toMatchObject({ status: 403 })
  })

  it('searches only authorized mock orders with literal case-insensitive text', async () => {
    const client = new MockStaffPortalClient()
    const session = await client.login({ email: MOCK_STAFF.leasing_consultant.email, password: DEMO_PASSWORDS.leasing_consultant })
    client.setAccessToken(session.accessToken)
    const page = await client.listOrderPage(undefined, 'executed', ' MIA.CHEN ')
    expect(page.total).toBe(1)
    expect(page.items[0].customer.displayName).toBe('Mia Chen')
    expect((await client.listOrderPage(undefined, undefined, 'Jack Thompson')).total).toBe(0)
    expect((await client.listOrderPage(undefined, undefined, '%')).total).toBe(0)
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

it('keeps mock city ownership consistent and blocks cross-city report creation', async () => {
  document.cookie = 'safescan_mock_staff=; Path=/staff; Max-Age=0'
  const client = new MockStaffPortalClient()
  const session = await client.login({ email: MOCK_STAFF.property_manager.email, password: DEMO_PASSWORDS.property_manager })
  client.setAccessToken(session.accessToken)
  expect((await client.listProperties()).every((property) => property.building.cityId === session.staff.cityId)).toBe(true)
  await expect(client.createPropertyReport('property-pr-0305')).rejects.toMatchObject({ status: 404 })
})

it('shows all sixteen staff with consistent city coverage and account format', async () => {
  const { STAFF_ACCOUNTS } = await import('./mockData')
  expect(STAFF_ACCOUNTS).toHaveLength(16)
  expect(new Set(STAFF_ACCOUNTS.map((staff) => staff.staffCode)).size).toBe(16)
  for (const city of ['sydney', 'melbourne', 'brisbane', 'adelaide', 'perth']) {
    for (const role of ['leasing_consultant', 'property_manager', 'maintainer']) {
      expect(STAFF_ACCOUNTS.some((staff) => staff.cityId === city && staff.role === role)).toBe(true)
    }
  }
  for (const staff of STAFF_ACCOUNTS) {
    expect(staff.email).toBe(`${staff.displayName.split(' ')[0]}Safescan@outlook.com`)
    expect(staff.staffCode).toMatch(/^(LC|PM|MT|MA)\d{3}$/)
  }
})
