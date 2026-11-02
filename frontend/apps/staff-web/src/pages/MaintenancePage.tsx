import { useCallback, useState } from 'react'
import { staffPortalClient } from '../api/client'
import { useAuth } from '../auth/authContext'
import { EmptyState, ErrorState, PageLoading } from '../components/AsyncState'
import { PageHeader } from '../components/PageHeader'
import { useAsyncData } from '../hooks/useAsyncData'
import type { ApiError, MaintenanceOrder, MaintenanceStatus } from '../types'

const STATUS_LABELS: Record<MaintenanceStatus, string> = { open: '待分派', assigned: '已分派', in_progress: '处理中', blocked: '受阻', completed: '已完成', cancelled: '已取消' }
const PRIORITY_LABELS = { low: '低', medium: '中', high: '高', urgent: '紧急' }
const NEXT_STATUS: Partial<Record<MaintenanceStatus, MaintenanceStatus>> = { assigned: 'in_progress', in_progress: 'completed', blocked: 'in_progress' }

export function MaintenancePage() {
  const [status, setStatus] = useState<MaintenanceStatus | 'all'>('all')
  const [cursorStack, setCursorStack] = useState<string[]>([])
  const cursor = cursorStack.at(-1)
  const loader = useCallback(() => staffPortalClient.listMaintenancePage({ status: status === 'all' ? undefined : status, cursor }), [status, cursor])
  const { data, error, loading, reload } = useAsyncData(loader)
  const { session } = useAuth()
  const [updating, setUpdating] = useState<string | null>(null)
  const [actionError, setActionError] = useState<ApiError | null>(null)
  const isAdmin = session?.staff.role === 'manager_admin'

  const advance = async (order: MaintenanceOrder) => {
    const next = NEXT_STATUS[order.status]
    if (!next) return
    setUpdating(order.id)
    setActionError(null)
    try {
      await staffPortalClient.transitionMaintenanceOrder(order.id, next, order.version)
      await reload()
    } catch (reason) { setActionError(reason as ApiError) } finally { setUpdating(null) }
  }

  return <>
    <PageHeader eyebrow="MAINTENANCE OPERATIONS" title="维修工单" description={isAdmin ? '全局查看工单、租客和分派员工详情。' : '查看并处理当前职责范围内的维修任务。'} />
    <div className="toolbar"><select aria-label="按工单状态筛选" value={status} onChange={(event) => { setStatus(event.target.value as MaintenanceStatus | 'all'); setCursorStack([]) }}><option value="all">全部状态</option>{Object.entries(STATUS_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select><span>{loading ? '加载中…' : `本页 ${data?.items.length ?? 0} 条`}</span><button className="button secondary" onClick={() => void reload()} disabled={loading}>刷新</button></div>
    {data?.contextUnavailable ? <div className="notice" role="status">部分房源或负责人信息暂时无法加载，可点击刷新重试。</div> : null}
    {actionError ? <ErrorState error={actionError} retry={() => setActionError(null)} /> : null}
    {loading ? <PageLoading /> : error ? <ErrorState error={error} retry={() => void reload()} /> : !data?.items.length ? <EmptyState title="没有维修任务" description="当前页没有匹配工单，可调整状态或继续翻页。" /> : <div className="work-order-list">{data.items.map((order) => <article key={order.id} className="work-order-card">
      <div className={`priority ${order.priority}`}><span />{PRIORITY_LABELS[order.priority]}优先级</div>
      <div className="work-order-main"><div><small>{order.reference}</small><h3>{order.summary}</h3><p>{order.description}</p></div><span className={`pill ${order.status}`}>{STATUS_LABELS[order.status]}</span></div>
      <div className="work-order-meta"><span><small>房源</small><strong>{order.property.building.name}{order.property.room !== '—' ? ` · ${order.property.room}` : ''}</strong><em>{order.property.reference !== '—' ? order.property.reference : ''}</em></span>{isAdmin ? <span><small>报修租客</small><strong>{order.tenant.displayName}</strong><em>{order.tenant.email}</em></span> : null}<span><small>当前负责人</small><strong>{order.assignee?.displayName ?? '尚未分派'}</strong><em>{order.assignee?.staffCode !== '—' ? order.assignee?.staffCode : ''}</em></span><span><small>最近更新</small><strong>{new Date(order.updatedAt).toLocaleString('zh-CN')}</strong></span></div>
      <div className="card-actions"><span className="projection-label">版本 v{order.version} · 状态变更将写入审计时间线</span>{NEXT_STATUS[order.status] ? <button className="button primary compact" disabled={updating === order.id} onClick={() => void advance(order)}>{updating === order.id ? '提交中…' : `推进为「${STATUS_LABELS[NEXT_STATUS[order.status]!] }」`}</button> : null}</div>
    </article>)}</div>}
    <div className="maintenance-pagination"><button className="button secondary" disabled={loading || cursorStack.length === 0} onClick={() => setCursorStack((current) => current.slice(0, -1))}>上一页</button><span>第 {cursorStack.length + 1} 页 · 每页 50 条</span><button className="button secondary" disabled={loading || Boolean(error) || !data?.nextCursor || cursorStack.includes(data.nextCursor)} onClick={() => { const next = data?.nextCursor; if (next) setCursorStack((current) => [...current, next]) }}>下一页</button></div>
  </>
}
