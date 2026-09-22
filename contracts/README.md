# Runtime contracts · v0.2

These JSON Schema files are generated from `backend/herlens/schemas.py`, not a separate hand-maintained specification.

```bash
node tools/python.mjs tools/export_contracts.py
```

`strategy-schema.json` defines the model extraction response (`annotations` and `evidence`). It replaces the v0.1 illustrative snake_case contract. The current browser/API use camelCase. Run metadata belongs to the persisted run record, not to the model-generated payload.

JSON Schema validates shape. Pydantic's cross-field validators additionally enforce exactly eight unique groups and the fulfillment enum. The extraction service checks current work/version/content hash, Unicode ranges, evidence fields and text scope. See `docs/UPGRADE_CONTRACT.md` for the endpoint/result contract.

Private source texts and credentials are never schema examples. Request examples live in the documented original/synthetic workflow.
