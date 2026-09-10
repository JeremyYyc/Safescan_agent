import { useCallback, useMemo, useState } from 'react'
import { staffPortalClient } from '../api/client'
import { EmptyState, ErrorState, PageLoading } from '../components/AsyncState'
import { PageHeader } from '../components/PageHeader'
import { useAsyncData } from '../hooks/useAsyncData'
import { ROLE_LABELS } from '../permissions'

export function StaffAdminPage() {
  const loader = useCallback(() => staffPortalClient.listStaff(), [])
  const { data, error, loading, reload } = useAsyncData(loader)
  const [query, setQuery] = useState('')
  const staff = useMemo(() => (data ?? []).filter((account) => `${account.displayName} ${account.email} ${account.staffCode}`.toLowerCase().includes(query.toLowerCase())), [data, query])
  return <>
    <PageHeader eyebrow="IDENTITY & ACCESS" title="员工账号与权限" description="查看 P0 员工账号、雇佣状态、角色与权限摘要。账号和范围变更将在 P1 开放。" />
    <div className="toolbar"><input className="search-input" aria-label="搜索员工" placeholder="搜索姓名、邮箱或员工编号" value={query} onChange={(event) => setQuery(event.target.value)} /><span className="readonly-badge">只读视图</span></div>
    {loading ? <PageLoading /> : error ? <ErrorState error={error} retry={() => void reload()} /> : staff.length === 0 ? <EmptyState title="没有匹配员工" description="调整搜索条件后再试。" /> : <div className="staff-grid">{staff.map((account) => <article className="staff-card" key={account.id}><div className="staff-card-head"><span className="avatar">{account.displayName.split(' ').map((part) => part[0]).join('')}</span><div><h3>{account.displayName}</h3><p>{account.email}</p></div><span className="status active">在职</span></div><dl><div><dt>员工编号</dt><dd>{account.staffCode}</dd></div><div><dt>角色</dt><dd>{ROLE_LABELS[account.role]}</dd></div><div><dt>权限数量</dt><dd>{account.permissions.length}</dd></div></dl><details><summary>查看权限摘要</summary><div className="permission-list">{account.permissions.map((permission) => <code key={permission}>{permission}</code>)}</div></details></article>)}</div>}
  </>
}
