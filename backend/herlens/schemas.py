"""Validated request models and shared HerLens constants.

The browser speaks camelCase, so these models deliberately use the public field
names rather than relying on an implicit snake_case conversion layer.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


SCHEMA_VERSION = "0.2"

Scope = Literal["full_text", "opening_only", "metadata_only"]
ReviewStatus = Literal["已审核", "待审核", "需复核"]
RunMode = Literal["fixture", "live"]

GROUPS: tuple[str, ...] = (
    "题材语境",
    "叙事驱动力",
    "核心关系",
    "主角目标",
    "核心冲突",
    "情绪承诺",
    "包装钩子",
    "承诺兑现",
)

SPECIAL_VALUES = frozenset({"unknown", "not_applicable"})
FULFILLMENT_VALUES = frozenset(
    {"fulfilled", "partial", "contradicted", "unknown", "not_applicable"}
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class MetricObservationInput(StrictModel):
    id: str | None = Field(default=None, max_length=160)
    versionId: str | None = Field(default=None, max_length=80)
    definition: str = Field(min_length=1, max_length=200)
    channel: str = Field(min_length=1, max_length=200)
    windowSpec: str = Field(min_length=1, max_length=200)
    countingUnit: str = Field(min_length=1, max_length=80)
    impressions: int | None = Field(default=None, ge=0)
    clicks: int | None = Field(default=None, ge=0)
    readers: int | None = Field(default=None, ge=0)
    ctrReported: float | None = Field(default=None, ge=0, le=100)
    windowStart: str = Field(min_length=1, max_length=80)
    windowEnd: str = Field(min_length=1, max_length=80)
    observationType: Literal["interval", "snapshot"] = "interval"
    window: str = Field(min_length=1, max_length=200)
    unit: str = Field(min_length=1, max_length=80)
    status: Literal["可比", "缺曝光", "口径不一致"] = "可比"

    @model_validator(mode="after")
    def validate_counts(self) -> "MetricObservationInput":
        if (
            self.impressions is not None
            and self.clicks is not None
            and self.clicks > self.impressions
        ):
            raise ValueError("clicks cannot exceed impressions")
        return self


class ImportItem(StrictModel):
    title: str = Field(min_length=1, max_length=500)
    intro: str = Field(default="", max_length=5_000)
    text: str = ""
    scope: Scope
    endingConfirmed: bool
    localConsent: bool
    modelConsent: bool
    isSynthetic: bool
    author: str | None = Field(default=None, max_length=200)
    sourceType: str | None = Field(default=None, max_length=200)
    observations: list[MetricObservationInput] = Field(default_factory=list, max_length=100)


class ImportRequest(StrictModel):
    # Individual dictionaries are validated in the route so one bad row is
    # returned as status=error without silently discarding the other rows.
    items: list[dict[str, Any]] = Field(min_length=1, max_length=100)


class RunRequest(StrictModel):
    workIds: list[str] = Field(min_length=1, max_length=100)
    mode: RunMode
    idempotencyKey: str = Field(min_length=1, max_length=200)

    @field_validator("workIds")
    @classmethod
    def unique_work_ids(cls, values: list[str]) -> list[str]:
        stripped = [value.strip() for value in values]
        if any(not value for value in stripped):
            raise ValueError("workIds cannot contain empty values")
        if len(stripped) != len(set(stripped)):
            raise ValueError("workIds must be unique")
        return stripped


class AnnotationPatch(StrictModel):
    value: str = Field(min_length=1, max_length=500)
    rationale: str = Field(min_length=1, max_length=5_000)
    evidenceIds: list[str] = Field(default_factory=list, max_length=100)
    reviewStatus: ReviewStatus
    expectedRevision: int = Field(ge=0)

    @field_validator("evidenceIds")
    @classmethod
    def unique_evidence_ids(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("evidenceIds must be unique")
        return values


class ComparisonRequest(StrictModel):
    workIds: list[str] = Field(min_length=1, max_length=500)
    group: str = Field(default="包装钩子", min_length=1, max_length=100)
    reviewedOnly: bool = True

    @field_validator("workIds")
    @classmethod
    def comparison_work_ids(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("workIds must be unique")
        return values


class ResearchRunRequest(ComparisonRequest):
    question: str = Field(min_length=1, max_length=2_000)


class ProviderAnnotation(StrictModel):
    group: str = Field(min_length=1, max_length=100)
    label: str | None = Field(default=None, max_length=100)
    value: str = Field(min_length=1, max_length=500)
    rationale: str = Field(min_length=1, max_length=5_000)
    evidenceIds: list[str] = Field(default_factory=list, max_length=100)


class ProviderEvidence(StrictModel):
    id: str = Field(min_length=1, max_length=200)
    workId: str = Field(min_length=1, max_length=200)
    versionId: str = Field(min_length=1, max_length=100)
    contentHash: str = Field(min_length=64, max_length=64)
    field: Literal["标题", "导语", "开篇", "正文", "结尾"]
    paragraphId: str = Field(min_length=1, max_length=200)
    quote: str = Field(min_length=1)
    startChar: int = Field(ge=0)
    endChar: int = Field(gt=0)
    note: str | None = Field(default=None, max_length=2_000)

    @model_validator(mode="after")
    def validate_span(self) -> "ProviderEvidence":
        if self.endChar <= self.startChar:
            raise ValueError("endChar must be greater than startChar")
        return self


class ProviderExtraction(StrictModel):
    annotations: list[ProviderAnnotation] = Field(min_length=1, max_length=len(GROUPS))
    evidence: list[ProviderEvidence] = Field(default_factory=list, max_length=200)

    @model_validator(mode="after")
    def validate_groups(self) -> "ProviderExtraction":
        groups = [annotation.group for annotation in self.annotations]
        if len(groups) != len(set(groups)):
            raise ValueError("annotation groups must be unique")
        if set(groups) != set(GROUPS):
            missing = sorted(set(GROUPS) - set(groups))
            extra = sorted(set(groups) - set(GROUPS))
            raise ValueError(f"exactly the eight configured groups are required; missing={missing}, extra={extra}")
        for annotation in self.annotations:
            if annotation.group == "承诺兑现" and annotation.value not in FULFILLMENT_VALUES:
                raise ValueError("承诺兑现 must use the fulfillment enum")
        return self
