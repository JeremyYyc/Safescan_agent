import { defaultStaffPath, ordersLabel, postLoginPath, staffNavigation } from './navigation'
import { ROLE_PERMISSIONS } from './permissions'

describe('staff navigation', () => {
  it('keeps work-context permission inside maintenance and removes the Maintainer property page', () => {
    const items = staffNavigation('maintainer', ROLE_PERMISSIONS.maintainer)

    expect(items.map((item) => item.to)).toEqual(['/maintenance', '/agent'])
    expect(defaultStaffPath('maintainer')).toBe('/maintenance')
    expect(postLoginPath('maintainer', '/properties')).toBe('/maintenance')
  })

  it('uses role-specific order wording', () => {
    const adminOrders = staffNavigation('manager_admin', ROLE_PERMISSIONS.manager_admin)
      .find((item) => item.to === '/orders')
    const consultantOrders = staffNavigation('leasing_consultant', ROLE_PERMISSIONS.leasing_consultant)
      .find((item) => item.to === '/orders')

    expect(adminOrders?.label).toBe('租房订单')
    expect(consultantOrders?.label).toBe('我的订单')
    expect(ordersLabel('manager_admin')).toBe('租房订单')
  })
})
