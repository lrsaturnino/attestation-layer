"""Frozen Pillar C contracts for the B↔C / A↔C boundary (PC-2).

Pillar C graduates language adapters into real verticals (Solidity, Go). Pillar B (the S∧R
composition / verification core) and Pillar A (intake / translation) build against the shapes C
emits — the call graph, the source-impact set, the normalized trace, and the system-spec registry.
For the parallel pillars not to drift, C freezes those shapes at SP1 and the other pillars compile
against this single, versioned surface plus a stub, rather than reaching into C's internal modules.

This module is that surface. It:

  * re-exports the frozen contract models so Pillar B/A import them from one stable place;
  * pins each contract to a frozen version and the committed JSON Schema that freezes its shape;
  * is enforced by ``tests/test_c_contracts_freeze.py`` — every pinned model's generated schema
    must equal its committed file, so a field change is a deliberate, reviewed schema bump rather
    than silent drift.

The lossy EVM-vs-Go trace-normalization rules are documented on :class:`NormalizedTrace` itself
(``models.NormalizedTrace``), which PC-3/PC-4 (and later PC-7) populate.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Type

from pydantic import BaseModel

from .models import (
    NormalizedTrace,
    NormalizedTraceArtifact,
    NormalizedTraceProducer,
)
from .source_adapter import SourceCallGraph
from .source_impact import ProductionSourceImpactReport, SourceImpactAnalysisArtifact
from .system_spec import SystemSpecEntry, SystemSpecRegistry


# The frozen B↔C / A↔C contract surface version. Bump this (and the affected per-contract version
# below) only with a reviewed schema change; PC-2's freeze test pins the shapes against the
# committed JSON Schemas so an unreviewed field change fails CI.
# 1.1 adds the agnostic, optional ``NormalizedTraceProducer.raw_output`` (a backward-compatible
# field B/A consumers ignore) so the capability gate is source-bound, not shape-bound (PC-1).
C_SIDE_CONTRACT_INTERFACE_VERSION = "1.1"


@dataclass(frozen=True)
class FrozenCContract:
    """One frozen Pillar C contract: its name, pinned version, model, and committed schema file."""

    contract_id: str
    version: str
    model: Type[BaseModel]
    schema_file: str
    description: str


# The frozen contracts Pillar B/A consume. Each is version-stamped and tied to the committed schema
# that freezes its shape. SystemSpecEntry is frozen through SystemSpecRegistry (its container),
# which is where its init_op/next_op/invariants operator metadata lives in the schema.
FROZEN_C_CONTRACTS: tuple[FrozenCContract, ...] = (
    FrozenCContract(
        contract_id="normalized-trace",
        version="0.2",
        model=NormalizedTraceArtifact,
        schema_file="normalized-traces.schema.json",
        description=(
            "Ecosystem-agnostic, call-and-event-level execution trace with optional recorded "
            "real-tool producer provenance; populated by PC-4 (Foundry) and PC-7 (Go). 0.2 adds "
            "the producer's captured raw_output so the capability gate can source-bind the evidence."
        ),
    ),
    FrozenCContract(
        contract_id="system-spec-registry",
        version="0.1",
        model=SystemSpecRegistry,
        schema_file="system-spec-registry.schema.json",
        description=(
            "Registry of reviewed system specs S, including each entry's init_op/next_op/invariants "
            "operator metadata the S∧R composition reads."
        ),
    ),
    FrozenCContract(
        contract_id="source-call-graph",
        version="0.1",
        model=SourceCallGraph,
        schema_file="source-call-graph.schema.json",
        description="Caller→callee edges over manifest modules; produced by PC-3 (Slither) for Solidity.",
    ),
    FrozenCContract(
        contract_id="source-impact-analysis",
        version="0.1",
        model=SourceImpactAnalysisArtifact,
        schema_file="source-impact-analysis.schema.json",
        description="Call-graph-reachable affected-module set for a requirement's bound symbols.",
    ),
    FrozenCContract(
        contract_id="production-source-impact-report",
        version="0.2",
        model=ProductionSourceImpactReport,
        schema_file="production-source-impact-report.schema.json",
        description="Confidence-scored, gateable source-impact report over resolved symbols + traces.",
    ),
)


# The frozen SystemSpecEntry operator fields PB-1 added; pinned here so the freeze test fails if any
# is renamed or removed out from under the S∧R composition that depends on them.
FROZEN_SYSTEM_SPEC_ENTRY_OPERATOR_FIELDS: tuple[str, ...] = ("init_op", "next_op", "invariants")


__all__ = [
    "C_SIDE_CONTRACT_INTERFACE_VERSION",
    "FROZEN_C_CONTRACTS",
    "FROZEN_SYSTEM_SPEC_ENTRY_OPERATOR_FIELDS",
    "FrozenCContract",
    "NormalizedTrace",
    "NormalizedTraceArtifact",
    "NormalizedTraceProducer",
    "ProductionSourceImpactReport",
    "SourceCallGraph",
    "SourceImpactAnalysisArtifact",
    "SystemSpecEntry",
    "SystemSpecRegistry",
]
