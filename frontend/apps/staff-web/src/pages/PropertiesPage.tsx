import { useCallback, useMemo, useState } from 'react'
import { staffPortalClient } from '../api/client'
import { useAuth } from '../auth/authContext'
import { EmptyState, ErrorState, PageLoading } from '../components/AsyncState'
import { PageHeader } from '../components/PageHeader'
import { PropertyVisual } from '../components/PropertyVisual'
import { CAPABILITIES, hasAnyPermission } from '../permissions'
import { useAsyncData } from '../hooks/useAsyncData'
import type { PropertySummary } from '../types'
import { LeasePdfDocument } from '../../../../shared/LeasePdfDocument'
import { AccessibleDialog } from '../../../../shared/AccessibleDialog'

export function PropertiesPage({ portfolio = 'vacancies' }: { portfolio?: 'vacancies' | 'tenancies' }) {
  const loader = useCallback(() => staffPortalClient.listProperties(), [])
  const { data, error, loading, reload } = useAsyncData(loader)
  const { session } = useAuth()
  const splitPortfolio = session?.staff.role === 'property_manager'
  const portfolioProperties = useMemo(() => (data ?? []).filter((property) => !splitPortfolio || (portfolio === 'tenancies' ? property.occupancy !== 'vacant' : property.occupancy === 'vacant')), [data, portfolio, splitPortfolio])
  const [building, setBuilding] = useState('all')
  const [query, setQuery] = useState('')
  const [reporting, setReporting] = useState<string | null>(null)
  const [notice, setNotice] = useState('')
  const [contractLeaseId, setContractLeaseId] = useState<string | null>(null)
  const canCreateReport = Boolean(session && hasAnyPermission(session.permissions, CAPABILITIES.createReport))
  const hasPortfolioProjection = Boolean(session && hasAnyPermission(session.permissions, CAPABILITIES.viewProperties))
  const buildings = useMemo(() => [...new Map(portfolioProperties.map((property) => [property.building.id, property.building])).values()], [portfolioProperties])
  const filtered = useMemo(() => portfolioProperties.filter((property) => (building === 'all' || property.building.id === building) && `${property.reference} ${property.room} ${property.building.name}`.toLowerCase().includes(query.toLowerCase())), [portfolioProperties, building, query])

  const createReport = async (property: PropertySummary) => {
    setReporting(property.id)
    setNotice('')
    try {
      const result = await staffPortalClient.createPropertyReport(property.id)
      setNotice(`${property.reference} 的检查报告已创建（${result.reportId}），可继续上传视频并启动分析。`)
    } catch (reason) {
      setNotice(reason instanceof Error ? reason.message : '报告任务创建失败')
    } finally { setReporting(null) }
  }

  return <>
    <PageHeader eyebrow="PROPERTY PORTFOLIO" title={splitPortfolio ? portfolio === 'tenancies' ? '在租与待入住' : '空置房源' : '房源信息'} description={splitPortfolio ? portfolio === 'tenancies' ? '集中查看在租和待入住的房源、租约与维护情况。' : '集中管理空置房源与招租状态。' : '按权限查看房间状态、租赁摘要与维护情况。'} />
    <div className="toolbar"><input className="search-input" aria-label="搜索房源" placeholder="搜索楼宇、房号或编号" value={query} onChange={(event) => setQuery(event.target.value)} /><select aria-label="按楼宇筛选" value={building} onChange={(event) => setBuilding(event.target.value)}><option value="all">全部楼宇</option>{buildings.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select><button className="button secondary" onClick={() => void reload()}>刷新</button></div>
    {notice ? <div className="notice" role="status">{notice}</div> : null}
    {loading ? <PageLoading /> : error ? <ErrorState error={error} retry={() => void reload()} /> : filtered.length === 0 ? <EmptyState title="没有匹配房源" description="调整楼宇或搜索条件后再试。" /> : <div className="property-grid">{filtered.map((property) => <article className="property-card" key={property.id}>
      <PropertyVisual property={property} />
      <div className="property-body"><div className="property-title"><div><small>{property.reference}</small><h3>{property.building.name} · {property.room}</h3></div>{hasPortfolioProjection ? <strong>${property.weeklyRent}<small>/周</small></strong> : null}</div>
        <div className="facts"><span>{property.bedrooms} 卧室</span><span>{property.bathrooms} 卫浴</span><span>{property.openMaintenance} 个开放工单</span>{hasPortfolioProjection ? <span>{property.reports} 份报告</span> : null}</div>
        {property.tenant ? <div className="detail-strip"><span><small>当前租户</small>{property.tenant.displayName}</span><span><small>租约</small>{property.lease?.reference}</span><span><small>缴费摘要</small>{property.billing?.overdue ? `逾期 $${property.billing.overdue}` : '无逾期'}</span></div> : <div className="detail-strip"><span><small>地址</small>{property.building.address}</span><span><small>发布状态</small>{property.listingStatus === 'marketing' ? '公开招租' : '内部房源'}</span></div>}
        <div className="card-actions">{property.lease?.id ? <button className="document-link" onClick={() => { if (property.lease?.id) setContractLeaseId(property.lease.id) }}>查看合同 PDF</button> : null}<span className="projection-label">已加载完整授权投影</span>{canCreateReport ? <button className="button primary compact" disabled={reporting === property.id} onClick={() => void createReport(property)}>{reporting === property.id ? '创建中…' : '创建视频报告'}</button> : null}</div>
      </div>
    </article>)}</div>}
    {contractLeaseId ? <div className="modal-backdrop" role="presentation" onMouseDown={() => setContractLeaseId(null)}><AccessibleDialog className="modal" labelledBy="property-contract-title" onClose={() => setContractLeaseId(null)}><div className="modal-head"><h2 id="property-contract-title">租赁合同</h2><button aria-label="关闭合同" onClick={() => setContractLeaseId(null)}>×</button></div><LeasePdfDocument key={contractLeaseId} leaseId={contractLeaseId} client={staffPortalClient} /></AccessibleDialog></div> : null}
  </>
}
