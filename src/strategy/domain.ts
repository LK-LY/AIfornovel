import type { Evidence, Report, Work } from '../types'

export const groups = ['题材语境', '叙事驱动力', '核心关系', '主角目标', '核心冲突', '情绪承诺', '包装钩子', '承诺兑现']
export const scopeNames = { full_text: '全文已确认', opening_only: '仅开篇', metadata_only: '标题与导语' }
export const productScopeNote = '作品篇幅不划分产品模式；所有作品沿用同一套文本范围、证据与审核原则。交互导入受资源上限约束，较大文件使用独立分块分析。'
export const interactiveImportMaxBytes = 512 * 1024
export const interactiveImportLimitLabel = '512 KiB'
export const largeFileAnalysisNote = '请使用 npm run analyze:novel 的文件分析流程；结果单独保存在 private-reports，不会自动进入样本库。'
export const valueNames: Record<string, string> = { unknown: '不足以判断', not_applicable: '不适用', fulfilled: '已对应兑现', partial: '部分对应', contradicted: '出现矛盾' }
export const optionsByGroup: Record<string, string[]> = {
  '题材语境': ['现代都市', '古代', '幻想', '其他', 'unknown'],
  '叙事驱动力': ['成长重建', '脱离关系', '事业', '复仇', '亲情', '悬疑', '爱情', 'unknown'],
  '核心关系': ['前夫妻', '恋人', '母女', '姐妹', '同事', 'not_applicable', 'unknown'],
  '主角目标': ['重新掌握生活节奏', '脱离关系', '建立事业', '修复亲情', '查明真相', 'unknown'],
  '核心冲突': ['关系中的长期忽视', '家庭阻力', '职场阻力', '外部威胁', '内在选择', 'unknown'],
  '情绪承诺': ['释然 / 自我回收', '复仇释放', '被认可', '反转', '甜', 'unknown'],
  '包装钩子': ['结果前置', '冲突前置', '身份反差', '关系反差', '结果悬念', 'unknown'],
  '承诺兑现': ['fulfilled', 'partial', 'contradicted', 'unknown', 'not_applicable'],
}
export function checkEvidence(work: Work, evidence: Evidence) {
  if (evidence.workId !== work.id || evidence.versionId !== work.versionId) return false
  if (evidence.contentHash && evidence.contentHash !== work.contentHash) return false
  if (!Number.isInteger(evidence.startChar) || !Number.isInteger(evidence.endChar)) return false
  let source: string
  if (evidence.field === '标题' || evidence.field === '导语') {
    if (evidence.paragraphId !== (evidence.field === '标题' ? 'title' : 'intro')) return false
    source = evidence.field === '标题' ? work.title : work.intro
  } else {
    if (!['开篇', '正文', '结尾'].includes(evidence.field)) return false
    if (work.scope === 'metadata_only') return false
    const paragraph = work.paragraphs.find(p => p.id === evidence.paragraphId)
    if (!paragraph || !(paragraph.label.startsWith(evidence.field) || evidence.field === '结尾' && paragraph.label.startsWith('开篇/结尾'))) return false
    if (evidence.field === '结尾' && (work.scope !== 'full_text' || !work.endingConfirmed)) return false
    if (evidence.field === '正文' && work.scope !== 'full_text') return false
    source = paragraph.text
  }
  const points = Array.from(source)
  return evidence.startChar >= 0 && evidence.endChar <= points.length && evidence.startChar < evidence.endChar && points.slice(evidence.startChar, evidence.endChar).join('') === evidence.quote
}
export function formatPercent(value: number | null | undefined) { return value == null ? '—' : `${(value * 100).toFixed(2)}%` }
export function downloadText(text: string, name: string, type = 'text/markdown;charset=utf-8') {
  const url = URL.createObjectURL(new Blob([text], { type }))
  const a = document.createElement('a'); a.href = url; a.download = name; a.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
export function reportMarkdown(report: Report) {
  return [`# HerLens 研究备忘录`, `\n${report.question}`, `\n报告 ${report.id} · 数据修订 ${report.revision} · 样本 ${report.sampleCount} · ${report.createdAt}`,
    '\n本报告使用原创虚构演示夹具，不代表真实作品表现。', ...report.findings.flatMap(f => [`\n## ${f.title}`, f.observation, `证据：${[...f.evidenceIds, ...f.queryIds].join('、')}`, `范围：${f.scope}`, `局限：${f.limitation}`, `验证：${f.nextStep}`, `判断标准：${f.criterion}`]), '\n## 工具执行记录', ...report.trace.map(s => `${s.index}. ${s.tool} / ${s.status} / ${s.durationMs} ms`)].join('\n\n')
}
