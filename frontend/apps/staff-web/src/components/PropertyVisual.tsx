import { useEffect, useState } from 'react'
import { staffPortalClient } from '../api/client'
import type { PropertySummary } from '../types'

const OCCUPANCY_LABELS = { vacant: '空置', reserved: '待入住', occupied: '在租' } as const

export function PropertyVisual({ property }: { property: PropertySummary }) {
  const [failedUrl, setFailedUrl] = useState<string | null>(null)
  const coverImageUrl = property.coverImageUrl?.trim()
  const [resolved, setResolved] = useState<{ source: string; url: string }>()
  const protectedImage = coverImageUrl?.startsWith('/api/v1/staff/')
  useEffect(() => {
    if (!protectedImage || !coverImageUrl) return
    let active = true
    let objectUrl: string | undefined
    staffPortalClient.getPropertyImage(coverImageUrl).then((blob) => {
      if (!active) return
      objectUrl = URL.createObjectURL(blob)
      setResolved({ source: coverImageUrl, url: objectUrl })
    }).catch(() => { if (active) setFailedUrl(coverImageUrl) })
    return () => { active = false; if (objectUrl) URL.revokeObjectURL(objectUrl) }
  }, [coverImageUrl, protectedImage])
  const imageUrl = protectedImage ? resolved?.source === coverImageUrl ? resolved?.url : undefined : coverImageUrl
  const showImage = Boolean(imageUrl && coverImageUrl !== failedUrl)
  const initials = property.building.name.split(' ').map((word) => word[0]).join('')

  return <div className={`property-visual${showImage ? ' has-image' : ''}`}>
    <span className="property-placeholder" aria-hidden="true">{initials}</span>
    {showImage ? <img
      src={imageUrl}
      alt={`${property.building.name} ${property.room} 房源照片`}
      onError={() => setFailedUrl(coverImageUrl!)}
    /> : null}
    <span className={`status ${property.occupancy}`}>{OCCUPANCY_LABELS[property.occupancy]}</span>
  </div>
}
