"""Generate reviewable JSON Schema directly from the runtime request models."""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.herlens.schemas import (AnnotationPatch, ComparisonRequest, ImportRequest,
    ImportItem, ProviderExtraction, ResearchRunRequest, RunRequest)

MODELS = {
    "strategy-schema": ProviderExtraction,
    "import-item": ImportItem,
    "import-request": ImportRequest,
    "annotation-patch": AnnotationPatch,
    "comparison-request": ComparisonRequest,
    "research-request": ResearchRunRequest,
    "run-request": RunRequest,
}

if __name__ == "__main__":
    for name, model in MODELS.items():
        schema = model.model_json_schema()
        schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        (ROOT / "contracts" / f"{name}.json").write_text(
            json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Generated {len(MODELS)} contracts from runtime Pydantic models.")
