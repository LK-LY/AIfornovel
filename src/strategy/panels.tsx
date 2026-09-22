import { useEffect, useId, useRef, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { AlertCircle, Check, FileText, Link2, LoaderCircle, ShieldCheck, Upload, X } from 'lucide-react'
import type { Annotation, Evidence, ReviewStatus, Scope, TraceStep, Work } from '../types'
import { checkEvidence, interactiveImportLimitLabel, interactiveImportMaxBytes, largeFileAnalysisNote, optionsByGroup, scopeNames, valueNames } from './domain'

type ImportResult = { row: number; status: string; workId?: string; message: string }
type ReviewChanges = { value: string; rationale: string; evidenceIds: string[]; reviewStatus: ReviewStatus }

export function Modal({ title, eyebrow, onClose, children, className = '' }: { title: string; eyebrow?: string; onClose: () => void; children: ReactNode; className?: string }) {
  const titleId = useId()
  const dialog = useRef<HTMLDivElement>(null)
  const close = useRef(onClose)
  close.current = onClose
  useEffect(() => {
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    const focusable = () => Array.from(dialog.current?.querySelectorAll<HTMLElement>('button:not(:disabled), a[href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), summary, [tabindex]:not([tabindex="-1"])') ?? []).filter(el => el.getClientRects().length > 0)
    const frame = requestAnimationFrame(() => (focusable()[0] ?? dialog.current)?.focus())
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { event.preventDefault(); close.current(); return }
      if (event.key !== 'Tab') return
      const items = focusable()
      const first = items[0], last = items[items.length - 1]
      if (!first) { event.preventDefault(); dialog.current?.focus(); return }
      if (!dialog.current?.contains(document.activeElement)) { event.preventDefault(); first.focus() }
      else if (event.shiftKey && (document.activeElement === first || document.activeElement === dialog.current)) { event.preventDefault(); last.focus() }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
    }
    const onFocus = (event: FocusEvent) => {
      if (event.target instanceof Node && !dialog.current?.contains(event.target)) (focusable()[0] ?? dialog.current)?.focus()
    }
    document.addEventListener('keydown', onKey, true)
    document.addEventListener('focusin', onFocus)
    return () => {
      cancelAnimationFrame(frame)
      document.removeEventListener('keydown', onKey, true)
      document.removeEventListener('focusin', onFocus)
      document.body.style.overflow = previousOverflow
      if (previous?.isConnected) previous.focus()
    }
  }, [])
  return createPortal(<div className="modal-backdrop" onMouseDown={event => { if (event.target === event.currentTarget) close.current() }}><div ref={dialog} className={`modal ${className}`} role="dialog" aria-modal="true" aria-labelledby={titleId} tabIndex={-1}><div className="modal-header"><div>{eyebrow && <div className="eyebrow">{eyebrow}</div>}<h2 id={titleId}>{title}</h2></div><button className="icon-btn" aria-label="关闭对话框" onClick={() => close.current()}><X size={20} /></button></div><div className="modal-body">{children}</div></div></div>, document.body)
}

function evidenceIsCurrent(work: Work, evidence: Evidence) {
  const correctField = evidence.field === '标题' ? evidence.paragraphId === 'title' : evidence.field === '导语' ? evidence.paragraphId === 'intro' : !['title', 'intro'].includes(evidence.paragraphId)
  return checkEvidence(work, evidence) && correctField && evidence.workId === work.id && (!evidence.contentHash || !work.contentHash || evidence.contentHash === work.contentHash) && (evidence.field !== '结尾' || work.scope === 'full_text' && work.endingConfirmed)
}

export function EvidencePanel({ work, evidence, onClose }: { work: Work; evidence: Evidence; onClose: () => void }) {
  const valid = evidenceIsCurrent(work, evidence)
  const source = evidence.paragraphId === 'title' ? work.title : evidence.paragraphId === 'intro' ? work.intro : work.paragraphs.find(p => p.id === evidence.paragraphId)?.text ?? ''
  const points = Array.from(source)
  const from = Math.max(0, evidence.startChar - 100), to = Math.min(points.length, evidence.endChar + 100)
  const annotations = work.annotations.filter(a => a.evidenceIds.includes(evidence.id))
  return <Modal title="沿着判断，回到原文" eyebrow="EVIDENCE INSPECTOR" onClose={onClose} className="evidence-modal"><div className={`evidence-check ${valid ? 'valid' : 'invalid'}`} role="status">{valid ? <ShieldCheck size={19} /> : <AlertCircle size={19} />}<div><b>{valid ? '引用与当前版本精确匹配' : '引用未通过当前版本校验'}</b><p>{valid ? '位置、原文与文本范围一致；语义解释仍需人工复查。' : '请检查文本版本、内容指纹、段落位置与结尾范围，暂不将这条引用作为已确认依据。'}</p></div></div><div className="evidence-work"><span className="pill neutral">{evidence.field}</span><h3>{work.title}</h3><span className="mono">{evidence.id}</span></div><blockquote className="evidence-quote">{evidence.quote}</blockquote><div className="meta-grid"><div>作品 / 版本<b>{work.id} / {evidence.versionId}</b></div><div>段落<b>{evidence.paragraphId}</b></div><div>字符位置<b>[{evidence.startChar}, {evidence.endChar})</b></div><div>审核状态<b>{evidence.reviewStatus}</b></div></div><p className="caption">Unicode code point 计数；起点包含、终点不包含。当前文本范围：{scopeNames[work.scope]}。</p><section className="source-context"><h3>原文上下文</h3>{valid ? <p>{from > 0 ? '…' : ''}{points.slice(from, evidence.startChar).join('')}<mark>{points.slice(evidence.startChar, evidence.endChar).join('')}</mark>{points.slice(evidence.endChar, to).join('')}{to < points.length ? '…' : ''}</p> : <p>{source || '当前版本未找到对应段落。'}</p>}</section>{evidence.note && <p className="muted">引用说明：{evidence.note}</p>}<section className="linked-annotations"><h3><Link2 size={16} />使用这条证据的判断</h3>{annotations.length ? annotations.map(a => <article key={a.id}><span className="pill neutral">{a.group}</span><b>{valueNames[a.value] ?? a.value}</b><p>{a.rationale}</p><small>{a.reviewStatus}</small></article>) : <p className="muted">暂未关联当前版本的标签。</p>}</section></Modal>
}

export function TracePanel({ steps }: { steps: TraceStep[] }) {
  return <div className="trace-list">{steps.length ? steps.map((step, index) => <article className="trace-step" key={`${step.tool}-${index}`}><span className="trace-number">{String(step.index ?? index + 1).padStart(2, '0')}</span><div className="trace-detail"><div className="trace-label"><b>{step.tool}</b><span className={`trace-status ${step.status}`}>{step.status}</span><small>{step.durationMs.toLocaleString()} ms</small></div>{step.summary && <p>{step.summary}</p>}{(step.input !== undefined || step.output !== undefined) && <details><summary>查看真实输入与输出</summary>{step.input !== undefined && <><h4>输入</h4><pre>{JSON.stringify(step.input, null, 2)}</pre></>}{step.output !== undefined && <><h4>输出</h4><pre>{JSON.stringify(step.output, null, 2)}</pre></>}</details>}</div></article>) : <p className="muted">该任务没有已记录的工具步骤。</p>}</div>
}

export function ReviewDialog({ annotation, work, onClose, onSave }: { annotation: Annotation; work: Work; onClose: () => void; onSave: (changes: ReviewChanges) => Promise<void> }) {
  const [value, setValue] = useState(annotation.value)
  const [rationale, setRationale] = useState(annotation.rationale)
  const [evidenceIds, setEvidenceIds] = useState(annotation.evidenceIds.filter(eid => work.evidence.some(e => e.id === eid && evidenceIsCurrent(work, e))))
  const [reviewStatus, setReviewStatus] = useState<ReviewStatus>(annotation.reviewStatus)
  const [error, setError] = useState(annotation.evidenceIds.some(eid => !work.evidence.some(e => e.id === eid && evidenceIsCurrent(work, e))) ? '部分原引用已失效，已取消选择。请重新检查证据后保存。' : '')
  const [saving, setSaving] = useState(false)
  const id = useId()
  const options = [...new Set([annotation.value, ...(optionsByGroup[annotation.group] ?? ['unknown', 'not_applicable'])])]
  const special = value === 'unknown'
  const endingBlocked = annotation.group === '承诺兑现' && !special && (work.scope !== 'full_text' || !work.endingConfirmed)
  async function save(event: FormEvent) {
    event.preventDefault(); setError('')
    if (!rationale.trim()) { setError('请填写此次判断的理由或修订原因。'); return }
    if (endingBlocked) { setError('未确认全文与结尾范围，请保留“不足以判断”。“不适用”同样需要确认范围与证据。'); return }
    if (!special && (!evidenceIds.length || evidenceIds.some(eid => !work.evidence.some(e => e.id === eid && evidenceIsCurrent(work, e))))) { setError('请为非空判断选择通过当前版本校验的原文证据。'); return }
    if (!special && ['包装钩子', '情绪承诺', '承诺兑现'].includes(annotation.group) && !evidenceIds.some(eid => work.evidence.some(e => e.id === eid && ['标题', '导语'].includes(e.field)))) { setError('这类判断需要标题或导语的原文支持，不能只引用正文或结尾。'); return }
    if (annotation.group === '承诺兑现' && !special && !evidenceIds.some(eid => work.evidence.some(e => e.id === eid && e.field === '结尾'))) { setError('承诺兑现判断需要至少一条已确认范围内的结尾证据。'); return }
    setSaving(true)
    try { await onSave({ value, rationale: rationale.trim(), evidenceIds, reviewStatus }) } catch (error) { setError(error instanceof Error ? error.message : String(error)) } finally { setSaving(false) }
  }
  return <Modal title={`审核 · ${annotation.group}`} eyebrow="HUMAN REVIEW" onClose={() => { if (!saving) onClose() }}><form onSubmit={event => void save(event)}><p className="muted">{work.title} · {work.versionId}。修改会记录前后值，并使既有报告过期。</p><div className="form-grid"><label className="field-label" htmlFor={`${id}-value`}>内容判断<select id={`${id}-value`} value={value} disabled={saving} onChange={event => { setValue(event.target.value); setEvidenceIds([]); setRationale(''); setReviewStatus('待审核'); setError('') }}>{options.map(option => <option key={option} value={option}>{valueNames[option] ?? option}</option>)}</select></label><label className="field-label" htmlFor={`${id}-status`}>审核结论<select id={`${id}-status`} value={reviewStatus} disabled={saving} onChange={event => setReviewStatus(event.target.value as ReviewStatus)}><option>待审核</option><option>已审核</option><option>需复核</option></select></label></div><label className="field-label" htmlFor={`${id}-reason`}>判断理由 / 修订原因<textarea id={`${id}-reason`} rows={3} required maxLength={5000} value={rationale} disabled={saving} onChange={event => setRationale(event.target.value)} placeholder="说明这段原文支持什么、不支持什么；修改标签后需要重新填写。" /></label><h3>重新选择支持这一判断的证据 <span className="count">{evidenceIds.length}</span></h3><p className="caption">更改标签值会清空原证据与理由。引用精确匹配不等于语义成立。</p><div className="candidate-list">{work.evidence.length ? work.evidence.map(evidence => { const valid = evidenceIsCurrent(work, evidence); return <label className={`candidate ${valid ? '' : 'disabled'}`} key={evidence.id}><input type="checkbox" disabled={!valid || saving} checked={evidenceIds.includes(evidence.id)} onChange={event => setEvidenceIds(ids => event.target.checked ? [...ids, evidence.id] : ids.filter(eid => eid !== evidence.id))} /><div><b>{evidence.field} · {evidence.id}</b><p>“{evidence.quote}”</p><small>{valid ? `${evidence.paragraphId} [${evidence.startChar}, ${evidence.endChar})` : '当前版本或文本范围未通过校验'}</small></div></label> }) : <p className="muted">当前作品没有候选证据；可先保存 unknown 与理由，或完成模型抽取后再审核。</p>}</div>{endingBlocked && <div className="banner warning">未确认完整结尾，不能接受兑现判断。</div>}{error && <div className="banner error" role="alert">{error}</div>}<div className="modal-actions"><button className="btn" type="button" disabled={saving} onClick={onClose}>取消</button><button className="btn primary" type="submit" disabled={saving || endingBlocked}>{saving ? <LoaderCircle size={15} className="spin" /> : <Check size={15} />}{saving ? '正在保存…' : '保存审核与修订'}</button></div></form></Modal>
}

export function ImportDialog({ onClose, onImport }: { onClose: () => void; onImport: (items: unknown[]) => Promise<ImportResult[]> }) {
  const id = useId()
  const [title, setTitle] = useState('')
  const [intro, setIntro] = useState('')
  const [text, setText] = useState('')
  const [scope, setScope] = useState<Scope>('opening_only')
  const [endingConfirmed, setEndingConfirmed] = useState(false)
  const [localConsent, setLocalConsent] = useState(false)
  const [modelConsent, setModelConsent] = useState(false)
  const [isSynthetic, setIsSynthetic] = useState(false)
  const [batch, setBatch] = useState<unknown[] | null>(null)
  const [fileName, setFileName] = useState('')
  const [results, setResults] = useState<ImportResult[]>([])
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const [reading, setReading] = useState(false)
  const limit = interactiveImportMaxBytes
  async function readFile(file?: File) {
    if (!file) return
    setError(''); setResults([])
    if (file.size > limit) { setError(`文件超过当前交互单次 ${interactiveImportLimitLabel} 上限；${largeFileAnalysisNote}`); return }
    if (!/\.(txt|json)$/i.test(file.name)) { setError('请选择 UTF-8 编码的 .txt 或 .json 文件。'); return }
    setReading(true)
    try {
      const content = (await file.text()).replace(/^\uFEFF/, '')
      if (/\.json$/i.test(file.name)) {
        const parsed: unknown = JSON.parse(content)
        const entries = Array.isArray(parsed) ? parsed : parsed && typeof parsed === 'object' && 'items' in parsed && Array.isArray(parsed.items) ? parsed.items : [parsed]
        if (!entries.length || entries.length > 100) throw new Error('JSON 每批应包含 1–100 条作品记录。')
        setBatch(entries)
      } else {
        setBatch(null); setText(content); if (!title.trim()) setTitle(file.name.replace(/\.txt$/i, ''))
      }
      setFileName(file.name)
    } catch (error) { setError(error instanceof Error ? error.message : '无法读取文件；请确认编码与 JSON 格式。') } finally { setReading(false) }
  }
  async function submit(event: FormEvent) {
    event.preventDefault(); setError(''); setResults([])
    if (!localConsent) { setError('导入前请确认拥有处理这些文本的权利，并同意保存在本地。'); return }
    if (!batch && !title.trim()) { setError('请填写作品标题。'); return }
    if (!batch && scope === 'full_text' && !endingConfirmed) { setError('全文导入需要明确确认结尾已包含在正文中。'); return }
    if (!batch && scope !== 'metadata_only' && !text.trim()) { setError('请选择标题与导语范围，或提供对应正文。'); return }
    if (!batch && new TextEncoder().encode(title + intro + text).length > limit) { setError(`文本超过当前交互单次 ${interactiveImportLimitLabel} 上限；${largeFileAnalysisNote}`); return }
    const entries = batch ?? [{ title: title.trim(), intro, text, scope, endingConfirmed: scope === 'full_text' && endingConfirmed, isSynthetic, sourceType: '本人导入文本' }]
    const valid: Record<string, unknown>[] = [], originalRows: number[] = [], localErrors: ImportResult[] = []
    entries.forEach((item, index) => {
      if (!item || typeof item !== 'object' || Array.isArray(item)) { localErrors.push({ row: index + 1, status: 'error', message: '该行必须是作品对象；未发送到后端。' }); return }
      valid.push({ ...item, isSynthetic: 'isSynthetic' in item ? item.isSynthetic : false, localConsent: true, modelConsent })
      originalRows.push(index + 1)
    })
    setSaving(true)
    try {
      const remote = valid.length ? await onImport(valid) : []
      setResults([...localErrors, ...remote.map((result, index) => ({ ...result, row: originalRows[result.row - 1] ?? originalRows[index] ?? result.row }))].sort((a, b) => a.row - b.row))
    } catch (error) { setError(error instanceof Error ? error.message : String(error)) } finally { setSaving(false) }
  }
  return <Modal title="把作品带入研究" eyebrow="IMPORT YOUR MATERIAL" onClose={() => { if (!saving && !reading) onClose() }} className="import-modal"><form onSubmit={event => void submit(event)}><label className="file-drop" onDragOver={event => event.preventDefault()} onDrop={event => { event.preventDefault(); if (!saving && !reading) void readFile(event.dataTransfer.files[0]) }}><Upload size={24} /><b>{reading ? '正在读取文件…' : fileName || '选择或拖入 TXT / JSON 文件'}</b><span>UTF-8 · 当前交互单次最多 {interactiveImportLimitLabel} · JSON 支持作品数组或 items 数组</span><input aria-label="选择作品文件" type="file" accept=".txt,.json,text/plain,application/json" disabled={saving || reading} onChange={event => { void readFile(event.target.files?.[0]); event.target.value = '' }} /></label>{batch ? <div className="import-note"><b>已读取 {batch.length} 条 JSON 记录</b><p>保留每条记录的文本、范围及 observations 原始指标。授权字段以下方当前勾选为准；字段问题、重复与导入结果逐行显示。</p><ul>{batch.slice(0, 5).map((item, index) => <li key={index}>{index + 1}. {item && typeof item === 'object' && 'title' in item ? String(item.title) : '未提供标题 / 待校验'}</li>)}</ul>{batch.length > 5 && <small>另有 {batch.length - 5} 条记录</small>}<button type="button" className="text-button" disabled={saving} onClick={() => { setBatch(null); setFileName(''); setResults([]) }}>改用手动粘贴</button></div> : <><label className="field-label" htmlFor={`${id}-title`}>作品标题<input id={`${id}-title`} value={title} maxLength={500} required disabled={saving} onChange={event => setTitle(event.target.value)} placeholder="填写真实标题，不自动生成" /></label><label className="field-label" htmlFor={`${id}-intro`}>导语<textarea id={`${id}-intro`} value={intro} rows={2} maxLength={5000} disabled={saving} onChange={event => setIntro(event.target.value)} placeholder="可留空" /></label><label className="field-label" htmlFor={`${id}-scope`}>此次提供的文本范围<select id={`${id}-scope`} value={scope} disabled={saving} onChange={event => { setScope(event.target.value as Scope); setEndingConfirmed(false) }}><option value="opening_only">仅开篇</option><option value="full_text">完整正文（包含结尾）</option><option value="metadata_only">仅标题与导语</option></select></label><label className="field-label" htmlFor={`${id}-text`}>正文<textarea id={`${id}-text`} value={text} rows={6} disabled={saving} onChange={event => setText(event.target.value)} placeholder={scope === 'metadata_only' ? '仅标题与导语时请留空。' : '粘贴有权处理的正文；段落会保留并生成版本指纹。'} /></label>{scope === 'full_text' && <label className="checkbox-label"><input type="checkbox" checked={endingConfirmed} disabled={saving} onChange={event => setEndingConfirmed(event.target.checked)} />我确认提供了全文，且最后部分包含真实结尾。</label>}<label className="checkbox-label"><input type="checkbox" checked={isSynthetic} disabled={saving} onChange={event => setIsSynthetic(event.target.checked)} />这些是虚构演示素材（默认按本人真实作品导入）</label></>}<div className="consent-box"><label><input type="checkbox" checked={localConsent} disabled={saving} onChange={event => setLocalConsent(event.target.checked)} /><span><b>我拥有处理这些文本的权利，同意在本机保存作品与分析记录。</b><small>必选。新导入的内容判断保留 unknown，等待抽取与人工审核。</small></span></label><label><input type="checkbox" checked={modelConsent} disabled={saving} onChange={event => setModelConsent(event.target.checked)} /><span><b>允许后续将这些作品发送至服务端配置的模型端点。</b><small>可选，默认关闭；仅导入不会立即调用模型。JSON 内预设授权不会覆盖这里的选择。</small></span></label></div>{error && <div className="banner error" role="alert"><AlertCircle size={16} />{error}</div>}{results.length > 0 && <section className="import-results" aria-live="polite"><h3><FileText size={17} />逐行导入结果</h3>{results.map((result, index) => <div key={`${result.row}-${index}`}><span className={`pill ${result.status === 'imported' ? 'green' : result.status === 'duplicate' ? 'neutral' : 'amber'}`}>{result.status === 'imported' ? '已导入' : result.status === 'duplicate' ? '重复作品' : '未导入'}</span><b>第 {result.row} 行</b><p>{result.message || (result.status === 'imported' ? '文本已保存，等待分析与审核。' : result.status)}</p>{result.workId && <small className="mono">{result.workId}</small>}</div>)}</section>}<div className="modal-actions"><button type="button" className="btn" disabled={saving || reading} onClick={onClose}>{results.length ? '完成' : '取消'}</button><button type="submit" className="btn primary" disabled={saving || reading || !localConsent}>{saving ? <LoaderCircle size={15} className="spin" /> : <Upload size={15} />}{saving ? '正在导入…' : batch ? `导入 ${batch.length} 条记录` : '导入作品'}</button></div></form></Modal>
}
