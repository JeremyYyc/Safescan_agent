import { useCallback, useState } from 'react'
import { Link, useLocation, useParams } from 'react-router-dom'
import { staffPortalClient } from '../api/client'
import { ErrorState, PageLoading } from '../components/AsyncState'
import { PageHeader } from '../components/PageHeader'
import { PropertyVisual } from '../components/PropertyVisual'
import { useAsyncData } from '../hooks/useAsyncData'
import { ApiError, type MaintenanceOrder } from '../types'
import { LeasePdfDocument } from '../../../../shared/LeasePdfDocument'
import { AccessibleDialog } from '../../../../shared/AccessibleDialog'

const STATUS: Record<string, string> = { active: '在租', executed: '待入住', ended: '已结束', completed: '已完成', planned: '已计划',
  open: '待分派', assigned: '已分派', in_progress: '处理中', blocked: '受阻', cancelled: '已取消' }
const KIND: Record<string, string> = { move_in: '入住检查', move_out: '退租检查', routine: '定期检查', video: '视频检查' }
const FIELDS: Array<[string, string]> = [['address', '地址'], ['propertyType', '房屋类型'], ['bedrooms', '卧室'], ['bathrooms', '卫浴'],
  ['roomsCount', '房间总数'], ['bedCount', '床位'], ['kitchenCount', '厨房'], ['livingRoomCount', '起居区'], ['parkingSpaces', '配属车位'],
  ['floorAreaSqm', '租用面积 m²'], ['wholeApartmentBedrooms', '整套公寓卧室'], ['wholeApartmentBathrooms', '整套公寓卫浴'],
  ['wholeApartmentFloorAreaSqm', '整套公寓面积 m²'], ['maxOccupants', '可住人数'], ['furnished', '配备家具']]

function WorkOrderHistory({ order }: { order: MaintenanceOrder }) {
  const [detail, setDetail] = useState<MaintenanceOrder>()
  const [error, setError] = useState<ApiError>()
  const [loading, setLoading] = useState(false)
  async function load() {
    setLoading(true); setError(undefined)
    try { setDetail(await staffPortalClient.getMaintenanceOrder(order.id)) } catch (e) { setError(e instanceof ApiError ? e : new ApiError(503, { code: 'request_failed', message: '工单时间线加载失败', retryable: true })) } finally { setLoading(false) }
  }
  return <article className="history-item" id={`work-${order.id}`}>
    <div className="history-heading"><div><small>{order.reference}</small><h3>{order.summary}</h3></div><span className={`pill ${order.status}`}>{STATUS[order.status]}</span></div>
    <p>{order.description}</p><p>报修住户：{order.tenant.displayName} · 负责人：{order.assignee?.displayName ?? '待分派'}</p>
    {error ? <ErrorState error={error} retry={() => void load()} /> : null}
    {detail ? <ol className="event-history">{detail.timeline?.map((event) => <li key={event.sequenceNo}><time>{new Date(event.occurredAt).toLocaleString('zh-CN')}</time> {event.message} <small>{STATUS[event.toStatus ?? '']}</small></li>)}</ol> : <button className="button secondary compact" disabled={loading} onClick={() => void load()}>{loading ? '加载中…' : '查看工单时间线'}</button>}
  </article>
}

export function PropertyDetailPage() {
  const { id = '' } = useParams()
  const location = useLocation()
  const backPath = location.state?.from === '/tenancies' ? '/tenancies' : '/properties'
  const loader = useCallback(() => staffPortalClient.getPropertyDetail(id), [id])
  const { data, error, loading, reload } = useAsyncData(loader)
  const [section, setSection] = useState('leases')
  const [contractLeaseId, setContractLeaseId] = useState<string | null>(null)
  if (loading) return <PageLoading />
  if (error || !data) return <ErrorState error={error ?? new ApiError(404, { code: 'resource_not_found', message: '未找到房源', retryable: false })} retry={() => void reload()} />
  const { property, leases, maintenance, inspections, attributes } = data
  const sources = attributes.fieldSources as Record<string, { origin: string }> | undefined
  return <>
    <Link className="back-link" to={backPath}>← 返回房源列表</Link>
    <PageHeader eyebrow={property.reference} title={`${property.building.name} · ${property.room}`} description={property.building.address} />
    {property.isSynthetic ? <p className="notice">模拟房源及使用记录 · 公开信息优先保留，补齐字段已标注来源。</p> : null}
    <div className="property-detail-overview"><PropertyVisual property={property} /><div className="property-field-grid">{FIELDS.map(([key, label]) => {
      const value = attributes[key] ?? ({ bedrooms: property.bedrooms, bathrooms: property.bathrooms, address: property.building.address, floorAreaSqm: property.floorAreaSqm, parkingSpaces: property.parkingSpaces } as Record<string, unknown>)[key]
      return <div key={key}><small>{label}</small><strong>{value == null ? '—' : typeof value === 'boolean' ? value ? '是' : '否' : String(value)}</strong>{sources?.[key] ? <em>{sources[key].origin === 'simulated' ? '模拟补齐' : '来源资料'}</em> : null}</div>
    })}</div></div>
    {data.partialErrors.length ? <p className="notice" role="status">部分关联记录暂不可用：{data.partialErrors.join('、')} <button onClick={() => void reload()}>重新加载</button></p> : null}
    <div className="tabs" role="tablist" aria-label="房源关联记录">
      {[['leases', `租住记录 (${leases.length})`], ['inspections', `检查记录 (${inspections.length})`], ['maintenance', `维修工单 (${maintenance.length})`]].map(([key, label]) => <button role="tab" aria-selected={section === key} className={section === key ? 'active' : ''} key={key} onClick={() => setSection(key)}>{label}</button>)}
    </div>
    <div className="history-list" role="tabpanel">
      {section === 'leases' ? leases.length ? leases.map((lease) => <article className="history-item" key={lease.id}><div className="history-heading"><div><small>{lease.reference}</small><h3>{lease.customer.displayName}</h3></div><span className={`pill ${lease.stage}`}>{STATUS[lease.status] ?? lease.status}</span></div><p>{lease.startsOn} 至 {lease.endsOn} · AUD ${lease.weeklyRent}/周</p><p>{lease.customer.email}</p>{lease.contract ? <details><summary>合同记录 · v{lease.contract.version}</summary><p>文档 {lease.contract.documentId}</p><code>{lease.contract.digest}</code><p><button className="button secondary compact" onClick={() => setContractLeaseId(lease.id)}>打开合同 PDF</button></p></details> : null}</article>) : <p>暂无租住记录。</p> : null}
      {section === 'inspections' ? inspections.length ? inspections.map((item) => <article className="history-item" key={item.id}><div className="history-heading"><h3>{KIND[item.kind] ?? item.kind} · {new Date(item.inspectedAt).toLocaleDateString('zh-CN')}</h3><span className="pill">{STATUS[item.status] ?? item.status}</span></div><p>{item.summary}</p><ul>{item.findings.map((finding, index) => <li key={index}><strong>{finding.area}</strong> · {finding.description} {finding.workOrderId ? <button className="text-button" onClick={() => setSection('maintenance')}>查看关联维修</button> : null}</li>)}</ul></article>) : <p>暂无可查看的检查记录。</p> : null}
      {section === 'maintenance' ? maintenance.length ? maintenance.map((order) => <WorkOrderHistory key={order.id} order={order} />) : <p>暂无维修工单。</p> : null}
    </div>
    {contractLeaseId ? <div className="modal-backdrop" role="presentation" onMouseDown={() => setContractLeaseId(null)}><AccessibleDialog className="modal" labelledBy="history-contract-title" onClose={() => setContractLeaseId(null)}><div className="modal-head"><h2 id="history-contract-title">租赁合同</h2><button aria-label="关闭历史合同" onClick={() => setContractLeaseId(null)}>×</button></div><LeasePdfDocument key={contractLeaseId} leaseId={contractLeaseId} client={staffPortalClient} /></AccessibleDialog></div> : null}
  </>
}
