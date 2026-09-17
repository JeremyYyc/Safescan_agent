import { Link } from 'react-router-dom'
import { useAuth } from '../auth/authContext'
import { defaultStaffPath } from '../navigation'

function HomeLink({ children }: { children: string }) {
  const { session } = useAuth()
  return <Link className="button primary" to={session ? defaultStaffPath(session.staff.role) : '/login'}>{children}</Link>
}

export function ForbiddenPage() {
  return <div className="status-page"><strong>403</strong><h1>当前账号无权访问此页面</h1><p>菜单由当前权限自动生成；如职责已变更，请联系 Manager Admin。</p><HomeLink>返回可访问页面</HomeLink></div>
}

export function NotFoundPage() {
  return <div className="status-page"><strong>404</strong><h1>页面不存在</h1><p>链接可能已经变更，或该功能尚未在 P0 开放。</p><HomeLink>返回工作台</HomeLink></div>
}
