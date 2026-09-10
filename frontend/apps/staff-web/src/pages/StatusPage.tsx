import { Link } from 'react-router-dom'

export function ForbiddenPage() {
  return <div className="status-page"><strong>403</strong><h1>当前账号无权访问此页面</h1><p>菜单由当前权限自动生成；如职责已变更，请联系 Manager Admin。</p><Link className="button primary" to="/properties">返回可访问页面</Link></div>
}

export function NotFoundPage() {
  return <div className="status-page"><strong>404</strong><h1>页面不存在</h1><p>链接可能已经变更，或该功能尚未在 P0 开放。</p><Link className="button primary" to="/properties">返回房源信息</Link></div>
}
