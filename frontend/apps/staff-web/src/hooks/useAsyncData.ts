import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError } from '../types'

export function useAsyncData<T>(loader: () => Promise<T>) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [loading, setLoading] = useState(true)
  const requestSequence = useRef(0)

  const reload = useCallback(async () => {
    const sequence = ++requestSequence.current
    setLoading(true)
    setError(null)
    try {
      const result = await loader()
      if (sequence === requestSequence.current) setData(result)
    } catch (reason) {
      if (sequence === requestSequence.current) setError(reason instanceof ApiError ? reason : new ApiError(500, {
        code: 'unexpected_error', message: '数据加载失败，请稍后重试。', retryable: true,
      }))
    } finally {
      if (sequence === requestSequence.current) setLoading(false)
    }
  }, [loader])

  useEffect(() => {
    void reload()
    return () => { requestSequence.current += 1 }
  }, [reload])
  return { data, setData, error, loading, reload }
}
