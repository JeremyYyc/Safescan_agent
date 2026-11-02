import { fireEvent, render, screen } from '@testing-library/react'
import { AccessibleDialog } from '../../../../shared/AccessibleDialog'

it('focuses a dialog, closes on Escape, and restores its trigger focus', () => {
  const onClose = vi.fn()
  const trigger = document.createElement('button')
  document.body.append(trigger)
  trigger.focus()
  const { unmount } = render(<AccessibleDialog className="modal" labelledBy="title" onClose={onClose}><h2 id="title">合同</h2><button>关闭</button></AccessibleDialog>)
  expect(screen.getByRole('button', { name: '关闭' })).toHaveFocus()
  fireEvent.keyDown(document, { key: 'Escape' })
  expect(onClose).toHaveBeenCalledOnce()
  unmount()
  expect(trigger).toHaveFocus()
  trigger.remove()
})
