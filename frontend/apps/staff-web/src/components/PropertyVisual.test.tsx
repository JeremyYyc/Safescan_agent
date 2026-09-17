import { fireEvent, render, screen } from '@testing-library/react'
import { PROPERTIES } from '../api/mockData'
import { PropertyVisual } from './PropertyVisual'

describe('PropertyVisual', () => {
  it('renders an accessible cover image when the BFF provides one', () => {
    render(<PropertyVisual property={{ ...PROPERTIES[0], coverImageUrl: '/staff/property-1.jpg' }} />)

    expect(screen.getByRole('img', { name: 'Harbour Heights 1204 房源照片' }))
      .toHaveAttribute('src', '/staff/property-1.jpg')
  })

  it('keeps the stable placeholder when no image exists or image loading fails', () => {
    const { container, rerender } = render(<PropertyVisual property={PROPERTIES[0]} />)
    const visual = container.querySelector('.property-visual')

    expect(screen.queryByRole('img')).not.toBeInTheDocument()
    expect(visual).toHaveClass('property-visual')

    rerender(<PropertyVisual property={{ ...PROPERTIES[0], coverImageUrl: '/staff/missing.jpg' }} />)
    fireEvent.error(screen.getByRole('img'))

    expect(screen.queryByRole('img')).not.toBeInTheDocument()
    expect(visual).not.toHaveClass('has-image')
  })
})
