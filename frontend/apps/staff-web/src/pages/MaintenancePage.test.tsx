import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MaintenancePage } from './MaintenancePage'

const { listMaintenancePage } = vi.hoisted(() => ({ listMaintenancePage: vi.fn() }))
vi.mock('../api/client', () => ({ staffPortalClient: { listMaintenancePage } }))
vi.mock('../auth/authContext', () => ({ useAuth: () => ({ session: { staff: { role: 'property_manager' } } }) }))

describe('maintenance page navigation', () => {
  it('keeps cursor pagination server-side and resets it when the status filter changes', async () => {
    listMaintenancePage.mockImplementation(({ cursor, status }) => Promise.resolve({ items: [], nextCursor: cursor || status ? undefined : 'page-2' }))
    render(<MaintenancePage />)
    await waitFor(() => expect(screen.getByRole('button', { name: '下一页' })).toBeEnabled())
    fireEvent.click(screen.getByRole('button', { name: '下一页' }))
    await waitFor(() => expect(listMaintenancePage).toHaveBeenLastCalledWith({ cursor: 'page-2', status: undefined }))
    expect(screen.getByText('第 2 页 · 每页 50 条')).toBeInTheDocument()
    fireEvent.change(screen.getByRole('combobox', { name: '按工单状态筛选' }), { target: { value: 'assigned' } })
    await waitFor(() => expect(listMaintenancePage).toHaveBeenLastCalledWith({ cursor: undefined, status: 'assigned' }))
    expect(screen.getByText('第 1 页 · 每页 50 条')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '上一页' })).toBeDisabled()
  })
})
