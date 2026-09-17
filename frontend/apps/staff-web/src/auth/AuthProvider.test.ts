import { MOCK_STAFF } from '../api/mockData'
import type { BootstrapData, Session } from '../types'
import { mergeBootstrap } from './session'

describe('mergeBootstrap', () => {
  it('does not let a bootstrap subject UUID replace the Identity username or display name', () => {
    const subjectId = '3bcd3db5-2d7c-4c20-b489-c70abc8bf107'
    const session: Session = {
      accessToken: 'token',
      expiresIn: 900,
      permissions: [],
      staff: { ...MOCK_STAFF.property_manager, id: subjectId },
    }
    const bootstrap: BootstrapData = {
      permissions: ['property:manage_assigned'],
      staff: {
        id: subjectId,
        username: subjectId,
        displayName: subjectId,
        email: '',
        staffCode: '',
        role: 'property_manager',
      },
    }

    const merged = mergeBootstrap(session, bootstrap)

    expect(merged.staff.username).toBe('NoahMitchell')
    expect(merged.staff.displayName).toBe('Noah Mitchell')
    expect(merged.staff.email).toBe('NoahSafescan@outlook.com')
  })

  it('uses a real username supplied by the Staff bootstrap projection', () => {
    const session: Session = {
      accessToken: 'token',
      expiresIn: 900,
      permissions: [],
      staff: MOCK_STAFF.manager_admin,
    }
    const bootstrap: BootstrapData = {
      permissions: ['lease:manage_all'],
      staff: { ...MOCK_STAFF.manager_admin, username: 'CharlotteAdmin' },
    }

    expect(mergeBootstrap(session, bootstrap).staff.username).toBe('CharlotteAdmin')
  })
})
