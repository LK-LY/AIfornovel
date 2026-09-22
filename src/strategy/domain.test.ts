import assert from 'node:assert/strict'
import test from 'node:test'
import type { Evidence, Work } from '../types'

// Node's native TypeScript loader needs .ts; a variable import keeps the app's
// noEmit TypeScript build compatible without changing its module settings.
const modulePath = './domain.ts'
const { checkEvidence, formatPercent, interactiveImportMaxBytes, largeFileAnalysisNote, productScopeNote, scopeNames } = await import(modulePath)

function example(): { work: Work; evidence: Evidence } {
  const work: Work = { id: 'unicode', versionId: 'v1', contentHash: 'a'.repeat(64), title: '她🌸重新开始', intro: '她终于回家。', author: '', sourceType: 'test', rightsStatus: 'synthetic', isSynthetic: true, scope: 'full_text', endingConfirmed: true, localConsent: true, modelConsent: false, revision: 1, updatedAt: '', reviewStatus: '待审核', annotations: [], evidence: [], observations: [], paragraphs: [{ id: 'p1', label: '开篇 · 01', text: '🌱她推开门。' }, { id: 'p2', label: '结尾 · 02', text: '她回到了自己的生活。' }] }
  return { work, evidence: { id: 'ev-unicode', workId: work.id, versionId: work.versionId, contentHash: work.contentHash, field: '标题', paragraphId: 'title', quote: '🌸', startChar: 1, endChar: 2, reviewStatus: '待审核' } }
}

test('emoji offsets use Unicode code points, not UTF-16 code units', () => {
  const { work, evidence } = example()
  assert.equal(checkEvidence(work, evidence), true)
  assert.equal(checkEvidence(work, { ...evidence, endChar: 3 }), false)
  assert.equal(checkEvidence(work, { ...evidence, startChar: 2, endChar: 3 }), false)
})

test('joined emoji remains a sequence of code points, not one grapheme', () => {
  const { work, evidence } = example()
  work.title = '家👩‍👩‍👧‍👦在这里'
  assert.equal(checkEvidence(work, { ...evidence, quote: '👩‍👩‍👧‍👦', startChar: 1, endChar: 8 }), true)
  assert.equal(checkEvidence(work, { ...evidence, quote: '👩‍👩‍👧‍👦', startChar: 1, endChar: 2 }), false)
})

test('different work, version, or content fingerprint cannot validate', () => {
  const { work, evidence } = example()
  for (const patch of [{ workId: 'other' }, { versionId: 'v0' }, { contentHash: 'b'.repeat(64) }]) assert.equal(checkEvidence(work, { ...evidence, ...patch }), false)
})

test('invalid, fractional, empty, and out-of-range positions are refused', () => {
  const { work, evidence } = example()
  for (const [startChar, endChar] of [[-1, 2], [1, 99], [2, 2], [2, 1], [.5, 2], [1, 2.5], [NaN, 2], [1, Infinity]]) assert.equal(checkEvidence(work, { ...evidence, startChar, endChar }), false)
})

test('field names cannot redirect evidence to a different source', () => {
  const { work, evidence } = example()
  assert.equal(checkEvidence(work, { ...evidence, paragraphId: 'intro' }), false)
  assert.equal(checkEvidence(work, { ...evidence, field: '导语' }), false)
  assert.equal(checkEvidence(work, { ...evidence, field: '开篇', paragraphId: 'missing' }), false)
})

test('ending evidence requires full text, confirmation, and an ending paragraph', () => {
  const { work, evidence } = example()
  const ending: Evidence = { ...evidence, field: '结尾', paragraphId: 'p2', quote: '她', startChar: 0, endChar: 1 }
  assert.equal(checkEvidence(work, ending), true)
  assert.equal(checkEvidence({ ...work, endingConfirmed: false }, ending), false)
  assert.equal(checkEvidence({ ...work, scope: 'opening_only' }, ending), false)
  assert.equal(checkEvidence({ ...work, scope: 'metadata_only' }, ending), false)
  assert.equal(checkEvidence(work, { ...ending, paragraphId: 'p1', quote: '🌱' }), false)
})

test('metadata-only scope cannot validate body evidence', () => {
  const { work, evidence } = example()
  const opening: Evidence = { ...evidence, field: '开篇', paragraphId: 'p1', quote: '🌱', startChar: 0, endChar: 1 }
  assert.equal(checkEvidence(work, opening), true)
  assert.equal(checkEvidence({ ...work, scope: 'metadata_only' }, opening), false)
})

test('middle body is distinct from opening evidence and requires full text', () => {
  const { work, evidence } = example()
  work.paragraphs.push({ id: 'middle', label: '正文 · 02', text: '后来，她修好了那扇门。' })
  const middle: Evidence = { ...evidence, field: '正文', paragraphId: 'middle', quote: '后来', startChar: 0, endChar: 2 }
  assert.equal(checkEvidence(work, middle), true)
  assert.equal(checkEvidence(work, { ...middle, field: '开篇' }), false)
  assert.equal(checkEvidence({ ...work, scope: 'opening_only' }, middle), false)
})

test('a confirmed one-paragraph work can have both opening and ending evidence', () => {
  const { work, evidence } = example()
  work.paragraphs = [{ id: 'only', label: '开篇/结尾 · 01', text: '她重新开始。' }]
  const pointer: Evidence = { ...evidence, field: '结尾', paragraphId: 'only', quote: '她', startChar: 0, endChar: 1 }
  assert.equal(checkEvidence(work, pointer), true)
  assert.equal(checkEvidence(work, { ...pointer, field: '开篇' }), true)
  assert.equal(checkEvidence({ ...work, endingConfirmed: false }, pointer), false)
})

test('missing rate stays missing and zero is rendered as an actual zero', () => {
  assert.equal(formatPercent(null), '—')
  assert.equal(formatPercent(undefined), '—')
  assert.equal(formatPercent(0), '0.00%')
  assert.equal(formatPercent(7680 / 40600), '18.92%')
})

test('one length-neutral product keeps explicit text-integrity scopes', () => {
  assert.match(productScopeNote, /篇幅不划分产品模式/)
  assert.match(productScopeNote, /交互导入受资源上限约束/)
  assert.match(productScopeNote, /独立分块分析/)
  assert.match(largeFileAnalysisNote, /npm run analyze:novel/)
  assert.match(largeFileAnalysisNote, /private-reports/)
  assert.match(largeFileAnalysisNote, /不会自动进入样本库/)
  assert.deepEqual(Object.keys(scopeNames).sort(), ['full_text', 'metadata_only', 'opening_only'])
  assert.equal(interactiveImportMaxBytes, 512 * 1024)
})
