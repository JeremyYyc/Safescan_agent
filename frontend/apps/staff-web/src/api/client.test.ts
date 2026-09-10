import { getApiMode } from './client'

describe('API mode selection', () => {
  beforeEach(() => {
    sessionStorage.clear()
    window.history.replaceState({}, '', '/staff/')
  })

  it('persists an explicit real mode across client-side navigation and reload paths', () => {
    window.history.replaceState({}, '', '/staff/?api=real')
    expect(getApiMode()).toBe('real')

    window.history.replaceState({}, '', '/staff/properties')
    expect(getApiMode()).toBe('real')
  })

  it('allows an explicit mock mode to replace the remembered real mode', () => {
    sessionStorage.setItem('safescan.staff.api-mode', 'real')
    window.history.replaceState({}, '', '/staff/?api=mock')
    expect(getApiMode()).toBe('mock')
  })
})
