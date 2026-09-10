import { HttpTenantPortalApi } from './httpAdapter'
import { MockTenantPortalApi } from './mockAdapter'

const params = new URLSearchParams(window.location.search)
export const isMockMode = params.get('api') !== 'real'
export const api = isMockMode ? new MockTenantPortalApi() : new HttpTenantPortalApi()
export { MockTenantPortalApi, mockPersonaLabels } from './mockAdapter'
export type { MockPersona } from './mockAdapter'
