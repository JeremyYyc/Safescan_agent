export type ApiMode = 'real' | 'mock'

const API_MODE_KEY = 'safescan.tenant.api-mode'

export function getTenantApiMode(): ApiMode {
  const requested = new URLSearchParams(window.location.search).get('api')
  if (requested === 'real' || requested === 'mock') {
    sessionStorage.setItem(API_MODE_KEY, requested)
    return requested
  }
  return sessionStorage.getItem(API_MODE_KEY) === 'mock' ? 'mock' : 'real'
}
