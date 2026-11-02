// Keep the React default import: shared files are outside the app JSX tsconfigs.
import React, { useEffect, useRef, type PropsWithChildren } from 'react'

export function AccessibleDialog({ children, className, labelledBy, onClose }: PropsWithChildren<{ className: string; labelledBy: string; onClose: () => void }>) {
  const dialog = useRef<HTMLElement>(null)
  useEffect(() => {
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null
    const element = dialog.current
    const focusable = () => Array.from(element?.querySelectorAll<HTMLElement>('button:not(:disabled), a[href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), iframe, [tabindex="0"]') ?? [])
    ;(focusable()[0] ?? element)?.focus()
    const keydown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { event.preventDefault(); onClose(); return }
      if (event.key !== 'Tab') return
      const controls = focusable()
      const first = controls[0]
      const last = controls.at(-1)
      if (!first) { event.preventDefault(); element?.focus(); return }
      if (event.shiftKey && (document.activeElement === first || document.activeElement === element)) { event.preventDefault(); last?.focus() }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
    }
    document.addEventListener('keydown', keydown)
    return () => { document.removeEventListener('keydown', keydown); previousFocus?.focus() }
  }, [onClose])
  return <section ref={dialog} className={className} role="dialog" aria-modal="true" aria-labelledby={labelledBy} tabIndex={-1} onMouseDown={(event) => event.stopPropagation()}>{children}</section>
}
