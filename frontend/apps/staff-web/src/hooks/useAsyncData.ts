import { useCallback, useEffect, useState } from 'react'
import type { ApiError } from '../types'

export function useAsyncData<T>(loader: () => Promise<T>) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [loading, setLoading] = useState(true)

  const reload = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setData(await loader())
    } catch (reason) {
      setError(reason as ApiError)
    } finally {
      setLoading(false)
    }
  }, [loader])

  useEffect(() => { void reload() }, [reload])
  return { data, setData, error, loading, reload }
}
