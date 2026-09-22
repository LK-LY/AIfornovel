# HerLens v0.2 implementation boundary

Frontend: existing React/Vite/TypeScript. Backend: FastAPI with local SQLite persistence. Browser UI uses camelCase shapes. Python service modules use plain dictionaries at boundaries. Public static build only reads fixtures; local mode explicitly connects to `/api/strategy`. No runtime key in browser.

## Shared shape

Work retains src/types.ts fields, adding `versionId`, `contentHash`, `endingConfirmed`, `localConsent`, `modelConsent`, `revision`, `observations` (array of MetricObservation; legacy metric remains first observation). Paragraph fields: id, label, text. Annotation: id, group, label, value, rationale, evidenceIds, reviewStatus, revision. Evidence as src/types.ts, plus contentHash. Metric: id, versionId, definition, channel, windowSpec, countingUnit, impressions?, clicks?, readers?, ctrReported?, windowStart, windowEnd, observationType (interval/snapshot), window, unit, status. Review strings: 已审核/待审核/需复核. Special values: unknown/not_applicable; fulfillment enum fulfilled/partial/contradicted/unknown/not_applicable. Eight groups from design.

State: `{works,revision,runs,reports,history,provider:{configured,model,baseUrl},mode:'local'|'readonly'}`.

## REST contract

- GET /api/strategy/state → State
- GET /api/strategy/health → {status,mode,schemaVersion}
- POST /api/strategy/datasets/import body `{items:[{title,intro,text,scope,endingConfirmed,localConsent,modelConsent,isSynthetic,author?,sourceType?,observations?}]}` → `{results:[{row,status:'imported'|'duplicate'|'error',workId?,message}],revision}`. No silent drops. TXT/paste normalization and size check. Imported annotations initially unknown; no fake LLM results.
- POST /api/strategy/runs body `{workIds,mode:'fixture'|'live',idempotencyKey}` → Run. Fixture can only replay known seed inputs. Live accepts only server-configured endpoint/key and work modelConsent. Run `{id,status,mode,model,cacheHit,createdAt,durationMs,steps:[{tool,status,summary,durationMs}],errors:[],workIds}`; synchronous bounded execution is acceptable. Failures persisted; restart unfinished→interrupted.
- GET /api/strategy/runs/{id} → Run
- PATCH /api/strategy/annotations/{id} body `{value,rationale,evidenceIds,reviewStatus,expectedRevision}` → `{annotation,revision}`. Conflict 409, invalid evidence 422. Every change records before/after/reason and invalidates reports. Accepted nonunknown annotations require exact evidence and coverage checks. Rejected supported by reviewStatus=需复核, value=unknown + rationale.
- POST /api/strategy/comparisons body `{workIds,group:'包装钩子',reviewedOnly:true}` → Comparison (below)
- POST /api/strategy/research-runs body `{workIds,question,group,reviewedOnly:true}` → Report (below)
- GET /api/strategy/reports/{id} → Report; old reports return `stale:true`
- GET /api/strategy/reports/{id}/export?format=md|html|xlsx → download; stale refused 409.

Comparison: `{queryId,revision,sampleCount,missingCount,sourceSnapshot,group,reviewedOnly,frequencies:[{value,count,workIds,evidenceIds}],metricGroups:[{key,definition,channel,windowSpec,countingUnit,workIds,observations,impressions,clicks,ctr}],excluded:[{workId,observationId?,reason}],sql,params,durationMs}`. Frequencies count each work once per field/value. Metrics must isolate synthetic/real cohorts, match version/definition/channel/window/countingUnit, reject overlapping intervals and cumulative snapshots, zero exposure denominator null; reported CTR never reverse-engineered.

Report: `{id,question,revision,createdAt,stale,mode:'deterministic-research',sampleCount,findings:[{id,title,observation,evidenceIds,queryIds,scope,limitation,nextStep,criterion}],trace:[{index,tool,status:'completed'|'refused',input,output,durationMs}],comparison}`. Always inspect_dataset first; at most 6 actions; no arbitrary SQL/network tools. Draft from computed outputs only, max 3 findings. Trace faithfully records actual execution, refusal causes, and evidence IDs. Manual changes require new report.

## Module ownership / cross-module signatures

`backend/herlens/store.py`: Store(path=None), state(), get_work(id), list_works(), revision(), save_report(report), get_report(id); sqlite file path available as `store.path`. Core backend agent owns API/storage/extraction/seed/tests for core.

`backend/herlens/analytics.py`: `compare(works:list[dict], revision:int, group:str='包装钩子', reviewed_only:bool=True)->dict`; analytics agent owns own in-memory SQLite query with actual SQL execution, exports and research.
`backend/herlens/research.py`: `research(works, revision, question, group='包装钩子', reviewed_only=True)->dict` calls compare and bounded tools, returns Report; no persistence (API handles save_report).
`backend/herlens/exporting.py`: `export_report(report, works, format)->tuple[bytes,str,str]` (bytes, media_type, filename).

Stable synthetic seed at `fixtures/demo.json` is a Work array, reused by UI and backend. All fixture outputs must be explicitly labeled precomputed, not model/human accuracy. pytest fixtures use tempfile databases. Runtime data excluded from Git. Public static mode never fetches private backend automatically. GitHub Actions build/test and manual Pages deployment are inactive examples under `docs/workflow-examples/`; local execution does not depend on them.
