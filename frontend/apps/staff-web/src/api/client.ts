import type { StaffPortalClient } from '../types'
import { MockStaffPortalClient } from './mockClient'
import { RealStaffPortalClient } from './realClient'

export type ApiMode = 'mock' | 'real'
const API_MODE_KEY = 'safescan.staff.api-mode'

export function getApiMode(): ApiMode {
  const requested = new URLSearchParams(window.location.search).get('api')
  if (requested === 'real' || requested === 'mock') {
    sessionStorage.setItem(API_MODE_KEY, requested)
    return requested
  }
  return sessionStorage.getItem(API_MODE_KEY) === 'real' ? 'real' : 'mock'
}

export function createStaffPortalClient(mode: ApiMode = getApiMode()): StaffPortalClient {
  return mode === 'real' ? new RealStaffPortalClient() : new MockStaffPortalClient()
}

export const staffPortalClient = createStaffPortalClient()
