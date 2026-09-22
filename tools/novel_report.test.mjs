import assert from 'node:assert/strict'
import test from 'node:test'
import { fixClassicScrollbarWidth } from './deliver_novel_report.mjs'

test('correct only the known classic-scrollbar top bar rule', () => {
  const css = '.chart{width:100vw}.analytics-top-bar { width: 100vw; margin-left: calc(50% - 50vw); margin-right: calc(50% - 50vw); background: var(--ds-bg); }'
  const fixed = fixClassicScrollbarWidth(css)
  assert.equal(fixed.corrections, 1)
  assert.ok(fixed.html.includes('.chart{width:100vw}'))
  assert.ok(fixed.html.includes('background: var(--ds-bg);'))
  assert.ok(fixed.html.includes('width: calc(100% + 2 * var(--ds-gutter));'))
})

test('leave a corrected or unknown renderer unchanged', () => {
  const css = '.analytics-top-bar { width: 100%; }'
  assert.deepEqual(fixClassicScrollbarWidth(css), { html: css, corrections: 0 })
})

test('ambiguous upstream runtime fails closed', () => {
  const rule = '.analytics-top-bar { width: 100vw; margin-left: calc(50% - 50vw); }'
  assert.throws(() => fixClassicScrollbarWidth(rule + rule), /Ambiguous/)
})
