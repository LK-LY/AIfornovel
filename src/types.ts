export type Scope = 'full_text' | 'opening_only' | 'metadata_only'
export type ReviewStatus = '已审核' | '待审核' | '需复核'

export type Evidence = {
  id: string
  workId: string
  versionId: string
  field: '标题' | '导语' | '开篇' | '正文' | '结尾'
  paragraphId: string
  quote: string
  startChar: number
  endChar: number
  reviewStatus: ReviewStatus
  note?: string
  contentHash?: string
}

export type Annotation = {
  id: string
  group: string
  label: string
  value: string
  rationale: string
  evidenceIds: string[]
  reviewStatus: ReviewStatus
}

export type MetricObservation = {
  id: string
  versionId: string
  window: string
  windowSpec: string
  channel: string
  definition: string
  unit: string
  countingUnit: string
  windowStart?: string
  windowEnd?: string
  observationType?: 'interval' | 'snapshot'
  impressions?: number
  clicks?: number
  readers?: number
  ctrReported?: number
  status: '可比' | '缺曝光' | '口径不一致'
}

export type Work = {
  id: string
  title: string
  author: string
  intro: string
  sourceType: string
  rightsStatus: string
  isSynthetic: boolean
  scope: Scope
  paragraphs: { id: string; label: string; text: string }[]
  annotations: Annotation[]
  evidence: Evidence[]
  metric?: MetricObservation
  updatedAt: string
  reviewStatus: ReviewStatus
  versionId: string
  contentHash: string
  endingConfirmed: boolean
  localConsent: boolean
  modelConsent: boolean
  revision: number
  observations: MetricObservation[]
}

export type View = 'library' | 'profile' | 'comparison' | 'memo'

export type TraceStep = { index?: number; tool: string; status: string; input?: unknown; output?: unknown; summary?: string; durationMs: number }
export type Run = { id: string; status: string; mode: string; model: string; cacheHit: boolean; createdAt: string; durationMs: number; steps: TraceStep[]; errors: unknown[]; workIds: string[] }
export type Frequency = { value: string; count: number; workIds: string[]; evidenceIds: string[] }
export type MetricGroup = { key: string; definition: string; channel: string; windowSpec: string; countingUnit: string; workIds: string[]; observations: MetricObservation[]; impressions: number; clicks: number; ctr: number | null }
export type Comparison = { queryId: string; revision: number; sampleCount: number; missingCount: number; sourceSnapshot: unknown; group: string; reviewedOnly: boolean; frequencies: Frequency[]; metricGroups: MetricGroup[]; excluded: { workId: string; observationId?: string; reason: string }[]; sql: string; params: unknown; durationMs: number }
export type Finding = { id: string; title: string; observation: string; evidenceIds: string[]; queryIds: string[]; scope: string; limitation: string; nextStep: string; criterion: string }
export type Report = { id: string; question: string; revision: number; createdAt: string; stale: boolean; mode: string; sampleCount: number; findings: Finding[]; trace: TraceStep[]; comparison: Comparison; refusal?: string }
export type RevisionEntry = { id?: string; annotationId?: string; revision: number; before: unknown; after: unknown; reason?: string; createdAt?: string }
export type WorkspaceState = { works: Work[]; revision: number; runs: Run[]; reports: Report[]; history: RevisionEntry[]; provider: { configured: boolean; model: string; baseUrl: string }; mode: 'local' | 'readonly' }
