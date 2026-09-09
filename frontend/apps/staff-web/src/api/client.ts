import type { StaffPortalClient } from '../types'
import { MockStaffPortalClient } from './mockClient'
import { RealStaffPortalClient } from './realClient'

export type ApiMode = 'mock' | 'real'

export function getApiMode(): ApiMode {
  return new URLSearchParams(window.location.search).get('api') === 'real' ? 'real' : 'mock'
}

export function createStaffPortalClient(mode: ApiMode = getApiMode()): StaffPortalClient {
  return mode === 'real' ? new RealStaffPortalClient() : new MockStaffPortalClient()
}

export const staffPortalClient = createStaffPortalClient()
