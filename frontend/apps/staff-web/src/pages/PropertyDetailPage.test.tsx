import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { PropertyDetailPage } from './PropertyDetailPage'

vi.mock('../api/client', async () => {
  const { RealStaffPortalClient } = await import('../api/realClient')
  return { staffPortalClient: new RealStaffPortalClient() }
})
vi.mock('../auth/authContext', () => ({ useAuth: () => ({ session: { staff: { role: 'leasing_consultant' }, permissions: ['property:read_market', 'lease:prepare'] } }) }))

describe('leasing consultant property history', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('shows the property and authorized leases when restricted history is absent', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ data: {
      property: { id: 'p1', reference: 'P-1', address: 'Melbourne VIC', status: 'marketing',
        attributes: { room_number: '101' }, building: { id: 'b1', name: 'Melbourne House', address: 'Melbourne VIC' } },
      leases: { items: [{ id: 'l1', reference: 'L-1', status: 'ended', tenant: { display_name: 'Assigned tenant' } }] },
    }, meta: { partial_errors: [{ component: 'maintenance' }, { component: 'recent_reports' }] } }), {
      status: 200, headers: { 'Content-Type': 'application/json' },
    }))
    vi.stubGlobal('fetch', fetchMock)
    render(<MemoryRouter initialEntries={['/properties/p1']}><Routes><Route path="/properties/:id" element={<PropertyDetailPage />} /></Routes></MemoryRouter>)
    expect(await screen.findByRole('heading', { name: 'Melbourne House · 101' })).toBeInTheDocument()
    expect(screen.getByText('Assigned tenant')).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('部分关联记录暂不可用')
    fireEvent.click(screen.getByRole('tab', { name: '检查记录 (0)' }))
    expect(screen.getByText('暂无可查看的检查记录。')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('tab', { name: '维修工单 (0)' }))
    expect(screen.getByText('暂无维修工单。')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledOnce()
  })

  it('shows a retryable error instead of unmounting the page after an unexpected response', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response('invalid JSON', { status: 200, headers: { 'Content-Type': 'application/json' } }))
      .mockResolvedValue(new Response(JSON.stringify({ data: {
        property: { id: 'p1', reference: 'P-1', address: 'Melbourne VIC', building: { id: 'b1', name: 'Recovered house' } },
        leases: { items: [] },
      } }), { status: 200, headers: { 'Content-Type': 'application/json' } }))
    vi.stubGlobal('fetch', fetchMock)
    render(<MemoryRouter initialEntries={['/properties/p1']}><Routes><Route path="/properties/:id" element={<PropertyDetailPage />} /></Routes></MemoryRouter>)
    expect(await screen.findByRole('alert')).toHaveTextContent('数据加载失败，请稍后重试。')
    fireEvent.click(screen.getByRole('button', { name: '重试' }))
    expect(await screen.findByRole('heading', { name: 'Recovered house · —' })).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })
})
