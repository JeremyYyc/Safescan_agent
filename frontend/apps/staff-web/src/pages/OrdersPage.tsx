import { useCallback, useMemo, useState } from 'react'
import { staffPortalClient } from '../api/client'
import { useAuth } from '../auth/authContext'
import { EmptyState, ErrorState, PageLoading } from '../components/AsyncState'
import { PageHeader } from '../components/PageHeader'
import { useAsyncData } from '../hooks/useAsyncData'

const STAGES = { application: '申请中', pending_signature: '待签约', executed: '已执行', ended: '历史合同' }

export function OrdersPage() {
  const loader = useCallback(() => staffPortalClient.listOrders(), [])
  const { data, error, loading, reload } = useAsyncData(loader)
  const { session } = useAuth()
  const [stage, setStage] = useState('all')
  const [selectedOrderId, setSelectedOrderId] = useState<string | null>(null)
  const orders = useMemo(() => (data ?? []).filter((item) => stage === 'all' || item.stage === stage), [data, stage])
  const selectedOrder = data?.find((item) => item.id === selectedOrderId)
  const isAdmin = session?.staff.role === 'manager_admin'

  return <>
    <PageHeader eyebrow="LEASING PIPELINE" title="我的订单" description={isAdmin ? '查看全部租约、房源与双方详细信息。' : '集中处理分配给你的申请、待签合同与历史成功订单。'} />
    <div className="metric-row"><div><small>全部订单</small><strong>{data?.length ?? '—'}</strong></div><div><small>待签约</small><strong>{data?.filter((item) => item.stage === 'pending_signature').length ?? '—'}</strong></div><div><small>成功合同</small><strong>{data?.filter((item) => item.stage === 'executed' || item.stage === 'ended').length ?? '—'}</strong></div></div>
    <div className="tabs" role="tablist"><button className={stage === 'all' ? 'active' : ''} onClick={() => setStage('all')}>全部</button>{Object.entries(STAGES).map(([value, label]) => <button key={value} className={stage === value ? 'active' : ''} onClick={() => setStage(value)}>{label}</button>)}</div>
    {loading ? <PageLoading /> : error ? <ErrorState error={error} retry={() => void reload()} /> : orders.length === 0 ? <EmptyState title="当前没有订单" description="该阶段暂无需要处理的记录。" /> : <div className="table-card"><table><thead><tr><th>订单 / 状态</th><th>房源</th><th>租客</th>{isAdmin ? <th>负责员工</th> : null}<th>租期 / 租金</th><th>合同</th></tr></thead><tbody>{orders.map((order) => <tr key={order.id}><td><strong>{order.reference}</strong><span className={`pill ${order.stage}`}>{STAGES[order.stage]}</span><small>{order.status}</small></td><td><strong>{order.property.building.name} · {order.property.room}</strong><small>{order.property.reference}</small></td><td><strong>{order.customer.displayName}</strong><small>{order.customer.email}</small><small>{order.customer.phone}</small></td>{isAdmin ? <td><strong>{order.consultant.displayName}</strong><small>{order.consultant.staffCode}</small></td> : null}<td><strong>{order.startsOn} → {order.endsOn}</strong><small>AUD ${order.weeklyRent}/周</small></td><td>{order.contract ? <button className="document-link" onClick={() => setSelectedOrderId(order.id)}><span>PDF</span><strong>{order.contract.documentId}</strong><small>v{order.contract.version} · {order.contract.digest}</small></button> : <small>尚未生成</small>}</td></tr>)}</tbody></table></div>}
    {selectedOrder?.contract ? <div className="modal-backdrop" role="presentation" onMouseDown={() => setSelectedOrderId(null)}><section className="modal" role="dialog" aria-modal="true" aria-labelledby="contract-title" onMouseDown={(event) => event.stopPropagation()}><div className="modal-head"><div><p className="eyebrow">LEASE CONTRACT</p><h2 id="contract-title">合同 {selectedOrder.contract.documentId}</h2></div><button aria-label="关闭合同详情" onClick={() => setSelectedOrderId(null)}>×</button></div><div className="contract-summary"><div><small>租约单</small><strong>{selectedOrder.reference}</strong></div><div><small>房源</small><strong>{selectedOrder.property.building.name} · {selectedOrder.property.room}</strong></div><div><small>租客</small><strong>{selectedOrder.customer.displayName}</strong></div><div><small>租期</small><strong>{selectedOrder.startsOn} 至 {selectedOrder.endsOn}</strong></div><div><small>租客签署</small><strong>{selectedOrder.contract.tenantSignedAt ? new Date(selectedOrder.contract.tenantSignedAt).toLocaleString('zh-CN') : '等待签署'}</strong></div><div><small>公司签署</small><strong>{selectedOrder.contract.companySignedAt ? new Date(selectedOrder.contract.companySignedAt).toLocaleString('zh-CN') : '等待签署'}</strong></div></div><div className="digest"><small>不可变文档摘要 · v{selectedOrder.contract.version}</small><code>{selectedOrder.contract.digest}</code></div><p className="modal-note">P0 展示带审计记录的产品确认合同，不代表第三方合规电子签章。</p></section></div> : null}
  </>
}
