from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


PUBLIC_SDK_SCHEMA_VERSION = "0.1"
PUBLIC_SDK_TOOL_VERSION = "0.1"


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
