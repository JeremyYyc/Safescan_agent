// @vitest-environment node
import React from 'react'
import pdfSource from '../../../../shared/LeasePdfDocument.tsx?raw'
import dialogSource from '../../../../shared/AccessibleDialog.tsx?raw'
import { transformSync } from 'esbuild'
import { renderToStaticMarkup } from 'react-dom/server'

// Shared files sit outside both app tsconfigs. Reproduce the classic JSX transform
// used for those files by production builds, instead of Vitest's React plugin.
function productionComponent(file: string, exportName: string): React.ComponentType<Record<string, unknown>> {
  const sources: Record<string, string> = { 'LeasePdfDocument.tsx': pdfSource, 'AccessibleDialog.tsx': dialogSource }
  const source = sources[file]
  const { code } = transformSync(source, { loader: 'tsx', jsx: 'transform', format: 'cjs', platform: 'node', target: 'es2022' })
  const compiled = { exports: {} as Record<string, React.ComponentType<Record<string, unknown>>> }
  const execute = new Function('require', 'module', 'exports', code)
  execute((name: string) => {
    if (name === 'react') return React
    throw new Error(`Unexpected production dependency: ${name}`)
  }, compiled, compiled.exports)
  return compiled.exports[exportName]
}

describe('shared components in the production JSX runtime', () => {
  it('renders the PDF loader without depending on a global React variable', () => {
    const Pdf = productionComponent('LeasePdfDocument.tsx', 'LeasePdfDocument')
    const html = renderToStaticMarkup(<Pdf leaseId="lease-1" client={{ getLeasePdf: () => new Promise(() => {}) }} />)
    expect(html).toContain('正在加载合同 PDF')
  })

  it('renders the production dialog without a global React variable', () => {
    const Dialog = productionComponent('AccessibleDialog.tsx', 'AccessibleDialog')
    const html = renderToStaticMarkup(<Dialog className="modal" labelledBy="production-dialog" onClose={() => {}}><h2 id="production-dialog">生产合同预览</h2><button>关闭预览</button></Dialog>)
    expect(html).toContain('role="dialog"')
    expect(html).toContain('生产合同预览')
  })
})
