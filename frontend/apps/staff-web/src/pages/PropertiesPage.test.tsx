import { MemoryRouter } from 'react-router-dom'
import { render, screen } from '@testing-library/react'
import { PropertiesPage } from './PropertiesPage'
import { PROPERTIES } from '../api/mockData'

vi.mock('../auth/authContext', () => ({ useAuth: () => ({ session: { staff: { role: 'property_manager' }, permissions: ['property:manage_assigned'] } }) }))
vi.mock('../hooks/useAsyncData', () => ({ useAsyncData: () => ({ data: PROPERTIES, loading: false, reload: vi.fn() }) }))

describe('manager property portfolios', () => {
  it('keeps vacancies separate and groups occupied and reserved homes together', () => {
    const { unmount } = render(<MemoryRouter><PropertiesPage /></MemoryRouter>)
    for (const property of PROPERTIES) {
      expect(Boolean(screen.queryByText(property.reference))).toBe(property.occupancy === 'vacant')
    }
    unmount()
    render(<MemoryRouter><PropertiesPage portfolio="tenancies" /></MemoryRouter>)
    for (const property of PROPERTIES) {
      expect(Boolean(screen.queryByText(property.reference))).toBe(property.occupancy !== 'vacant')
    }
  })
})
