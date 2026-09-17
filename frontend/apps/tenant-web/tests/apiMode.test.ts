// @vitest-environment jsdom

import { beforeEach, describe, expect, it } from 'vitest'
import { getTenantApiMode } from '../src/api/mode'

describe('tenant API mode selection', () => {
  beforeEach(() => {
    sessionStorage.clear()
    window.history.replaceState({}, '', '/tenant/')
  })

  it('uses real mode by default', () => {
    expect(getTenantApiMode()).toBe('real')
  })

  it('uses mock mode only when explicitly requested', () => {
    window.history.replaceState({}, '', '/tenant/?api=mock')
    expect(getTenantApiMode()).toBe('mock')
  })

  it('keeps an explicit mode across client-side navigation', () => {
    window.history.replaceState({}, '', '/tenant/?api=mock')
    expect(getTenantApiMode()).toBe('mock')

    window.history.replaceState({}, '', '/tenant/properties')
    expect(getTenantApiMode()).toBe('mock')

    window.history.replaceState({}, '', '/tenant/?api=real')
    expect(getTenantApiMode()).toBe('real')
  })
})
