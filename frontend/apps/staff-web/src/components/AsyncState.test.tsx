import { fireEvent, render, screen } from '@testing-library/react'
import { ErrorState } from './AsyncState'
import { ApiError } from '../types'

describe('error display', () => {
  it('renders a safe retry state for a normal JavaScript error', () => {
    const retry = vi.fn()
    render(<ErrorState error={new TypeError('Malformed optional history page')} retry={retry} />)
    expect(screen.getByRole('alert')).toHaveTextContent('服务暂时不可用')
    fireEvent.click(screen.getByRole('button', { name: '重试' }))
    expect(retry).toHaveBeenCalledOnce()
  })

  it('keeps an API error status and request ID visible', () => {
    render(<ErrorState error={new ApiError(403, { code: 'forbidden', message: '没有权限', retryable: false, requestId: 'request-1' })} />)
    expect(screen.getByRole('alert')).toHaveTextContent('没有访问权限')
    expect(screen.getByRole('alert')).toHaveTextContent('请求编号：request-1')
  })
})
