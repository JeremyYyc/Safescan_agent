import { ApiError } from '../types'

const ERROR_TITLES: Record<number, string> = {
  403: '没有访问权限',
  404: '未找到相关内容',
  409: '数据已发生变化',
  422: '提交内容需要调整',
  500: '服务暂时不可用',
  503: '依赖服务暂时不可用',
  504: '服务响应超时',
}

export function PageLoading() {
  return <div className="skeleton-grid" aria-label="正在加载"><div /><div /><div /></div>
}

export function EmptyState({ title, description }: { title: string; description: string }) {
  return <div className="empty-state"><span className="empty-mark">✓</span><h3>{title}</h3><p>{description}</p></div>
}

export function ErrorState({ error, retry }: { error: unknown; retry?: () => void }) {
  const apiError = error instanceof ApiError ? error : null
  const status = apiError?.status ?? 500
  const title = status === 0 ? '网络连接失败' : (ERROR_TITLES[status] ?? '请求未能完成')
  return <div className="error-state" role="alert"><span>!</span><div><h3>{title}</h3><p>{apiError?.message ?? '数据加载失败，请稍后重试。'}</p>{apiError?.error.requestId ? <small>请求编号：{apiError.error.requestId}</small> : null}</div>{retry ? <button className="button secondary" onClick={retry}>重试</button> : null}</div>
}
