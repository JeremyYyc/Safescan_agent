import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { OrdersPage } from './OrdersPage'

const { listOrderPage } = vi.hoisted(() => ({ listOrderPage: vi.fn() }))
vi.mock('../api/client', () => ({ staffPortalClient: { listOrderPage } }))
vi.mock('../auth/authContext', () => ({ useAuth: () => ({ session: { staff: { role: 'leasing_consultant' } } }) }))

describe('order search', () => {
  beforeEach(() => { listOrderPage.mockReset() })

  it('submits a trimmed server query, keeps it across pages and stages, and clears it', async () => {
    listOrderPage.mockImplementation((cursor) => Promise.resolve({ items: [], total: 101, nextCursor: cursor ? undefined : 'page-2' }))
    render(<OrdersPage />)
    await waitFor(() => expect(screen.getByRole('button', { name: '搜索' })).toBeEnabled())
    fireEvent.change(screen.getByRole('searchbox', { name: '搜索订单' }), { target: { value: '  Alice & 1204  ' } })
    expect(listOrderPage).toHaveBeenCalledTimes(1)
    fireEvent.submit(screen.getByRole('search', { name: '订单查询' }))
    await waitFor(() => expect(listOrderPage).toHaveBeenLastCalledWith(undefined, undefined, 'Alice & 1204'))
    await waitFor(() => expect(screen.getByRole('button', { name: '下一页' })).toBeEnabled())
    fireEvent.click(screen.getByRole('button', { name: '下一页' }))
    await waitFor(() => expect(listOrderPage).toHaveBeenLastCalledWith('page-2', undefined, 'Alice & 1204'))
    fireEvent.click(screen.getByRole('button', { name: '历史合同' }))
    await waitFor(() => expect(listOrderPage).toHaveBeenLastCalledWith(undefined, 'ended', 'Alice & 1204'))
    expect(screen.getByText('第 1 页 · 每页 50 条')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '清空' }))
    await waitFor(() => expect(listOrderPage).toHaveBeenLastCalledWith(undefined, 'ended', undefined))
    expect(screen.getByRole('searchbox', { name: '搜索订单' })).toHaveValue('')
  })

  it('does not let a slower search overwrite results after clearing the query', async () => {
    let finishSearch: (value: { items: []; total: number }) => void = () => {}
    listOrderPage.mockImplementation((_cursor, _stage, query) => query
      ? new Promise((resolve) => { finishSearch = resolve })
      : Promise.resolve({ items: [], total: 550 }))
    render(<OrdersPage />)
    await screen.findByText('550')
    fireEvent.change(screen.getByRole('searchbox', { name: '搜索订单' }), { target: { value: 'Alice' } })
    fireEvent.submit(screen.getByRole('search', { name: '订单查询' }))
    await waitFor(() => expect(listOrderPage).toHaveBeenLastCalledWith(undefined, undefined, 'Alice'))
    fireEvent.click(screen.getByRole('button', { name: '清空' }))
    await waitFor(() => expect(listOrderPage).toHaveBeenLastCalledWith(undefined, undefined, undefined))
    await act(async () => { finishSearch({ items: [], total: 10 }) })
    expect(screen.getByText('550')).toBeInTheDocument()
    expect(screen.queryByText('10')).not.toBeInTheDocument()
  })
})
