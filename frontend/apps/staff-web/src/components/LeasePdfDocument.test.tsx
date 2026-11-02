import { render, screen, waitFor } from '@testing-library/react'
import { LeasePdfDocument } from '../../../../shared/LeasePdfDocument'

describe('LeasePdfDocument', () => {
  it('shows the authenticated PDF and releases the private Blob URL on close', async () => {
    const create = vi.fn().mockReturnValue('blob:private-document')
    const revoke = vi.fn()
    vi.stubGlobal('URL', Object.assign(URL, { createObjectURL: create, revokeObjectURL: revoke }))
    const client = { getLeasePdf: vi.fn().mockResolvedValue(new Blob(['%PDF'], { type: 'application/pdf' })) }
    const { unmount } = render(<LeasePdfDocument leaseId="lease-1" client={client} />)
    await waitFor(() => expect(screen.getByTitle('租赁合同 PDF')).toHaveAttribute('src', 'blob:private-document'))
    expect(client.getLeasePdf).toHaveBeenCalledWith('lease-1')
    expect(screen.getByRole('link')).toHaveAttribute('rel', 'noopener noreferrer')
    unmount()
    expect(revoke).toHaveBeenCalledWith('blob:private-document')
    vi.unstubAllGlobals()
  })
})
