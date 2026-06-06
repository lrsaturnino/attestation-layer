from __future__ import annotations

from pathlib import Path

from nlreq.dsl_v3 import DslV3Parser
from nlreq.formal_claim import (
    FormalClaim,
    FormalClaimFragment,
    build_formal_claim,
    build_proof_dispatch_plan_from_formal_claim,
    formal_claim_to_proof_premise_routes,
)
from nlreq.models import EvidenceLevel
from nlreq.proof_closure import build_proof_object, default_evidence_producer_mapping


FIXTURES = Path(__file__).parent / "fixtures" / "requirements"


def test_formal_claim_to_proof_premise_routes_maps_fragments() -> None:
    """Each non-scope FormalClaim fragment becomes a typed ProofPremiseRoute."""
    ir = DslV3Parser().parse_ir(
        FIXTURES.joinpath("authorization_precondition_v3.nlreq").read_text(),
        requirement_id="AUTH-001",
        title="Authorization precondition",
    )
    report = build_formal_claim(ir)
    assert report.result == "lowered"
    assert report.formal_claim is not None

    routes = formal_claim_to_proof_premise_routes(report.formal_claim)

    assert len(routes) == len(report.formal_claim.premises) + len(report.formal_claim.obligations)


def test_formal_claim_to_proof_premise_routes_evidence_by_kind() -> None:
    """Fragment kind determines required evidence level."""
    ir = DslV3Parser().parse_ir(
        FIXTURES.joinpath("authorization_precondition_v3.nlreq").read_text(),
        requirement_id="AUTH-001",
        title="Authorization precondition",
    )
    report = build_formal_claim(ir)
    assert report.formal_claim is not None

    routes = formal_claim_to_proof_premise_routes(report.formal_claim)
    by_kind = {r.node_kind: r.required_evidence for r in routes}
    by_backend = {r.node_kind: r.backend_id for r in routes}

    # A premise predicate is an uninterpreted boolean with no fragment-level SMT content; it
    # is discharged only by the requirement-level S ∧ R model check that interprets it under a
    # reviewed S. So it routes — like the rejection-order obligation — to solver_system_checker
    # at BOUNDED_CHECKED, the producer that runs the gate's S ∧ R, not to a fragment-level SMT.
    assert by_kind["predicate"] == EvidenceLevel.BOUNDED_CHECKED
    assert by_kind["rejection_order"] == EvidenceLevel.BOUNDED_CHECKED
    assert by_backend["predicate"] == "solver_system_checker"
    assert by_backend["rejection_order"] == "solver_system_checker"


def test_numeric_state_invariant_routes_to_solver_system_checker() -> None:
    """A numeric_invariant obligation is discharged by the S ∧ R producer, not generic Apalache."""
    ir = DslV3Parser().parse_ir(
        "requirement numeric_invariant:\n"
        "scope reserve\n"
        "when collateral >= 10 and collateral <= 50\n"
        "then keep collateral >= 1\n",
        requirement_id="NUMERIC-ROUTE-001",
        title="Numeric invariant",
    )
    report = build_formal_claim(ir)
    assert report.formal_claim is not None

    routes = formal_claim_to_proof_premise_routes(report.formal_claim)
    state_route = next(route for route in routes if route.node_kind == "state_invariant")

    assert state_route.backend_id == "solver_system_checker"
    assert state_route.required_evidence == EvidenceLevel.BOUNDED_CHECKED


def test_formal_claim_routes_count_matches_fragments() -> None:
    """ProofPremiseRoute count equals premises + obligations (not scope or action)."""
    ir = DslV3Parser().parse_ir(
        FIXTURES.joinpath("authorization_precondition_v3.nlreq").read_text(),
        requirement_id="AUTH-001",
        title="Authorization precondition",
    )
    report = build_formal_claim(ir)
    assert report.formal_claim is not None
    claim = report.formal_claim

    routes = formal_claim_to_proof_premise_routes(claim)
    expected_count = len(claim.premises) + len(claim.obligations)

    assert len(routes) == expected_count
    premise_route_ids = {r.premise_id for r in routes}
    for fragment in [*claim.premises, *claim.obligations]:
        assert fragment.fragment_id in premise_route_ids


def test_formal_claim_routes_backend_compatible_with_evidence() -> None:
    """Each route's backend_id can produce the route's required_evidence level.

    Routes must not default to system_checker for SMT_CHECKED or BOUNDED_CHECKED
    fragments — system_checker only allows CONSISTENCY_CHECKED. Each route must
    select a backend from the default producer mapping whose allowed_evidence_levels
    includes the required evidence.
    """
    ir = DslV3Parser().parse_ir(
        FIXTURES.joinpath("authorization_precondition_v3.nlreq").read_text(),
        requirement_id="AUTH-001",
        title="Authorization precondition",
    )
    report = build_formal_claim(ir)
    assert report.formal_claim is not None

    routes = formal_claim_to_proof_premise_routes(report.formal_claim)
    mapping = default_evidence_producer_mapping()
    producer_by_id = {p.producer_id: p for p in mapping.producers}

    for route in routes:
        producer = producer_by_id.get(route.backend_id)
        assert producer is not None, f"route has unknown backend_id: {route.backend_id}"
        assert route.required_evidence in producer.allowed_evidence_levels, (
            f"backend '{route.backend_id}' cannot produce "
            f"'{route.required_evidence}' (fragment kind: {route.node_kind})"
        )


def test_build_proof_dispatch_plan_from_formal_claim_routes_fragment_ids() -> None:
    """Dispatch plan routes have premise_ids matching the FormalClaim fragment IDs."""
    ir = DslV3Parser().parse_ir(
        FIXTURES.joinpath("authorization_precondition_v3.nlreq").read_text(),
        requirement_id="AUTH-001",
        title="Authorization precondition",
    )
    report = build_formal_claim(ir)
    assert report.formal_claim is not None
    claim = report.formal_claim

    plan = build_proof_dispatch_plan_from_formal_claim(claim)

    assert plan.policy_id == f"formal-claim:{claim.claim_id}"
    route_ids = {r.premise_id for r in plan.routes}
    for fragment in [*claim.premises, *claim.obligations]:
        assert fragment.fragment_id in route_ids, (
            f"fragment {fragment.fragment_id} ({fragment.kind}) not in dispatch plan routes"
        )


def test_proof_object_premises_contain_formal_fragment_ids() -> None:
    """ProofObject.premises[*].premise_id contains FormalClaim fragment IDs when using formal dispatch.

    With no backend results, premises are open (not discharged) — this is expected.
    The test asserts fragment IDs appear, not that they are discharged.
    """
    ir = DslV3Parser().parse_ir(
        FIXTURES.joinpath("authorization_precondition_v3.nlreq").read_text(),
        requirement_id="AUTH-001",
        title="Authorization precondition",
    )
    report = build_formal_claim(ir)
    assert report.formal_claim is not None
    claim = report.formal_claim

    plan = build_proof_dispatch_plan_from_formal_claim(claim)
    proof = build_proof_object(
        requirement=ir,
        backend_results=[],
        dispatch=plan,
    )

    premise_ids = {p.premise_id for p in proof.premises}
    for fragment in [*claim.premises, *claim.obligations]:
        assert fragment.fragment_id in premise_ids, (
            f"fragment {fragment.fragment_id} ({fragment.kind}) missing from ProofObject.premises"
        )
    # All premises are open (no backend results supplied) — not discharged
    assert all(p.status == "open" for p in proof.premises)
