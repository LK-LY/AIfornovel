# Third-party notices

This file separates software dependencies from projects that informed the design. It is not a replacement for the license files distributed with installed packages.

## Runtime and development dependencies

The repository declares dependencies in `package-lock.json` and `backend/requirements.txt`. Direct frontend dependencies include:

| Package | License | Project |
| --- | --- | --- |
| React / React DOM | MIT | <https://github.com/facebook/react> |
| Vite / `@vitejs/plugin-react` | MIT | <https://github.com/vitejs/vite> |
| TypeScript | Apache-2.0 | <https://github.com/microsoft/TypeScript> |
| Lucide React | ISC | <https://github.com/lucide-icons/lucide> |

Python packages retain their own licenses and copyright notices. A production distributor should generate and review a complete software bill of materials from the locked dependency set before release.

## Upstream projects reviewed, not incorporated

HerLens was designed after reading fixed, public snapshots of two MIT-licensed projects:

1. `elecfish-yxf/novel-deconstructor`
   - Snapshot: [`a91931691af905fda04282988f3dd86e46e86646`](https://github.com/elecfish-yxf/novel-deconstructor/commit/a91931691af905fda04282988f3dd86e46e86646)
   - Upstream copyright: Copyright (c) 2026 elecfish-yxf
   - License: [MIT at the pinned snapshot](https://github.com/elecfish-yxf/novel-deconstructor/blob/a91931691af905fda04282988f3dd86e46e86646/LICENSE)
   - Reviewed areas: React/Vite/FastAPI structure, upload and normalization services, chapter splitting, task lifecycle, and export boundaries.

2. `Ce-Legend/novel-analysis-agent`
   - Snapshot: [`93e45864937cb3bc0794a5bdcfaaebe94e154c02`](https://github.com/Ce-Legend/novel-analysis-agent/commit/93e45864937cb3bc0794a5bdcfaaebe94e154c02)
   - Upstream copyright: Copyright (c) 2026 Ce-Legend
   - License: [MIT at the pinned snapshot](https://github.com/Ce-Legend/novel-analysis-agent/blob/93e45864937cb3bc0794a5bdcfaaebe94e154c02/LICENSE)
   - Reviewed areas: structured response models, chunk aggregation, evidence fields, mock workflows, and report checks.

As of the verification recorded in [`docs/UPSTREAM_REVIEW.md`](./docs/UPSTREAM_REVIEW.md), this repository does **not** copy source code from either upstream project and does not claim runtime integration with them. Architectural ideas, public interfaces, and general engineering patterns are not presented as copied implementation.

If a future change copies or adapts upstream code, that pull request must:

- identify every source file and pinned upstream revision;
- preserve the upstream copyright and MIT permission notice;
- update this file from “reviewed, not incorporated” to an exact file-level attribution;
- add regression tests for the adopted behavior; and
- re-check licenses for assets, example data, and transitive dependencies separately.

## Optional local analysis and report tools

The full-file analysis command invokes the user's installed Codex CLI with existing authentication; this repository does not embed credentials or redistribute the CLI. The optional polished HTML export uses the installed Data Analytics plugin's canonical report builder, reader, and verifier. HerLens supplies its own analysis payload and a narrowly scoped Windows scrollbar compatibility adjustment; it does not claim authorship of that report-rendering runtime. Plugin source and private generated reports are not copied into this repository's public assets. Markdown and structured analysis outputs do not require that renderer.

## Demonstration content and private source rights

`fixtures/demo.json` contains synthetic demonstration material created for HerLens. It is not sourced from the two upstream projects or from a publishing platform. Local private works and benchmark inputs are excluded from the public repository and are not relicensed by the HerLens MIT license.
