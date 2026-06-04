from __future__ import annotations

from pathlib import Path

from nlreq.dsl_v3 import DslV3Parser
from nlreq.formal_claim import (
    FormalClaim,
    FormalClaimFragment,
    build_formal_claim,
    formal_claim_to_proof_premise_routes,
)
from nlreq.models import EvidenceLevel


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

    assert by_kind["predicate"] == EvidenceLevel.SMT_CHECKED
    assert by_kind["rejection_order"] == EvidenceLevel.BOUNDED_CHECKED


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
