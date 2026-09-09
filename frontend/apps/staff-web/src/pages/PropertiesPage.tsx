import { useCallback, useMemo, useState } from 'react'
import { staffPortalClient } from '../api/client'
import { useAuth } from '../auth/authContext'
import { EmptyState, ErrorState, PageLoading } from '../components/AsyncState'
import { PageHeader } from '../components/PageHeader'
import { CAPABILITIES, hasAnyPermission } from '../permissions'
import { useAsyncData } from '../hooks/useAsyncData'
import type { PropertySummary } from '../types'

const OCCUPANCY_LABELS = { vacant: '空置', reserved: '待入住', occupied: '在租' }

export function PropertiesPage() {
  const loader = useCallback(() => staffPortalClient.listProperties(), [])
  const { data, error, loading, reload } = useAsyncData(loader)
  const { session } = useAuth()
  const [building, setBuilding] = useState('all')
  const [query, setQuery] = useState('')
  const [reporting, setReporting] = useState<string | null>(null)
  const [notice, setNotice] = useState('')
  const canCreateReport = Boolean(session && hasAnyPermission(session.permissions, CAPABILITIES.createReport))
  const hasPortfolioProjection = Boolean(session && hasAnyPermission(session.permissions, CAPABILITIES.viewProperties))
  const buildings = useMemo(() => [...new Map((data ?? []).map((property) => [property.building.id, property.building])).values()], [data])
  const filtered = useMemo(() => (data ?? []).filter((property) => (building === 'all' || property.building.id === building) && `${property.reference} ${property.room} ${property.building.name}`.toLowerCase().includes(query.toLowerCase())), [data, building, query])

  const createReport = async (property: PropertySummary) => {
    setReporting(property.id)
    setNotice('')
    try {
      const result = await staffPortalClient.createPropertyReport(property.id)
      setNotice(`${property.reference} 的报告任务已创建（${result.jobId}）`)
    } catch (reason) {
      setNotice(reason instanceof Error ? reason.message : '报告任务创建失败')
    } finally { setReporting(null) }
  }

  return <>
    <PageHeader eyebrow="PROPERTY PORTFOLIO" title="房源信息" description="按权限查看房间状态、租赁摘要与维护情况。" />
    <div className="toolbar"><input className="search-input" aria-label="搜索房源" placeholder="搜索楼宇、房号或编号" value={query} onChange={(event) => setQuery(event.target.value)} /><select aria-label="按楼宇筛选" value={building} onChange={(event) => setBuilding(event.target.value)}><option value="all">全部楼宇</option>{buildings.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select><button className="button secondary" onClick={() => void reload()}>刷新</button></div>
    {notice ? <div className="notice" role="status">{notice}</div> : null}
    {loading ? <PageLoading /> : error ? <ErrorState error={error} retry={() => void reload()} /> : filtered.length === 0 ? <EmptyState title="没有匹配房源" description="调整楼宇或搜索条件后再试。" /> : <div className="property-grid">{filtered.map((property) => <article className="property-card" key={property.id}>
      <div className="property-visual"><span>{property.building.name.split(' ').map((word) => word[0]).join('')}</span><span className={`status ${property.occupancy}`}>{OCCUPANCY_LABELS[property.occupancy]}</span></div>
      <div className="property-body"><div className="property-title"><div><small>{property.reference}</small><h3>{property.building.name} · {property.room}</h3></div>{hasPortfolioProjection ? <strong>${property.weeklyRent}<small>/周</small></strong> : null}</div>
        <div className="facts"><span>{property.bedrooms} 卧室</span><span>{property.bathrooms} 卫浴</span><span>{property.openMaintenance} 个开放工单</span>{hasPortfolioProjection ? <span>{property.reports} 份报告</span> : null}</div>
        {property.tenant ? <div className="detail-strip"><span><small>当前租户</small>{property.tenant.displayName}</span><span><small>租约</small>{property.lease?.reference}</span><span><small>缴费摘要</small>{property.billing?.overdue ? `逾期 $${property.billing.overdue}` : '无逾期'}</span></div> : <div className="detail-strip"><span><small>地址</small>{property.building.address}</span><span><small>发布状态</small>{property.listingStatus === 'marketing' ? '公开招租' : '内部房源'}</span></div>}
        <div className="card-actions"><span className="projection-label">已加载完整授权投影</span>{canCreateReport ? <button className="button primary compact" disabled={reporting === property.id} onClick={() => void createReport(property)}>{reporting === property.id ? '创建中…' : '创建视频报告'}</button> : null}</div>
      </div>
    </article>)}</div>}
  </>
}
