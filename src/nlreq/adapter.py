from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from .jsonutil import sha256_json
from .models import (
    EvidenceCapability,
    EvidenceLevel,
    RequirementIR,
    SemanticNodeKind,
    Symbol,
    SymbolBinding,
    SymbolRef,
    SymbolResolution,
    ValidationResult,
    VerificationTask,
)
from .proof_closure import backend_for_proof_node


# v1 ``Predicate.op`` -> the proof-node kind the generic adapter routes that premise on. The op
# carries the encodable content, so comparisons keep their fine-grained kind (lt/lte/.../eq/neq) and
# reach the theory-aware SMT backend, ``in`` becomes ``membership`` and reaches cvc5's finite-set
# theory, and the authorization/approval predicates collapse to ``predicate`` for the core SMT
# consistency checker. This is intentionally FINER than the v1->v2 migration's
# ``compositional_ir._predicate_node`` (which collapses every op to ``predicate``): that migration is
# the coarse legacy lift, while this routing follows the authoritative per-premise policy (comparison
# -> smt-theories, membership -> cvc5). No contract compares the two artifacts, and a comparison
# premise is more honestly a theory query than a free boolean. Exhaustive over ``Predicate.op``; an
# unmapped op raises (``_node_kind_for_predicate_op``) rather than silently defaulting to a backend.
_PREDICATE_OP_NODE_KIND: dict[str, SemanticNodeKind] = {
    "authorized": "predicate",
    "not_authorized": "predicate",
    "approved": "predicate",
    "not_approved": "predicate",
    "eq": "eq",
    "neq": "neq",
    "gt": "gt",
    "lt": "lt",
    "gte": "gte",
    "lte": "lte",
    "in": "membership",
}

# v1 ``ExpectedResult.kind`` -> the proof-node kind of the obligation. This MIRRORS the authoritative
# migration ``compositional_ir._expected_node`` (rejected_before -> before, set/increase/decrease ->
# state_delta, not_change -> invariant, rejected/succeed -> predicate, emit -> event) so the
# obligation routes exactly as a migrated requirement's ``obligation.must`` node would; a drift test
# pins this map to that function. ``emit`` -> ``event`` currently routes to core_smt, weaker than a
# trace check — refine when an emit-obligation requirement with a real trace producer lands.
# Exhaustive over ``ExpectedResult.kind``; an unmapped kind raises rather than silently defaulting.
_EXPECTED_KIND_NODE_KIND: dict[str, SemanticNodeKind] = {
    "rejected": "predicate",
    "rejected_before": "before",
    "succeed": "predicate",
    "emit": "event",
    "not_change": "invariant",
    "set": "state_delta",
    "increase": "state_delta",
    "decrease": "state_delta",
}


def _node_kind_for_predicate_op(op: str) -> SemanticNodeKind:
    node_kind = _PREDICATE_OP_NODE_KIND.get(op)
    if node_kind is None:
        raise ValueError(f"no proof-node routing for premise predicate op {op!r}")
    return node_kind


def _node_kind_for_expected_kind(kind: str) -> SemanticNodeKind:
    node_kind = _EXPECTED_KIND_NODE_KIND.get(kind)
    if node_kind is None:
        raise ValueError(f"no proof-node routing for obligation expected kind {kind!r}")
    return node_kind


class Adapter(ABC):
    adapter_id: str
    target_kind: str

    @abstractmethod
    def resolve_symbols(self, refs: list[SymbolRef]) -> list[SymbolResolution]:
        raise NotImplementedError

    @abstractmethod
    def validate_binding(self, binding: SymbolBinding) -> ValidationResult:
        raise NotImplementedError

    @abstractmethod
    def available_evidence(self, symbols: list[Symbol]) -> list[EvidenceCapability]:
        raise NotImplementedError

    @abstractmethod
    def generate_tasks(self, ir: RequirementIR) -> list[VerificationTask]:
        raise NotImplementedError

    @abstractmethod
    def collect_evidence(self, task_results: list[object]) -> list[object]:
        raise NotImplementedError


class GenericAdapter(Adapter):
    adapter_id = "generic"
    target_kind = "static_symbol_table"

    def __init__(self, symbols: dict[str, dict[str, object]]):
        self._symbols = symbols

    def resolve_symbols(self, refs: list[SymbolRef]) -> list[SymbolResolution]:
        resolutions: list[SymbolResolution] = []
        for ref in refs:
            raw = self._symbols.get(ref.name)
            if raw is None:
                resolutions.append(
                    SymbolResolution(ref=ref, status="unresolved", reason="symbol not found")
                )
                continue
            if "matches" in raw:
                matches = _symbols_from_matches(ref.name, raw["matches"])
                if ref.expected_type:
                    matches = [symbol for symbol in matches if symbol.symbol_type == ref.expected_type]
                if not matches:
                    resolutions.append(
                        SymbolResolution(
                            ref=ref,
                            status="unresolved",
                            reason=f"expected {ref.expected_type}, found no matching symbols",
                        )
                    )
                    continue
                resolutions.append(
                    SymbolResolution(
                        ref=ref,
                        status="ambiguous",
                        symbols=matches,
                        reason="multiple symbols matched",
                    )
                )
                continue
            symbol_type = str(raw.get("type", "unknown"))
            if ref.expected_type and ref.expected_type != symbol_type:
                resolutions.append(
                    SymbolResolution(
                        ref=ref,
                        status="unresolved",
                        reason=f"expected {ref.expected_type}, found {symbol_type}",
                    )
                )
                continue
            resolutions.append(
                SymbolResolution(
                    ref=ref,
                    status="resolved",
                    symbols=[
                        Symbol(
                            name=ref.name,
                            symbol_type=symbol_type,
                            metadata={key: value for key, value in raw.items() if key != "type"},
                        )
                    ],
                )
            )
        return resolutions

    def validate_binding(self, binding: SymbolBinding) -> ValidationResult:
        raw = self._symbols.get(binding.symbol)
        if raw is None:
            return ValidationResult(valid=False, reason="binding symbol not found")
        symbol_type = str(raw.get("type", "unknown"))
        if symbol_type != binding.symbol_type:
            return ValidationResult(
                valid=False,
                reason=f"binding type mismatch: expected {binding.symbol_type}, found {symbol_type}",
            )
        return ValidationResult(valid=True)

    def available_evidence(self, symbols: list[Symbol]) -> list[EvidenceCapability]:
        if not symbols:
            return []
        return [
            EvidenceCapability(
                evidence_level=EvidenceLevel.STATICALLY_RESOLVED,
                description="Symbol exists in the generic static symbol table.",
            )
        ]

    def generate_tasks(self, ir: RequirementIR) -> list[VerificationTask]:
        # C1 is the whole-requirement self-consistency query (its SMT lives in smt/C1.smt2): one
        # core_smt check that the claim as a whole is satisfiable and supported. The per-premise tasks
        # below are a DIFFERENT granularity — one routed task per condition premise plus the
        # obligation, each sent via ``backend_for_proof_node`` to the backend that can actually
        # discharge its kind, so the verification plan names smt-theories/cvc5/apalache where the
        # propositional core_smt cannot encode the premise. C1 and any ``predicate`` premise both read
        # ``core_smt`` but are not duplicates: C1 is whole-requirement, the premise task is per-node.
        tasks: list[VerificationTask] = [
            VerificationTask(
                id="C1",
                backend="core_smt",
                description=f"SMT consistency and supported-claim check for {ir.requirement_id}.",
                input_hash=sha256_json(ir),
                payload={"requirement_id": ir.requirement_id, "claim_kind": ir.claim.kind},
            )
        ]
        for index, predicate in enumerate(ir.claim.condition):
            node_kind = _node_kind_for_predicate_op(predicate.op)
            backend = backend_for_proof_node("premise", node_kind)
            payload = {
                "requirement_id": ir.requirement_id,
                "role": "premise",
                "premise_index": index,
                "op": predicate.op,
                "node_kind": node_kind,
            }
            tasks.append(
                VerificationTask(
                    id=f"P{index + 1}",
                    backend=backend,
                    description=(
                        f"Check condition premise {index} ({predicate.op}) of "
                        f"{ir.requirement_id} via {backend}."
                    ),
                    input_hash=sha256_json(payload),
                    payload=payload,
                )
            )
        obligation_kind = _node_kind_for_expected_kind(ir.claim.expected.kind)
        obligation_backend = backend_for_proof_node("obligation", obligation_kind)
        obligation_payload = {
            "requirement_id": ir.requirement_id,
            "role": "obligation",
            "expected_kind": ir.claim.expected.kind,
            "node_kind": obligation_kind,
        }
        tasks.append(
            VerificationTask(
                id="O1",
                backend=obligation_backend,
                description=(
                    f"Check the {ir.claim.expected.kind} obligation of "
                    f"{ir.requirement_id} via {obligation_backend}."
                ),
                input_hash=sha256_json(obligation_payload),
                payload=obligation_payload,
            )
        )
        return tasks

    def collect_evidence(self, task_results: list[object]) -> list[object]:
        return task_results


def default_generic_adapter() -> GenericAdapter:
    return GenericAdapter(
        {
            "operation": {"type": "action"},
            "actor": {"type": "principal"},
            "authorized": {"type": "predicate"},
            "state_change": {"type": "state_transition"},
            "operation_status": {"type": "state"},
            "counter": {"type": "quantity"},
            "limit": {"type": "quantity"},
            "ambiguous_actor": {
                "matches": [
                    {"name": "ambiguous_actor_primary", "type": "principal"},
                    {"name": "ambiguous_actor_delegate", "type": "principal"},
                ]
            },
            "ambiguous_operation": {
                "matches": [
                    {"name": "ambiguous_operation_v1", "type": "action"},
                    {"name": "ambiguous_operation_v2", "type": "action"},
                ]
            },
        }
    )


def _symbols_from_matches(ref_name: str, raw_matches: Any) -> list[Symbol]:
    if not isinstance(raw_matches, list):
        return []
    symbols: list[Symbol] = []
    for index, raw in enumerate(raw_matches):
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name", f"{ref_name}_{index}"))
        symbol_type = str(raw.get("type", "unknown"))
        symbols.append(
            Symbol(
                name=name,
                symbol_type=symbol_type,
                metadata={str(key): value for key, value in raw.items() if key not in {"name", "type"}},
            )
        )
    return symbols
