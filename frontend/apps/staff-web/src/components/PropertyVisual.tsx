import { useState } from 'react'
import type { PropertySummary } from '../types'

const OCCUPANCY_LABELS = { vacant: '空置', reserved: '待入住', occupied: '在租' } as const

export function PropertyVisual({ property }: { property: PropertySummary }) {
  const [failedUrl, setFailedUrl] = useState<string | null>(null)
  const coverImageUrl = property.coverImageUrl?.trim()
  const showImage = Boolean(coverImageUrl && coverImageUrl !== failedUrl)
  const initials = property.building.name.split(' ').map((word) => word[0]).join('')

  return <div className={`property-visual${showImage ? ' has-image' : ''}`}>
    <span className="property-placeholder" aria-hidden="true">{initials}</span>
    {showImage ? <img
      src={coverImageUrl}
      alt={`${property.building.name} ${property.room} 房源照片`}
      onError={() => setFailedUrl(coverImageUrl!)}
    /> : null}
    <span className={`status ${property.occupancy}`}>{OCCUPANCY_LABELS[property.occupancy]}</span>
  </div>
}
