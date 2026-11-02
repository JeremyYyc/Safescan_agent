import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { StaffAdminPage } from './StaffAdminPage'

const { listStaff } = vi.hoisted(() => ({ listStaff: vi.fn() }))
vi.mock('../api/client', () => ({ staffPortalClient: { listStaff } }))

it('shows database permission codes and differentiates empty and unavailable summaries', async () => {
  const common = { role:'maintainer',employmentStatus:'active',cityId:'perth',email:'staff@example.test' }
  listStaff.mockResolvedValue([
    { ...common,id:'s1',staffCode:'MT005',displayName:'Benjamin Scott',permissions:['custom:database_scope','work_order:read_assigned'] },
    { ...common,id:'s2',staffCode:'EMPTY',displayName:'Empty role',permissions:[] },
    { ...common,id:'s3',staffCode:'MISSING',displayName:'Missing summary',permissions:null },
  ])
  render(<StaffAdminPage />)
  const benjamin = within((await screen.findByText('Benjamin Scott')).closest('article')!)
  expect(benjamin.getByText('2')).toBeInTheDocument()
  fireEvent.click(benjamin.getByText('查看权限摘要'))
  expect(benjamin.getByText('custom:database_scope')).toBeVisible()
  expect(benjamin.getByText('work_order:read_assigned')).toBeVisible()
  const empty = within(screen.getByText('Empty role').closest('article')!)
  expect(empty.getByText('0')).toBeInTheDocument()
  fireEvent.click(empty.getByText('查看权限摘要'))
  expect(empty.getByText('该角色未配置权限。')).toBeVisible()
  const missing = within(screen.getByText('Missing summary').closest('article')!)
  expect(missing.getByText('未获取')).toBeInTheDocument()
  expect(missing.queryByText('0')).not.toBeInTheDocument()
  fireEvent.click(missing.getByText('查看权限摘要'))
  expect(missing.getByText('权限摘要暂未获取，请刷新重试。')).toBeVisible()
  fireEvent.click(screen.getByRole('button', { name:'刷新' }))
  await waitFor(() => expect(screen.getByText('Benjamin Scott')).toBeInTheDocument())
  expect(listStaff).toHaveBeenCalledTimes(2)
})
