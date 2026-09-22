import type { WorkspaceState, Report, Comparison, Run, ReviewStatus } from '../types'

const root = '/api/strategy'
export const isLocalBuild = import.meta.env.VITE_API_MODE === 'local'

async function request<T>(path: string, body?: unknown, method = 'POST'): Promise<T> {
  const res = await fetch(`${root}${path}`, body === undefined ? undefined : {
    method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  })
  if (!res.ok) {
    const data = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }))
    throw new Error(typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail ?? data))
  }
  return res.json() as Promise<T>
}

export const api = {
  state: () => request<WorkspaceState>('/state'),
  import: (items: unknown[]) => request<{ results: { row: number; status: string; workId?: string; message: string }[]; revision: number }>('/datasets/import', { items }),
  annotate: (id: string, data: { value: string; rationale: string; evidenceIds: string[]; reviewStatus: ReviewStatus; expectedRevision: number }) => request(`/annotations/${encodeURIComponent(id)}`, data, 'PATCH'),
  run: (workIds: string[], mode: 'live' | 'fixture', idempotencyKey: string) => request<Run>('/runs', { workIds, mode, idempotencyKey }),
  compare: (workIds: string[], group: string, reviewedOnly = true) => request<Comparison>('/comparisons', { workIds, group, reviewedOnly }),
  research: (workIds: string[], question: string, group: string, reviewedOnly = true) => request<Report>('/research-runs', { workIds, question, group, reviewedOnly }),
  exportUrl: (id: string, format: 'md' | 'html' | 'xlsx') => `${root}/reports/${encodeURIComponent(id)}/export?format=${format}`,
}
