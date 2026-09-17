import { useAuth } from '../auth/authContext'
import { PageHeader } from '../components/PageHeader'
import { ROLE_LABELS } from '../permissions'

export function ProfilePage() {
  const { session } = useAuth()
  if (!session) return null
  return <><PageHeader eyebrow="YOUR ACCOUNT" title="个人资料" description="员工身份与当前授权摘要。" /><div className="profile-page-card"><span className="avatar large">{session.staff.username.slice(0, 2).toUpperCase()}</span><div><h2>{session.staff.username}</h2><p>{ROLE_LABELS[session.staff.role]}</p></div><dl><div><dt>员工编号</dt><dd>{session.staff.staffCode}</dd></div><div><dt>邮箱</dt><dd>{session.staff.email}</dd></div><div><dt>当前权限</dt><dd>{session.permissions.length} 项</dd></div></dl><p className="muted">P0 个人资料为只读。资料与会话管理能力将在后续版本开放。</p></div></>
}
