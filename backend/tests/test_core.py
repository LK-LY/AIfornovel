from __future__ import annotations

import json

from fastapi.testclient import TestClient
import pytest

from herlens.analytics import compare, valid_evidence
from herlens.api import create_app
from herlens.extraction import (
    EvidenceValidationError,
    ProviderConfig,
    extract_live,
    validate_evidence,
)
from herlens.schemas import GROUPS
from herlens.store import Store


def imported_item(**overrides):
    item = {
        "title": "她说：重新开始🌱",
        "intro": "一个明确的本地测试导语。",
        "text": "第一段从门口开始。\n\n最后一段在灯下结束。",
        "scope": "full_text",
        "endingConfirmed": True,
        "localConsent": True,
        "modelConsent": False,
        "isSynthetic": False,
        "author": "测试作者",
        "sourceType": "pytest paste",
        "observations": [],
    }
    item.update(overrides)
    return item


@pytest.fixture()
def store(tmp_path):
    return Store(tmp_path / "herlens.sqlite3")


@pytest.fixture()
def client(store):
    return TestClient(create_app(store=store, testing=True))


def _import(client: TestClient, item=None):
    response = client.post(
        "/api/strategy/datasets/import", json={"items": [item or imported_item()]}
    )
    assert response.status_code == 200, response.text
    result = response.json()["results"][0]
    assert result["status"] == "imported", result
    return result["workId"]


def _work(client: TestClient, work_id: str):
    state = client.get("/api/strategy/state").json()
    return next(work for work in state["works"] if work["id"] == work_id), state


def test_seed_is_persistent_complete_and_exact(store, monkeypatch):
    monkeypatch.setenv("HERLENS_API_KEY", "super-secret")
    monkeypatch.setenv("HERLENS_MODEL", "test-model")
    state = store.state()
    assert len(state["works"]) == 4
    assert state["revision"] == 1
    assert state["provider"] == {
        "configured": True,
        "model": "test-model",
        "baseUrl": "https://api.openai.com/v1",
    }
    assert "super-secret" not in json.dumps(state, ensure_ascii=False)
    for work in state["works"]:
        assert {annotation["group"] for annotation in work["annotations"]} == set(GROUPS)
        assert len(work["contentHash"]) == 64
        for evidence in work["evidence"]:
            assert evidence["contentHash"] == work["contentHash"]
            validate_evidence(work, evidence)

    reopened = Store(store.path)
    assert reopened.state()["works"] == state["works"]


def test_import_returns_every_row_and_never_invents_labels(client):
    response = client.post(
        "/api/strategy/datasets/import",
        json={
            "items": [
                imported_item(),
                imported_item(localConsent=False, title="拒绝落盘"),
                {"title": "结构错误"},
            ]
        },
    )
    assert response.status_code == 200
    results = response.json()["results"]
    assert [result["status"] for result in results] == ["imported", "error", "error"]
    work, _ = _work(client, results[0]["workId"])
    assert len(work["annotations"]) == 8
    assert {annotation["value"] for annotation in work["annotations"]} == {"unknown"}
    assert all(not annotation["evidenceIds"] for annotation in work["annotations"])
    assert [evidence["field"] for evidence in work["evidence"]] == [
        "标题",
        "导语",
        "开篇",
        "结尾",
    ]
    for evidence in work["evidence"]:
        assert evidence["reviewStatus"] == "待审核"
        validate_evidence(work, evidence)

    duplicate = client.post(
        "/api/strategy/datasets/import", json={"items": [imported_item()]}
    ).json()["results"][0]
    assert duplicate["status"] == "duplicate"
    assert duplicate["workId"] == work["id"]


def test_import_scope_and_size_guards_are_explicit(client):
    items = [
        imported_item(title="metadata body", scope="metadata_only", endingConfirmed=False),
        imported_item(title="opening ending", scope="opening_only", endingConfirmed=True),
        imported_item(title="too large", text="字" * (512 * 1024)),
    ]
    results = client.post(
        "/api/strategy/datasets/import", json={"items": items}
    ).json()["results"]
    assert [result["status"] for result in results] == ["error", "error", "error"]
    assert "metadata_only" in results[0]["message"]
    assert "opening_only" in results[1]["message"]
    assert "maximum" in results[2]["message"]


def test_full_text_middle_paragraph_is_body_not_opening(client):
    work_id = _import(
        client,
        imported_item(text="开场。\n\n发展中的正文。\n\n收束结尾。", title="三段结构"),
    )
    work, _ = _work(client, work_id)
    assert [paragraph["label"].split(" · ")[0] for paragraph in work["paragraphs"]] == [
        "开篇",
        "正文",
        "结尾",
    ]
    assert [evidence["field"] for evidence in work["evidence"][-3:]] == [
        "开篇",
        "正文",
        "结尾",
    ]
    for evidence in work["evidence"]:
        validate_evidence(work, evidence)
    valid = valid_evidence(work)
    middle = next(e for e in work["evidence"] if e["field"] == "正文")
    assert middle["id"] in valid
    forged = dict(middle, id="forged-opening", field="开篇")
    work["evidence"].append(forged)
    assert forged["id"] not in valid_evidence(work)


def test_single_paragraph_full_text_has_exact_opening_and_ending_candidates(client):
    work_id = _import(client, imported_item(text="一段完整的微型故事。", title="单段全文"))
    work, _ = _work(client, work_id)
    paragraph_evidence = [
        evidence for evidence in work["evidence"] if evidence["paragraphId"].startswith("p")
    ]
    assert {evidence["field"] for evidence in paragraph_evidence} == {"开篇", "结尾"}
    assert {evidence["id"] for evidence in paragraph_evidence} <= set(valid_evidence(work))
    for evidence in paragraph_evidence:
        validate_evidence(work, evidence)


def test_annotation_patch_exact_evidence_revision_and_ending_coverage(client):
    work_id = _import(client)
    work, state = _work(client, work_id)
    hook = next(a for a in work["annotations"] if a["group"] == "包装钩子")
    title_evidence = next(e for e in work["evidence"] if e["field"] == "标题")
    response = client.patch(
        f"/api/strategy/annotations/{hook['id']}",
        json={
            "value": "标题结果前置",
            "rationale": "标题明确给出重新开始。",
            "evidenceIds": [title_evidence["id"]],
            "reviewStatus": "已审核",
            "expectedRevision": state["revision"],
        },
    )
    assert response.status_code == 200, response.text
    new_revision = response.json()["revision"]
    assert new_revision == state["revision"] + 1

    conflict = client.patch(
        f"/api/strategy/annotations/{hook['id']}",
        json={
            "value": "另一个值",
            "rationale": "stale client",
            "evidenceIds": [title_evidence["id"]],
            "reviewStatus": "已审核",
            "expectedRevision": state["revision"],
        },
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["currentRevision"] == new_revision

    work, state = _work(client, work_id)
    fulfillment = next(a for a in work["annotations"] if a["group"] == "承诺兑现")
    no_ending = client.patch(
        f"/api/strategy/annotations/{fulfillment['id']}",
        json={
            "value": "fulfilled",
            "rationale": "缺少结尾覆盖。",
            "evidenceIds": [title_evidence["id"]],
            "reviewStatus": "已审核",
            "expectedRevision": state["revision"],
        },
    )
    assert no_ending.status_code == 422
    assert "ending" in no_ending.json()["detail"]

    unknown_evidence = client.patch(
        f"/api/strategy/annotations/{fulfillment['id']}",
        json={
            "value": "unknown",
            "rationale": "证据候选不存在。",
            "evidenceIds": ["ev-does-not-exist"],
            "reviewStatus": "需复核",
            "expectedRevision": state["revision"],
        },
    )
    assert unknown_evidence.status_code == 422


def test_packaging_and_fulfillment_require_domain_coverage(client):
    work_id = _import(client, imported_item(title="覆盖规则"))
    work, state = _work(client, work_id)
    hook = next(a for a in work["annotations"] if a["group"] == "包装钩子")
    opening = next(e for e in work["evidence"] if e["field"] == "开篇")
    rejected = client.patch(
        f"/api/strategy/annotations/{hook['id']}",
        json={
            "value": "冲突前置",
            "rationale": "正文证据不能证明包装。",
            "evidenceIds": [opening["id"]],
            "reviewStatus": "已审核",
            "expectedRevision": state["revision"],
        },
    )
    assert rejected.status_code == 422
    assert "title or intro" in rejected.json()["detail"]

    # The deterministic analytics boundary repeats the same rule, so callers
    # cannot bypass PATCH validation by injecting a raw in-memory work.
    forged = next(a for a in work["annotations"] if a["group"] == "包装钩子")
    forged.update(value="冲突前置", rationale="malicious raw row", evidenceIds=[opening["id"]], reviewStatus="已审核")
    comparison = compare(
        [work], state["revision"], group="包装钩子", reviewed_only=True
    )
    assert comparison["frequencies"] == []
    assert any("标题" in row["reason"] for row in comparison["excluded"])

    # Fulfillment needs both sides of the promise-to-outcome chain.
    fulfillment = next(a for a in work["annotations"] if a["group"] == "承诺兑现")
    ending = next(e for e in work["evidence"] if e["field"] == "结尾")
    ending_only = client.patch(
        f"/api/strategy/annotations/{fulfillment['id']}",
        json={
            "value": "fulfilled",
            "rationale": "只有结尾，没有包装承诺。",
            "evidenceIds": [ending["id"]],
            "reviewStatus": "已审核",
            "expectedRevision": state["revision"],
        },
    )
    assert ending_only.status_code == 422
    assert "title or intro" in ending_only.json()["detail"]


def test_unicode_offsets_and_ending_guard(client):
    work_id = _import(client, imported_item(scope="opening_only", endingConfirmed=False, text="A🌱女主开门。"))
    work, _ = _work(client, work_id)
    paragraph = work["paragraphs"][0]
    evidence = {
        "id": "unicode-span",
        "workId": work_id,
        "versionId": work["versionId"],
        "contentHash": work["contentHash"],
        "field": "开篇",
        "paragraphId": paragraph["id"],
        "quote": "🌱女主",
        "startChar": 1,
        "endChar": 4,
        "reviewStatus": "待审核",
    }
    validate_evidence(work, evidence)
    evidence["endChar"] = 3
    with pytest.raises(EvidenceValidationError):
        validate_evidence(work, evidence)
    evidence.update(field="结尾", quote="🌱女主", endChar=4)
    with pytest.raises(EvidenceValidationError, match="confirmed full_text"):
        validate_evidence(work, evidence)


def test_fixture_run_is_exact_and_idempotent_and_failure_is_durable(client):
    first = client.post(
        "/api/strategy/runs",
        json={"workIds": ["HL-024"], "mode": "fixture", "idempotencyKey": "fx-1"},
    )
    assert first.status_code == 200
    assert first.json()["status"] == "completed"
    assert "precomputed" in first.json()["steps"][0]["summary"]
    second = client.post(
        "/api/strategy/runs",
        json={"workIds": ["HL-024"], "mode": "fixture", "idempotencyKey": "fx-1"},
    ).json()
    assert second["id"] == first.json()["id"]
    assert second["cacheHit"] is True

    work_id = _import(client, imported_item(title="not a seed"))
    failed = client.post(
        "/api/strategy/runs",
        json={"workIds": [work_id], "mode": "fixture", "idempotencyKey": "fx-bad"},
    ).json()
    assert failed["status"] == "failed"
    fetched = client.get(f"/api/strategy/runs/{failed['id']}").json()
    assert fetched["status"] == "failed"
    reused_failure = client.post(
        "/api/strategy/runs",
        json={"workIds": [work_id], "mode": "fixture", "idempotencyKey": "fx-bad"},
    ).json()
    assert reused_failure["id"] == failed["id"]
    assert reused_failure["cacheHit"] is False

    partial = client.post(
        "/api/strategy/runs",
        json={
            "workIds": [work_id, "HL-019"],
            "mode": "fixture",
            "idempotencyKey": "fx-partial",
        },
    ).json()
    assert partial["status"] == "partial_failed"
    assert [step["status"] for step in partial["steps"]] == ["failed", "completed"]
    assert partial["errors"][0]["workId"] == work_id


def test_fresh_fixture_run_never_overwrites_human_review(client):
    work, state = _work(client, "HL-024")
    annotation = next(a for a in work["annotations"] if a["group"] == "包装钩子")
    title_evidence = next(e for e in work["evidence"] if e["field"] == "标题")
    patch = client.patch(
        f"/api/strategy/annotations/{annotation['id']}",
        json={
            "value": "人工保留值",
            "rationale": "人工已经核对，候选回放不得覆盖。",
            "evidenceIds": [title_evidence["id"]],
            "reviewStatus": "已审核",
            "expectedRevision": state["revision"],
        },
    )
    assert patch.status_code == 200, patch.text
    run = client.post(
        "/api/strategy/runs",
        json={
            "workIds": ["HL-024"],
            "mode": "fixture",
            "idempotencyKey": "fixture-after-human-review",
        },
    ).json()
    assert run["status"] == "completed"
    after, _ = _work(client, "HL-024")
    retained = next(a for a in after["annotations"] if a["group"] == "包装钩子")
    assert retained["value"] == "人工保留值"
    assert retained["rationale"] == "人工已经核对，候选回放不得覆盖。"
    assert retained["reviewStatus"] == "已审核"


def _provider_content_from_request(payload):
    document = json.loads(payload["messages"][1]["content"])["untrustedDocument"]
    title_id = next(e["id"] for e in document["availableEvidence"] if e["field"] == "标题")
    ending_id = next(e["id"] for e in document["availableEvidence"] if e["field"] == "结尾")
    annotations = []
    for group in GROUPS:
        annotations.append(
            {
                "group": group,
                "label": group,
                "value": "fulfilled" if group == "承诺兑现" else "grounded-demo",
                "rationale": "This is a pending structured proposal.",
                "evidenceIds": [title_id, ending_id] if group == "承诺兑现" else [title_id],
            }
        )
    return json.dumps({"annotations": annotations, "evidence": []}, ensure_ascii=False)


def test_live_run_repairs_once_and_never_returns_secret(tmp_path, monkeypatch):
    monkeypatch.setenv("HERLENS_API_KEY", "never-return-this-secret")
    monkeypatch.setenv("HERLENS_BASE_URL", "https://provider.invalid/v1")
    monkeypatch.setenv("HERLENS_MODEL", "structured-test")
    calls = []

    def fake_request(url, headers, payload, timeout):
        calls.append((url, headers, payload, timeout))
        content = "{}" if len(calls) == 1 else _provider_content_from_request(payload)
        return {"choices": [{"message": {"content": content}}]}

    app = create_app(
        data_path=tmp_path / "live.sqlite3", provider_request=fake_request, testing=True
    )
    with TestClient(app) as live_client:
        work_id = _import(live_client, imported_item(modelConsent=True, title="live work"))
        run = live_client.post(
            "/api/strategy/runs",
            json={"workIds": [work_id], "mode": "live", "idempotencyKey": "live-1"},
        ).json()
        assert run["status"] == "completed", run
        assert len(calls) == 2
        assert "2 attempt" in run["steps"][0]["summary"]
        state_text = json.dumps(live_client.get("/api/strategy/state").json())
        assert "never-return-this-secret" not in state_text
        work, _ = _work(live_client, work_id)
        assert all(annotation["reviewStatus"] == "待审核" for annotation in work["annotations"])


def test_live_run_without_model_consent_never_calls_provider(tmp_path, monkeypatch):
    monkeypatch.setenv("HERLENS_API_KEY", "must-not-be-used")
    monkeypatch.setenv("HERLENS_BASE_URL", "https://provider.invalid/v1")
    monkeypatch.setenv("HERLENS_MODEL", "structured-test")
    calls = []

    def forbidden_request(url, headers, payload, timeout):
        calls.append((url, headers, payload, timeout))
        raise AssertionError("provider must not be called without per-work consent")

    app = create_app(
        data_path=tmp_path / "no-consent.sqlite3",
        provider_request=forbidden_request,
        testing=True,
    )
    with TestClient(app) as live_client:
        work_id = _import(
            live_client, imported_item(modelConsent=False, title="no model consent")
        )
        run = live_client.post(
            "/api/strategy/runs",
            json={
                "workIds": [work_id],
                "mode": "live",
                "idempotencyKey": "no-consent-live",
            },
        ).json()
        assert run["status"] == "failed"
        assert calls == []
        assert "modelConsent" in run["errors"][0]["message"]


def test_live_json_repair_is_bounded_to_two(tmp_path, monkeypatch):
    monkeypatch.setenv("HERLENS_API_KEY", "bounded-secret")
    monkeypatch.setenv("HERLENS_BASE_URL", "https://provider.invalid/v1")
    monkeypatch.setenv("HERLENS_MODEL", "structured-test")
    calls = []

    def always_invalid(url, headers, payload, timeout):
        calls.append(payload)
        return {"choices": [{"message": {"content": "{}"}}]}

    app = create_app(
        data_path=tmp_path / "bounded.sqlite3",
        provider_request=always_invalid,
        testing=True,
    )
    with TestClient(app) as live_client:
        work_id = _import(live_client, imported_item(modelConsent=True, title="bounded"))
        run = live_client.post(
            "/api/strategy/runs",
            json={"workIds": [work_id], "mode": "live", "idempotencyKey": "bounded"},
        ).json()
        assert run["status"] == "failed"
        assert len(calls) == 3  # initial request plus at most two repairs
        assert "bounded-secret" not in json.dumps(run)


def test_restart_marks_unfinished_run_interrupted(tmp_path):
    path = tmp_path / "restart.sqlite3"
    store = Store(path)
    run, reused = store.start_run(
        idempotency_key="crash",
        fingerprint="f" * 64,
        mode="fixture",
        model="precomputed-fixture",
        work_ids=["HL-024"],
    )
    assert reused is False and run["status"] == "running"
    reopened = Store(path)
    recovered = reopened.get_run(run["id"])
    assert recovered["status"] == "interrupted"
    assert recovered["errors"][0]["code"] == "interrupted"


def test_report_becomes_stale_and_export_is_refused(client):
    report_response = client.post(
        "/api/strategy/research-runs",
        json={
            "workIds": ["HL-024", "HL-019"],
            "question": "哪些包装钩子有证据支持？",
            "group": "包装钩子",
            "reviewedOnly": True,
        },
    )
    assert report_response.status_code == 200, report_response.text
    report = report_response.json()
    fresh_export = client.get(
        f"/api/strategy/reports/{report['id']}/export", params={"format": "md"}
    )
    assert fresh_export.status_code == 200, fresh_export.text

    work, state = _work(client, "HL-024")
    annotation = next(a for a in work["annotations"] if a["group"] == "包装钩子")
    changed = client.patch(
        f"/api/strategy/annotations/{annotation['id']}",
        json={
            "value": "结果前置（人工修订）",
            "rationale": "人工修订后必须重新研究。",
            "evidenceIds": annotation["evidenceIds"],
            "reviewStatus": "已审核",
            "expectedRevision": state["revision"],
        },
    )
    assert changed.status_code == 200, changed.text
    assert client.get(f"/api/strategy/reports/{report['id']}").json()["stale"] is True
    stale_export = client.get(
        f"/api/strategy/reports/{report['id']}/export", params={"format": "md"}
    )
    assert stale_export.status_code == 409


def test_readonly_and_non_loopback_writes_are_rejected(tmp_path):
    readonly_app = create_app(data_path=tmp_path / "ro.sqlite3", read_only=True, testing=True)
    with TestClient(readonly_app) as readonly_client:
        response = readonly_client.post(
            "/api/strategy/datasets/import", json={"items": [imported_item()]}
        )
        assert response.status_code == 403
        assert readonly_client.get("/api/strategy/health").json()["mode"] == "readonly"

    remote_app = create_app(data_path=tmp_path / "remote.sqlite3", testing=False)
    with TestClient(remote_app, client=("203.0.113.8", 50000)) as remote_client:
        response = remote_client.post(
            "/api/strategy/datasets/import", json={"items": [imported_item()]}
        )
        assert response.status_code == 403
