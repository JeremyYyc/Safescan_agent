// Keep the React default import: shared files are outside the app JSX tsconfigs.
import React, { useEffect, useState } from 'react'

interface PdfClient { getLeasePdf(leaseId: string): Promise<Blob> }

export function LeasePdfDocument({ leaseId, client }: { leaseId: string; client: PdfClient }) {
  const [url, setUrl] = useState<string>()
  const [error, setError] = useState<string>()
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    let active = true
    let objectUrl: string | undefined
    client.getLeasePdf(leaseId).then((blob) => {
      if (!active) return
      objectUrl = URL.createObjectURL(blob)
      setUrl(objectUrl)
      setError(undefined)
    }).catch((reason: unknown) => {
      if (active) setError(reason instanceof Error ? reason.message : '合同 PDF 加载失败')
    })
    return () => {
      active = false
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [leaseId, client, attempt])

  if (error) return <div role="alert"><p>{error}</p><button className="button secondary" onClick={() => { setError(undefined); setAttempt((value) => value + 1) }}>重试加载合同</button></div>
  if (!url) return <p role="status">正在加载合同 PDF…</p>
  return <div>
    <p><a href={url} target="_blank" rel="noopener noreferrer">在新窗口打开合同 PDF</a></p>
    <iframe title="租赁合同 PDF" src={url} style={{ width: '100%', height: '65vh', border: '1px solid #dce4e8', borderRadius: 8 }} />
  </div>
}
