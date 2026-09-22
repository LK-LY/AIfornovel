import { useEffect, useState } from 'react'
import { ArrowUpRight, BookOpen, ChevronRight, Database, Download, FileText, FlaskConical, FolderOpen, GitBranch, Layers3, Menu, Plus, RefreshCw, Search, Settings2, ShieldCheck, Sparkles, X } from 'lucide-react'
import { demoState } from './data'
import type { Annotation, Comparison, Evidence, Report, Run, View, Work, WorkspaceState } from './types'
import { api, isLocalBuild } from './strategy/api'
import { downloadText, groups, productScopeNote, reportMarkdown, scopeNames } from './strategy/domain'
import { ComparisonPanel, LibraryPanel, MemoPanel, ProfilePanel } from './strategy/pages'
import { EvidencePanel, ImportDialog, ReviewDialog, Modal, TracePanel } from './strategy/panels'
import './styles.css'

type Snapshot = { works: Work[]; comparison: Comparison; comparisons: Record<string, Comparison>; report: Report; generatedAt: string }
const navigation = [
  { id: 'library', title: '样本库', subtitle: '定义研究对象', icon: FolderOpen },
  { id: 'profile', title: '作品剖面', subtitle: '原文与内容判断', icon: BookOpen },
  { id: 'comparison', title: '对比分析', subtitle: '口径与描述性统计', icon: Layers3 },
  { id: 'memo', title: '研究备忘录', subtitle: '工具轨迹与验证方案', icon: FileText },
] as const

export default function App() {
  const [workspace, setWorkspace] = useState<WorkspaceState>(demoState)
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null)
  const [view, setView] = useState<View>('library')
  const [selectedId, setSelectedId] = useState('HL-024')
  const [dataset, setDataset] = useState<'demo' | 'private'>('demo')
  const [comparison, setComparison] = useState<Comparison | null>(null)
  const [report, setReport] = useState<Report | null>(null)
  const [group, setGroup] = useState('包装钩子')
  const [reviewedOnly, setReviewedOnly] = useState(true)
  const [question, setQuestion] = useState('标题与导语的情绪承诺，是否在开篇与结尾获得支持？')
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [showImport, setShowImport] = useState(false)
  const [showSettings, setShowSettings] = useState(false)
  const [showHistory, setShowHistory] = useState(false)
  const [evidence, setEvidence] = useState<{ work: Work; evidence: Evidence } | null>(null)
  const [review, setReview] = useState<Annotation | null>(null)
  const [runDetail, setRunDetail] = useState<Run | null>(null)
  const [navOpen, setNavOpen] = useState(false)
  const [connectionReady, setConnectionReady] = useState(!isLocalBuild)

  const writable = isLocalBuild && connectionReady && workspace.mode === 'local'
  const cohort = workspace.works.filter(w => dataset === 'demo' ? w.isSynthetic : !w.isSynthetic)
  const selected = cohort.find(w => w.id === selectedId) ?? cohort[0]
  const stale = Boolean(report && (report.stale || report.revision !== workspace.revision))

  async function refresh() {
    if (!isLocalBuild) return
    const state = await api.state()
    setWorkspace(state); setConnectionReady(true)
    if (report && report.revision !== state.revision) setReport({ ...report, stale: true })
    return state
  }

  async function perform(label: string, action: () => Promise<void>) {
    setBusy(label); setError('')
    try { await action() } catch (e) { setError(e instanceof Error ? e.message : String(e)) } finally { setBusy('') }
  }

  useEffect(() => {
    if (isLocalBuild) {
      api.state().then(state => { setWorkspace(state); setConnectionReady(true); const saved = state.reports.filter(r => Array.isArray(r.comparison.sourceSnapshot) && r.comparison.sourceSnapshot.length && r.comparison.sourceSnapshot.every((s: { isSynthetic?: boolean }) => s.isSynthetic === true)); if (saved.length) setReport(saved[saved.length - 1]) })
        .catch(e => { setError(`后端未连接。请运行 npm run dev:local 启动完整工作台。${e.message}`); setConnectionReady(false) })
    } else {
      fetch(`${import.meta.env.BASE_URL}demo-snapshot.json`).then(r => { if (!r.ok) throw new Error('公开演示快照未生成'); return r.json() as Promise<Snapshot> }).then(data => {
        setSnapshot(data); setWorkspace({ ...demoState, works: data.works, revision: data.report.revision }); setComparison(data.comparison); setReport(data.report)
      }).catch(e => setError(e.message))
    }
  }, [])

  useEffect(() => { if (!notice) return; const id = setTimeout(() => setNotice(''), 4200); return () => clearTimeout(id) }, [notice])

  function changeDataset(next: 'demo' | 'private') {
    setDataset(next); setComparison(next === 'demo' && !isLocalBuild ? snapshot?.comparison ?? null : null)
    setReport(next === 'demo' && !isLocalBuild ? snapshot?.report ?? null : null)
    const first = workspace.works.find(w => next === 'demo' ? w.isSynthetic : !w.isSynthetic)
    if (first) setSelectedId(first.id)
  }

  function openWork(work: Work) { setSelectedId(work.id); setView('profile'); setNavOpen(false) }
  function openEvidence(id: string) {
    for (const work of workspace.works) { const ev = work.evidence.find(e => e.id === id); if (ev) { setEvidence({ work, evidence: ev }); return } }
    setError('该证据不属于当前内容版本，请刷新作品后重试。')
  }

  async function compare() {
    await perform('正在执行只读 SQL', async () => {
      if (isLocalBuild) setComparison(await api.compare(cohort.map(w => w.id), group, reviewedOnly))
      else setComparison(snapshot?.comparisons[group] ?? snapshot?.comparison ?? null)
    })
  }

  async function research() {
    await perform('研究控制器正在执行工具', async () => {
      if (isLocalBuild) {
        const result = await api.research(cohort.map(w => w.id), question, group, reviewedOnly)
        setReport(result); setComparison(result.comparison); await refresh(); setReport(result)
      } else { setReport(snapshot?.report ?? null); setNotice('已打开由真实研究引擎执行并保存的演示报告') }
    })
  }

  async function analyze(mode: 'fixture' | 'live', workId = selected.id) {
    await perform(mode === 'live' ? '正在调用已配置模型并校验证据' : '正在验证预计算夹具', async () => {
      const run = await api.run([workId], mode, crypto.randomUUID()); setRunDetail(run); await refresh()
      setComparison(null)
      setNotice(run.status === 'failed' ? '本次抽取失败，错误与输入已保留' : '任务已记录，候选标签等待人工审核')
    })
  }

  const page = navigation.find(n => n.id === view)!
  return <div className="workspace">
    <aside className={`rail ${navOpen ? 'open' : ''}`}>
      <a className="wordmark" href="#" onClick={e => { e.preventDefault(); setView('library') }}><span className="logo">H<span /></span><span>HerLens<small>CONTENT RESEARCH LAB</small></span></a>
      <div className="workspace-label"><Sparkles size={18} /><div>女频内容研究<small>从一个问题，到一条证据</small></div></div>
      <p className="nav-caption">研究工作台</p>
      <nav aria-label="主要页面">{navigation.map((n, i) => <button key={n.id} className={`nav-item ${view === n.id ? 'active' : ''}`} aria-current={view === n.id ? 'page' : undefined} onClick={() => { setView(n.id); setNavOpen(false) }}><n.icon size={19} /><span>{n.title}<small>{n.subtitle}</small></span><em>0{i + 1}</em></button>)}</nav>
      <div className="rail-bottom"><div className="rail-principle"><ShieldCheck size={17} /><div>让判断可以被复查<small>文本证据 · 人工审核 · 统计口径</small></div></div><button className="rail-settings" onClick={() => setShowSettings(true)}><Settings2 size={16} />运行与方法<span>v0.2</span></button></div>
    </aside>
    <main className="main">
      <header className="topbar"><div className="crumb"><button className="mobile-menu icon-btn" aria-label="打开导航" onClick={() => setNavOpen(!navOpen)}><Menu size={20} /></button><span>工作空间</span><ChevronRight size={13} /><b>{page.title}</b></div><div className="top-actions"><span className={`mode-dot ${writable ? 'local' : ''}`} />{isLocalBuild ? connectionReady ? '本地持久化' : '等待后端连接' : '公开只读演示'}<span className="revision-badge">数据修订 r{workspace.revision}</span><button className="avatar" onClick={() => setShowHistory(true)} aria-label="查看修订历史"><GitBranch size={16} /></button></div></header>
      <div className="content">
        <div className="page-heading"><div><div className="eyebrow">HERLENS / {String(navigation.findIndex(n => n.id === view) + 1).padStart(2, '0')}</div><h1>{page.title}<span className="title-dot">.</span></h1><p>{({ library: '建立清楚的样本边界，让每次内容研究都有可靠的起点。', profile: '标题许下的承诺，在原文里走到了哪一步？', comparison: '在同一统计口径下看差异，也看见还不能回答的问题。', memo: '从证据与数据出发，形成下一步可以验证的内容假设。' })[view]}</p></div><div className="heading-actions">{view === 'library' ? <button className="btn primary" onClick={() => writable ? setShowImport(true) : setShowSettings(true)}><Plus size={16} />{writable ? '导入作品' : '如何使用本地版'}</button> : view === 'memo' && report ? <button className="btn primary" disabled={stale || !!busy} onClick={() => void downloadReport('md')}><Download size={16} />导出备忘录</button> : <button className="btn" onClick={() => setShowHistory(true)}><GitBranch size={15} />修订记录</button>}</div></div>
        {error && <div className="banner error" role="alert"><span>{error}</span><button className="icon-btn" aria-label="关闭错误" onClick={() => setError('')}><X size={16} /></button></div>}
        {busy && <div className="banner loading" role="status"><RefreshCw size={16} className="spin" />{busy}…</div>}
        <div className="dataset-strip"><div className="dataset-switch" aria-label="样本类型"><button className={dataset === 'demo' ? 'selected' : ''} onClick={() => changeDataset('demo')}>原创演示 <span>{workspace.works.filter(w => w.isSynthetic).length}</span></button>{isLocalBuild && <button className={dataset === 'private' ? 'selected' : ''} onClick={() => changeDataset('private')}>本地私有 <span>{workspace.works.filter(w => !w.isSynthetic).length}</span></button>}</div><span><ShieldCheck size={13} />{dataset === 'demo' ? '虚构文本与指标 · 只用于验证工作流' : '仅保存在本地 · 模型外发需逐作品确认'}</span></div>
        {view === 'library' && <LibraryPanel works={cohort} local={writable} openWork={openWork} openImport={() => writable ? setShowImport(true) : setShowSettings(true)} runs={workspace.runs} openRun={setRunDetail} />}
        {view === 'profile' && selected && <ProfilePanel work={selected} local={writable} busy={!!busy} providerReady={workspace.provider.configured} onEvidence={openEvidence} onReview={setReview} onAnalyze={analyze} onSelect={id => setSelectedId(id)} works={cohort} />}
        {view === 'profile' && !selected && <div className="empty card"><BookOpen size={28} /><h3>先导入一篇作品</h3><p>标题与导语也可以开始；缺失的正文部分会明确保留为空。</p></div>}
        {view === 'comparison' && <ComparisonPanel works={cohort} comparison={comparison} revision={workspace.revision} group={group} setGroup={g => { setGroup(g); setComparison(null) }} reviewedOnly={reviewedOnly} setReviewedOnly={v => { setReviewedOnly(v); setComparison(null) }} local={isLocalBuild} busy={!!busy} onCompare={compare} onEvidence={openEvidence} onWork={openWork} />}
        {view === 'memo' && <MemoPanel report={report} stale={stale} question={question} setQuestion={setQuestion} local={isLocalBuild} busy={!!busy} group={group} onGenerate={research} onEvidence={openEvidence} onExport={format => void downloadReport(format)} />}
        <footer className="page-footer"><span>HerLens · 独立内容研究项目</span><span>证据存在性 ≠ 语义正确性 · 描述性比较 ≠ 因果结论</span></footer>
      </div>
    </main>
    {evidence && <EvidencePanel {...evidence} onClose={() => setEvidence(null)} />}
    {showImport && <ImportDialog onClose={() => setShowImport(false)} onImport={async items => { const result = await api.import(items); const state = await refresh(); setComparison(null); setReport(null); const first = state?.works.find(w => result.results.some(r => r.workId === w.id && r.status === 'imported')); if (first) { setDataset(first.isSynthetic ? 'demo' : 'private'); setSelectedId(first.id) } return result.results }} />}
    {review && selected && <ReviewDialog annotation={review} work={selected} onClose={() => setReview(null)} onSave={async changes => { await api.annotate(review.id, { ...changes, expectedRevision: workspace.revision }); await refresh(); setComparison(null); setReview(null); setNotice('修订已保存；相关统计与备忘录需要重新生成') }} />}
    {runDetail && <Modal title="分析任务记录" eyebrow="EXTRACTION RUN" onClose={() => setRunDetail(null)}><div className="meta-grid"><div>模式<b>{runDetail.mode === 'fixture' ? '预计算夹具回放' : '真实模型抽取'}</b></div><div>状态<b>{runDetail.status}</b></div><div>缓存<b>{runDetail.cacheHit ? '命中' : '未使用'}</b></div></div><p className="mono">{runDetail.id}</p><TracePanel steps={runDetail.steps} />{runDetail.errors.length > 0 && <pre className="error-output">{JSON.stringify(runDetail.errors, null, 2)}</pre>}{writable && ['failed', 'partial_failed', 'interrupted'].includes(runDetail.status) && <button className="btn primary" disabled={!!busy} onClick={() => void analyze(runDetail.mode === 'live' ? 'live' : 'fixture', runDetail.workIds[0])}>以新任务重试失败作品</button>}</Modal>}
    {showHistory && <Modal title="每次修改都有来处" eyebrow="REVISION HISTORY" onClose={() => setShowHistory(false)}><p className="muted">当前数据修订 r{workspace.revision}。审核会保存修改前后值、理由和时间，旧报告保留原版本并标记过期。</p>{workspace.history.length ? workspace.history.slice().reverse().map((h, i) => <div className="history-entry" key={h.id ?? i}><div><GitBranch size={15} /><b>r{h.revision}</b><span>{h.createdAt}</span></div><p>{h.reason ?? '标签审核'}</p><details><summary>查看前后值</summary><pre>{JSON.stringify({ before: h.before, after: h.after }, null, 2)}</pre></details></div>) : <div className="empty"><GitBranch size={25} /><h3>{writable ? '尚无人工修订' : '这是预计算快照'}</h3><p>{writable ? '在作品剖面选择一个标签并提交审核，即可生成第一条记录。' : '本地版可演示“修改 → 统计更新 → 新报告”的完整过程。'}</p></div>}</Modal>}
    {showSettings && <Modal title="可以复现的内容研究" eyebrow="RUNTIME & METHOD" onClose={() => setShowSettings(false)}><div className="method-intro"><FlaskConical size={26} /><div><b>一个受限研究控制器，六个工具动作</b><p>先检查数据，再选择样本、执行 SQL、取回原文，最后生成带验证方案的备忘录。</p></div></div><div className="runtime-grid"><div><span>当前模式</span><b>{isLocalBuild ? '本地 API + SQLite' : '静态只读快照'}</b></div><div><span>模型端点</span><b>{workspace.provider.configured ? `${workspace.provider.model} · 已配置` : '未配置，仍可离线审核与研究'}</b></div></div><h3>本地启动</h3><pre className="code-block">{`python -m venv .venv\n.venv\\Scripts\\python -m pip install -r backend/requirements.txt\nnpm ci\nnpm run dev:local`}</pre><p className="muted">模型配置在服务端环境文件中填写 HERLENS_BASE_URL、HERLENS_MODEL、HERLENS_API_KEY；浏览器不接收密钥。只读页面不自动连接本地私有数据库。</p><h3>这份演示证明什么</h3><ul className="method-list"><li>{productScopeNote}</li><li>结构化标签与原文精确引用可以被检查。</li><li>人工修订、版本冲突和旧报告失效都有实际记录。</li><li>统计经过可比性检查，研究工具会在缺数时拒绝指标分支。</li><li>评测区分工程回归与人工标签质量。真实作品与 F1 仍需后续人工标注。</li></ul></Modal>}
    {notice && <div className="toast" role="status"><ShieldCheck size={16} />{notice}</div>}
  </div>

  async function downloadReport(format: 'md' | 'html' | 'xlsx') {
    if (!report || stale) return
    if (!isLocalBuild) {
      const a = document.createElement('a'); a.href = `${import.meta.env.BASE_URL}demo-memo.${format}`; a.download = `HerLens-demo-memo.${format}`; a.click(); return
    }
    await perform('正在生成导出文件', async () => {
      const response = await fetch(isLocalBuild ? api.exportUrl(report.id, format) : `${import.meta.env.BASE_URL}demo-memo.${format}`)
      if (!response.ok) { const e = await response.json(); throw new Error(typeof e.detail === 'string' ? e.detail : '导出失败，请检查报告版本') }
      const objectUrl = URL.createObjectURL(await response.blob()); const a = document.createElement('a'); a.href = objectUrl; a.download = `HerLens-${report.id}.${format}`; a.click(); setTimeout(() => URL.revokeObjectURL(objectUrl), 1000)
    })
  }
}
