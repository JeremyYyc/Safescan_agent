import { useAuth } from '../auth/authContext'
import { PageHeader } from '../components/PageHeader'
import { ROLE_LABELS } from '../permissions'
import { assignedRegions } from '../regions'

export function ProfilePage() {
  const { session } = useAuth()
  if (!session) return null
  const buildings = session.staff.assignedBuildings ?? []
  const regions = assignedRegions(buildings)
  const scope = session.staff.assignmentScope
  const regionSummary = scope === 'unavailable'
    ? '地区信息暂时无法加载，请稍后重新登录查看'
    : scope === 'all' ? '全部地区'
      : regions.length ? regions.join('、')
        : session.staff.role === 'maintainer' ? '按分配的维修工单授权' : '未分配固定地区'

  return <>
    <PageHeader eyebrow="YOUR ACCOUNT" title="个人资料" description="员工身份与当前授权摘要。" />
    <div className="profile-page-card">
      <span className="avatar large">{session.staff.username.slice(0, 2).toUpperCase()}</span>
      <div><h2>{session.staff.username}</h2><p>{ROLE_LABELS[session.staff.role]}</p></div>
      <dl>
        <div><dt>员工编号</dt><dd>{session.staff.staffCode}</dd></div>
        <div><dt>邮箱</dt><dd>{session.staff.email}</dd></div>
        <div><dt>当前权限</dt><dd>{session.permissions.length} 项</dd></div>
        <div className="profile-regions"><dt>掌管地区</dt><dd>{regionSummary}</dd></div>
      </dl>
      {buildings.length ? <details className="profile-buildings"><summary>查看授权楼宇（{buildings.length} 栋）</summary>{buildings.map((building) => <p key={building.id}><strong>{building.name}</strong><br />{building.address}</p>)}</details> : null}
      <p className="muted">P0 个人资料为只读。资料与会话管理能力将在后续版本开放。</p>
    </div>
  </>
}
