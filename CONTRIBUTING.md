# Contributing to HerLens

HerLens accepts changes that make a content conclusion easier to audit, a metric safer to compare, or the demo easier to reproduce. More labels, more agents, or more charts are not goals by themselves.

## Before opening a change

1. Read [`docs/PROJECT_DESIGN.md`](./docs/PROJECT_DESIGN.md), [`docs/CODEBOOK.md`](./docs/CODEBOOK.md), and [`SECURITY.md`](./SECURITY.md).
2. Keep public fixtures synthetic or explicitly licensed for redistribution. Never commit a user's manuscript, platform screenshot, model request/response, API key, or private metric export.
3. Describe whether the change affects the public read-only mode, the local API mode, or both.
4. For annotation changes, provide a definition, positive example, counterexample, and `unknown` condition. Do not add a label that cannot be audited against text.
5. For metric changes, state the numerator, denominator, counting unit, channel, version link, and time-window rule.

## Local checks

```bash
npm ci
npm run build
npm run test:ui
python -m pip install -r backend/requirements.txt
python -m pytest -q
```

Run the read-only snapshot check when UI behavior or fixtures change:

```bash
npm run snapshot
```

Do not add a network-dependent model call to the default test suite. Tests must run without credentials and should use temporary databases and synthetic inputs.

## Pull request checklist

- [ ] The change has one clear user or research outcome.
- [ ] New behavior includes a deterministic test or a documented manual check.
- [ ] Empty, loading, failure, and insufficient-evidence states remain honest.
- [ ] Evidence references still match the normalized source exactly.
- [ ] Metric comparisons do not mix definitions, channels, windows, counting units, versions, synthetic and real cohorts, overlapping intervals, or cumulative snapshots.
- [ ] Public output contains no private text, credential, absolute local path, or raw model payload.
- [ ] Documentation describes current behavior, not planned behavior as if completed.
- [ ] Any copied or adapted third-party code is pinned and attributed in `THIRD_PARTY_NOTICES.md`.

## Commit and review guidance

Prefer small commits organized around one contract or behavior. A useful pull-request description contains:

- the question or failure being addressed;
- the before/after behavior;
- commands run and their results;
- data and privacy impact;
- screenshots for visible UI changes at 1366×768 and 1440×900; and
- known limitations or follow-up gates.

Reviewers should reject changes that silently drop invalid rows, infer missing denominators, turn correlation into causation, treat an exact quote as proof of semantic support, or expose a write-capable/public model endpoint by default.

## Adding real-case evidence

Real manuscripts are local inputs, not repository fixtures. Follow [`docs/REAL_CASE_INTAKE.md`](./docs/REAL_CASE_INTAKE.md); publish only a separately reviewed, redacted derivative if the rights holder explicitly authorizes public display.

## Reporting security issues

Do not open a public issue for suspected credential, manuscript, or path disclosure. Follow [`SECURITY.md`](./SECURITY.md).
# Public-file review

The repository has an explicit `.release-files.json` allowlist. Before adding a file, review it for manuscript text, personal data, credentials and machine-specific state; then update the allowlist. Run `npm run check:release -- --tracked` after staging reviewed source. The guard prints file paths and rule names, never matched secret values. It supplements manual inspection and does not guarantee all forms of sensitive data are detected.
