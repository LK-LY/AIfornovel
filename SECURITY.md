# Security policy

HerLens processes manuscripts and optional performance observations that may be private, copyrighted, or commercially sensitive. Treat confidentiality failures as security issues even when no executable exploit is involved.

## Supported version

This portfolio repository is under active development. Security fixes target the current default branch; older snapshots are not maintained.

## Report privately

Use the repository's **Security → Report a vulnerability** flow to report a suspected issue. If private reporting is unavailable, contact the repository owner before sharing reproduction data. Do not open a public issue containing:

- API keys, access tokens, headers, or `.env` content;
- unpublished manuscript text or identifying excerpts;
- local absolute paths, database files, or raw model payloads; or
- an exploit that exposes another person's work.

Include the affected revision, mode (`readonly` or `local`), minimal synthetic reproduction steps, impact, and any suggested mitigation. Replace private text with a synthetic equivalent.

## Trust model

- **Public read-only mode:** uses bundled synthetic fixtures only. It must not accept uploads, contact a paid model endpoint, or contain private runtime data.
- **Local API mode:** binds to `127.0.0.1` by default. Imported text and SQLite state stay in ignored local directories unless the operator deliberately exports a reviewed artifact.
- **Optional model call:** requires both a server-side credential and per-work consent for model processing. A local-processing right does not imply permission to send text to a third party.
- **Novel text is untrusted input:** instructions inside a story are content, not commands. The research controller has no arbitrary shell, URL, or SQL-write tool.

## Credential handling

- Keep `HERLENS_API_KEY` in an ignored `.env` file or an operating-system secret store.
- Never prefix a secret with `VITE_`; Vite exposes such values to browser code.
- Do not persist credentials in browser storage, SQLite, reports, logs, traces, screenshots, fixtures, or CI artifacts.
- The inactive CI and Pages examples require no application/model credentials. Neither workflow is enabled in this release.
- Rotate a key immediately if it may have entered Git history or a public artifact; deleting the visible file alone is insufficient.

## Input and output safeguards

- Accept only documented formats and bounded sizes; P0 must not accept arbitrary server paths or ZIP extraction.
- Normalize text before hashing and locating evidence. An accepted evidence record must satisfy exact source matching for its version.
- Escape plain text and sanitize any Markdown before rendering.
- Reject path traversal and keep runtime output under the configured private data directory.
- Spreadsheet exports must neutralize formula-leading text such as `=`, `+`, `-`, and `@`.
- Do not publish raw prompts, raw model responses, private source text, or unreviewed exports.

## Deployment warning

The optional GitHub Pages workflow is an inactive example under `docs/workflow-examples/`; if separately enabled, it is designed to publish only the static read-only build by manual dispatch. No hosted demo is deployed by this release. The FastAPI service is a local demonstration service, not a hardened multi-tenant SaaS. Exposing it to a network requires authentication, origin restrictions, TLS, rate limiting, durable secret management, upload malware controls, retention/deletion policy, and a separate security review.
