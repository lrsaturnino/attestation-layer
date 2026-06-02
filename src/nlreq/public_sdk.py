from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .jsonutil import sha256_json


PUBLIC_SDK_SCHEMA_VERSION = "0.1"
PUBLIC_SDK_TOOL_VERSION = "0.1"
PUBLIC_DOCS_FREEZE_SCHEMA_VERSION = "0.1"
REQUIRED_PUBLIC_AUDIENCES: tuple[str, ...] = (
    "user",
    "adapter_author",
    "backend_author",
    "operator",
)
REQUIRED_PUBLIC_DOC_TOPICS: tuple[str, ...] = (
    "evidence_labels",
    "limitations",
    "failure_modes",
    "cli_usage",
    "schema_guide",
    "adapter_guide",
    "ci_modes",
    "sdk_api",
)


class PublicDocEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    doc_id: str
    title: str
    path: str
    audience: Literal["user", "adapter_author", "backend_author", "operator"]
    schema_refs: list[str] = Field(default_factory=list)


class PublicSdkExample(BaseModel):
    model_config = ConfigDict(extra="forbid")

    example_id: str
    title: str
    path: str
    covers: list[str] = Field(default_factory=list)


class PublicDocumentationIndex(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = PUBLIC_SDK_SCHEMA_VERSION
    version: str
    docs: list[PublicDocEntry] = Field(default_factory=list)
    examples: list[PublicSdkExample] = Field(default_factory=list)
    tool: str = "nlreq.public_sdk"
    tool_version: str = PUBLIC_SDK_TOOL_VERSION

    @model_validator(mode="after")
    def validate_unique_ids(self) -> PublicDocumentationIndex:
        doc_ids = [doc.doc_id for doc in self.docs]
        example_ids = [example.example_id for example in self.examples]
        if len(doc_ids) != len(set(doc_ids)):
            raise ValueError("doc ids must be unique")
        if len(example_ids) != len(set(example_ids)):
            raise ValueError("example ids must be unique")
        return self


class PublicDocumentationCoverageReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = PUBLIC_SDK_SCHEMA_VERSION
    version: str
    result: Literal["passed", "blocked"]
    checked_docs: int = 0
    checked_examples: int = 0
    missing_docs: list[str] = Field(default_factory=list)
    missing_examples: list[str] = Field(default_factory=list)
    missing_schema_refs: list[str] = Field(default_factory=list)
    missing_audiences: list[str] = Field(default_factory=list)
    tool: str = "nlreq.public_sdk"
    tool_version: str = PUBLIC_SDK_TOOL_VERSION


class PublicDocumentationFreezeReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = PUBLIC_DOCS_FREEZE_SCHEMA_VERSION
    version: str
    result: Literal["passed", "blocked"]
    coverage_report_hash: str
    frozen_schema_hashes: dict[str, str] = Field(default_factory=dict)
    compatibility_commitments: list[str] = Field(default_factory=list)
    required_topics: list[str] = Field(default_factory=list)
    covered_topics: list[str] = Field(default_factory=list)
    missing_topics: list[str] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)
    input_hashes: dict[str, str] = Field(default_factory=dict)
    tool: str = "nlreq.public_sdk"
    tool_version: str = PUBLIC_SDK_TOOL_VERSION


def validate_public_documentation_index(
    index: PublicDocumentationIndex,
    *,
    existing_paths: set[str],
    existing_schemas: set[str] | None = None,
    required_audiences: tuple[str, ...] = REQUIRED_PUBLIC_AUDIENCES,
) -> PublicDocumentationCoverageReport:
    missing_docs = [doc.path for doc in index.docs if doc.path not in existing_paths]
    missing_examples = [
        example.path
        for example in index.examples
        if example.path not in existing_paths
    ]
    present_audiences = {doc.audience for doc in index.docs}
    missing_audiences = sorted(set(required_audiences) - present_audiences)
    missing_schema_refs: list[str] = []
    if existing_schemas is not None:
        missing_schema_refs = [
            f"{doc.doc_id}:{schema_ref}"
            for doc in index.docs
            for schema_ref in doc.schema_refs
            if schema_ref not in existing_schemas
        ]
    blocked = bool(
        missing_docs
        or missing_examples
        or missing_schema_refs
        or missing_audiences
        or not index.docs
        or not index.examples
    )
    return PublicDocumentationCoverageReport(
        version=index.version,
        result="blocked" if blocked else "passed",
        checked_docs=len(index.docs),
        checked_examples=len(index.examples),
        missing_docs=missing_docs,
        missing_examples=missing_examples,
        missing_schema_refs=missing_schema_refs,
        missing_audiences=missing_audiences,
    )


def build_public_documentation_freeze_report(
    index: PublicDocumentationIndex,
    coverage: PublicDocumentationCoverageReport,
    *,
    frozen_schema_hashes: dict[str, str],
    covered_topics: list[str] | None = None,
    required_topics: tuple[str, ...] | list[str] = REQUIRED_PUBLIC_DOC_TOPICS,
    compatibility_commitments: list[str] | None = None,
) -> PublicDocumentationFreezeReport:
    covered_topics = covered_topics or []
    compatibility_commitments = compatibility_commitments or []
    missing_topics = sorted(set(required_topics) - set(covered_topics))
    schema_refs = {
        schema_ref
        for doc in index.docs
        for schema_ref in doc.schema_refs
    }
    missing_frozen_schemas = sorted(schema_refs - set(frozen_schema_hashes))
    findings: list[str] = []
    if coverage.result != "passed":
        findings.append("public documentation coverage did not pass")
    if missing_topics:
        findings.append("public documentation is missing topics: " + ", ".join(missing_topics))
    if missing_frozen_schemas:
        findings.append("schema references are not frozen: " + ", ".join(missing_frozen_schemas))
    if not compatibility_commitments:
        findings.append("public SDK compatibility commitments are empty")
    return PublicDocumentationFreezeReport(
        version=index.version,
        result="blocked" if findings else "passed",
        coverage_report_hash=sha256_json(coverage),
        frozen_schema_hashes=frozen_schema_hashes,
        compatibility_commitments=compatibility_commitments,
        required_topics=list(required_topics),
        covered_topics=covered_topics,
        missing_topics=missing_topics,
        findings=findings,
        input_hashes={
            "index": sha256_json(index),
            "coverage": sha256_json(coverage),
            "frozen_schema_hashes": sha256_json(frozen_schema_hashes),
            "covered_topics": sha256_json(covered_topics),
            "compatibility_commitments": sha256_json(compatibility_commitments),
        },
    )


def build_default_public_documentation_index(version: str = "0.1") -> PublicDocumentationIndex:
    return PublicDocumentationIndex(
        version=version,
        docs=[
            PublicDocEntry(
                doc_id="getting-started",
                title="Getting Started",
                path="docs/getting-started.md",
                audience="user",
                schema_refs=["end-to-end-requirement-gate.schema.json"],
            ),
            PublicDocEntry(
                doc_id="adapter-sdk",
                title="Adapter SDK Guide",
                path="docs/adapter-sdk-guide.md",
                audience="adapter_author",
                schema_refs=["source-manifest.schema.json", "adapter-certification-report.schema.json"],
            ),
            PublicDocEntry(
                doc_id="formal-backend-sdk",
                title="Formal Backend Guide",
                path="docs/formal-backend-guide.md",
                audience="backend_author",
                schema_refs=["formal-backend-request.schema.json", "formal-backend-response.schema.json"],
            ),
            PublicDocEntry(
                doc_id="operator-guide",
                title="CI And Evidence Operator Guide",
                path="docs/operator-guide.md",
                audience="operator",
                schema_refs=["ci-pr-gate-report.schema.json", "artifact-store-manifest.schema.json"],
            ),
        ],
        examples=[
            PublicSdkExample(
                example_id="static-adapter-template",
                title="Static Adapter Template",
                path="examples/static-adapter-template",
                covers=["source adapter", "certification"],
            ),
            PublicSdkExample(
                example_id="ci-gate-template",
                title="CI Gate Template",
                path="examples/ci-gate-template",
                covers=["report-only", "hard-gate"],
            ),
        ],
    )
