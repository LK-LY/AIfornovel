import rawWorks from '../fixtures/demo.json'
import type { Work, WorkspaceState } from './types'

export const works = rawWorks as unknown as Work[]
export const demoState: WorkspaceState = {
  works, revision: 1, runs: [], reports: [], history: [], mode: 'readonly',
  provider: { configured: false, model: '', baseUrl: '' },
}
