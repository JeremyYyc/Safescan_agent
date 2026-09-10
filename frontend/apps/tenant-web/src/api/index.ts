import { HttpTenantPortalApi } from './httpAdapter'
import { MockTenantPortalApi } from './mockAdapter'

const API_MODE_KEY = 'safescan.tenant.api-mode'
const requested = new URLSearchParams(window.location.search).get('api')
if (requested === 'real' || requested === 'mock') sessionStorage.setItem(API_MODE_KEY, requested)
const apiMode = requested === 'real' || requested === 'mock'
  ? requested
  : sessionStorage.getItem(API_MODE_KEY) === 'real' ? 'real' : 'mock'
export const isMockMode = apiMode !== 'real'
export const api = isMockMode ? new MockTenantPortalApi() : new HttpTenantPortalApi()
export { MockTenantPortalApi, mockPersonaLabels } from './mockAdapter'
export type { MockPersona } from './mockAdapter'
