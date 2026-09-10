import { HttpTenantPortalApi } from './httpAdapter'
import { MockTenantPortalApi } from './mockAdapter'
import { getTenantApiMode } from './mode'

const apiMode = getTenantApiMode()
export const isMockMode = apiMode !== 'real'
export const api = isMockMode ? new MockTenantPortalApi() : new HttpTenantPortalApi()
export { MockTenantPortalApi, mockPersonaLabels } from './mockAdapter'
export type { MockPersona } from './mockAdapter'
