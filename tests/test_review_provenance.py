"""AC5 regression tests: fabricated package-builder reviews are explicitly non-human and cannot
back a ``PinningProvenance(kind="human_review")`` record (ADR 0206 §2; acceptance #5).

The package builders (``package._review`` + the per-language ``*_package.py`` builders) fabricate
an ``approved`` ``review.json`` under a ``phase<N>@example.invalid`` placeholder reviewer. The
positive ``review_origin`` contract (``ReviewArtifact``) labels every such fabrication
``"package_builder"`` — explicitly NON-human — and the construction guard makes a ``"human"``
origin unrepresentable under a placeholder reviewer. AC1 byte-identity (acceptance #1) requires
the DEFAULT pipeline output to be byte-identical to the pre-machine-pinning pipeline, so the
``review_origin`` field is carried at the MODEL level (a ``ReviewArtifact`` default of
``"package_builder"``), NOT serialized by the default builders. These tests assert, empirically:

  1. The generic ``_review(...)`` output (and every per-builder placeholder reviewer) does NOT
     serialize ``review_origin`` (byte-identical default output), and loads as a ``ReviewArtifact``
     whose origin defaults to ``"package_builder"`` — NOT a real human review
     (``is_real_human_review`` is False).
  2. The on-disk ``review.json`` written by a real ``build_package`` / ``build_python_package``
     run does NOT serialize ``review_origin`` (AC1 byte-identity), but loads as a ``ReviewArtifact``
     whose ``review_origin`` defaults to ``"package_builder"`` (explicitly non-human) and whose
     reviewer is a package-builder placeholder.
  3. None of those fabricated reviews can back a ``PinningProvenance(kind="human_review")``
     record: the ``human_review`` backing guard rejects the full placeholder family.

This closes the gap the original provenance-axis guard left open (the ``ReviewArtifact`` itself
previously accepted the fabricated review); the deeper stamping-path change — a machine package
emitting a pinning record INSTEAD of the fake review — has since shipped
(``build_package(pinning=...)`` writes a ``needs_review`` review plus a ``machine_agreement``
``pinning-provenance.json``).
"""
from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from nlreq.jsonutil import read_json
from nlreq.models import (
    PinningProvenance,
    ReviewArtifact,
    ReviewChecklist,
    is_real_human_review,
)
from nlreq.package import _review, build_package
from nlreq.parser import RequirementParser
from nlreq.python_adapter import PythonPackageAdapter
from nlreq.python_package import build_python_package


_FIXTURES = Path(__file__).parent / "fixtures" / "requirements"
_PYTHON_FIXTURE_PACKAGE = Path(__file__).parent / "fixtures" / "adapters" / "pythonpkg" / "samplepkg"
_PYTHON_TEST_PATH = Path("tests/fixtures/adapters/pythonpkg")
_REPO_ROOT = Path(__file__).parents[1]

# The placeholder reviewer every package builder writes its fabricated approved review.json under.
PACKAGE_BUILDER_PLACEHOLDER_REVIEWERS = [
    ("generic", "phase0@example.invalid"),
    ("python", "phase2@example.invalid"),
    ("openapi", "phase7@example.invalid"),
    ("command", "phase10@example.invalid"),
    ("tla", "phase13@example.invalid"),
    ("graphql", "phase14@example.invalid"),
    ("jsonschema", "phase15@example.invalid"),
    ("asyncapi", "phase16@example.invalid"),
    ("protobuf", "phase17@example.invalid"),
]

_VALID_HASH = "sha256:" + "a1" * 32

# The exact set of keys the pre-machine-pinning (pre-P1) package-builder review.json carried.
# AC1 byte-identity (acceptance #1) requires the default package output to be byte-identical to
# that pipeline, so a default ``build_package`` review.json MUST NOT introduce any new key (in
# particular the machine-pinning-era ``review_origin``), and rebuilding MUST be byte-stable. This
# is the regression guard against reintroducing the iter-5 default-off byte drift.
_PRE_P1_REVIEW_JSON_KEYS = frozenset(
    {
        "review_id",
        "reviewer",
        "decision",
        "self_audit",
        "reviewed_hashes",
        "checklist",
        "timestamp",
    }
)


def _ir():
    return RequirementParser().parse_ir(
        (_FIXTURES / "authorization_precondition.nlreq").read_text(),
        requirement_id="REQ-AUTH-001",
        title="Unauthorized operation is rejected before state changes",
        claim_kind="authorization_precondition",
        approved_by="phase0@example.invalid",
        approved_at="2026-05-26T00:00:00Z",
    )


# --- 1. The fabricated _review(...) output is explicitly non-human, for every builder ---


def test_default_package_review_json_is_byte_identical_to_pre_pinning_pipeline(
    tmp_path: Path,
) -> None:
    # AC1 byte-identity (acceptance #1): with machine pinning disabled (the default), the package
    # output is byte-identical to the pre-machine-pinning pipeline — no pinning-era key is added to
    # review.json, and the output is byte-stable across rebuilds. This regression test exists so a
    # future iteration cannot silently reintroduce the iter-5 default-off byte drift (which added
    # ``review_origin`` to the default builder output and the committed fixtures).
    text = (_FIXTURES / "authorization_precondition.nlreq").read_text()

    out_a = tmp_path / "build-a" / "REQ-AUTH-001"
    out_b = tmp_path / "build-b" / "REQ-AUTH-001"
    for out in (out_a, out_b):
        build_package(
            controlled_text=text,
            output_dir=out,
            requirement_id="REQ-AUTH-001",
            title="Unauthorized operation is rejected before state changes",
            claim_kind="authorization_precondition",
        )

    review_a = (out_a / "review.json").read_text()
    review_b = (out_b / "review.json").read_text()

    # Byte-stable across rebuilds.
    assert review_a == review_b
    # Exactly the pre-P1 key set — no machine-pinning-era key (review_origin) smuggled in.
    raw = read_json(out_a / "review.json")
    assert frozenset(raw) == _PRE_P1_REVIEW_JSON_KEYS
    assert "review_origin" not in raw


# --- 2. The fabricated _review(...) output is explicitly non-human, for every builder ---


def test_generic_review_dict_does_not_serialize_review_origin() -> None:
    # AC1 byte-identity (acceptance #1): the default package-builder review dict does NOT carry a
    # serialized ``review_origin`` key, so the default pipeline output is byte-identical to the
    # pre-machine-pinning pipeline. The non-human origin is carried at the MODEL level:
    # ``ReviewArtifact.review_origin`` defaults to ``"package_builder"``, so loading this
    # fabricated review yields the explicitly non-human origin (acceptance #5).
    review_dict = _review(_ir())  # the default phase0@example.invalid fabrication

    assert "review_origin" not in review_dict  # not serialized -> byte-identical default output
    assert review_dict["reviewer"] == "phase0@example.invalid"
    assert review_dict["decision"] == "approved"

    review = ReviewArtifact.model_validate(review_dict)
    assert review.review_origin == "package_builder"  # model-level default
    assert is_real_human_review(review) is False


@pytest.mark.parametrize(
    ("builder", "reviewer"),
    PACKAGE_BUILDER_PLACEHOLDER_REVIEWERS,
    ids=[builder for builder, _ in PACKAGE_BUILDER_PLACEHOLDER_REVIEWERS],
)
def test_every_package_builder_placeholder_reviewer_yields_a_non_human_review(
    builder: str, reviewer: str
) -> None:
    # Every package builder calls ``_review(ir, reviewer=phase<N>@...)`` to fabricate its approved
    # review.json. Each such review is explicitly ``package_builder`` (non-human), regardless of the
    # per-language placeholder reviewer it is attributed to.
    review_dict = _review(_ir(), reviewer=reviewer)

    # AC1 byte-identity: review_origin is NOT serialized by any package builder (every per-language
    # builder routes through _review), so the per-language default outputs are byte-identical to
    # pre-P1 too. The non-human origin is the model-level default on load.
    assert "review_origin" not in review_dict
    assert review_dict["reviewer"] == reviewer

    review = ReviewArtifact.model_validate(review_dict)
    assert review.review_origin == "package_builder"  # model-level default -> non-human
    assert is_real_human_review(review) is False


# --- 2. The on-disk review.json from a real build is explicitly non-human ---


def test_built_generic_package_review_json_does_not_serialize_review_origin(tmp_path: Path) -> None:
    out = tmp_path / "REQ-AUTH-001"
    build_package(
        controlled_text=(_FIXTURES / "authorization_precondition.nlreq").read_text(),
        output_dir=out,
        requirement_id="REQ-AUTH-001",
        title="Unauthorized operation is rejected before state changes",
        claim_kind="authorization_precondition",
    )

    raw = read_json(out / "review.json")
    # AC1 byte-identity: the on-disk review.json does NOT serialize review_origin.
    assert "review_origin" not in raw
    assert raw["reviewer"] == "phase0@example.invalid"

    review = ReviewArtifact.model_validate(raw)
    assert review.review_origin == "package_builder"  # model-level default -> non-human
    assert review.decision == "approved"
    assert is_real_human_review(review) is False


def test_built_python_package_review_json_is_non_human(tmp_path: Path) -> None:
    adapter = PythonPackageAdapter(
        _PYTHON_FIXTURE_PACKAGE,
        package_name="samplepkg",
        project_root=_REPO_ROOT,
        test_paths=[_PYTHON_TEST_PATH],
        property_checks=False,
    )
    out = tmp_path / "REQ-PY-001"
    build_python_package(
        controlled_text=(
            "For every operation request:\n"
            "if actor is approved\n"
            "then operation must succeed.\n"
        ),
        output_dir=out,
        requirement_id="REQ-PY-001",
        title="Python operation succeeds for approved actor",
        claim_kind="state_precondition",
        adapter=adapter,
    )

    raw = read_json(out / "review.json")
    # AC1 byte-identity: the python-builder review.json does NOT serialize review_origin either
    # (build_python_package routes through the shared _review helper).
    assert "review_origin" not in raw
    assert raw["reviewer"] == "phase2@example.invalid"

    review = ReviewArtifact.model_validate(raw)
    assert review.review_origin == "package_builder"  # model-level default -> non-human
    assert is_real_human_review(review) is False


# --- 3. No fabricated package-builder review can back a human_review provenance record ---


def _real_human_review_event() -> ReviewArtifact:
    # A REAL human review event: non-placeholder reviewer + review_origin="human".
    return ReviewArtifact(
        review_id="RVW-REQ-AUTH-001-001",
        reviewer="reviewer@example.org",
        decision="approved",
        reviewed_hashes={"requirement_ir": _VALID_HASH},
        checklist=ReviewChecklist(
            controlled_form_matches_intent="pass",
            claim_shape_matches_controlled_form="pass",
            source_spans_present="pass",
            assumptions_explicit="pass",
            bindings_justified="pass",
            evidence_level_appropriate="pass",
            unsupported_claims_hidden="pass",
        ),
        timestamp="2026-06-26T05:22:13Z",
        review_origin="human",
    )


@pytest.mark.parametrize(
    ("builder", "reviewer"),
    PACKAGE_BUILDER_PLACEHOLDER_REVIEWERS,
    ids=[builder for builder, _ in PACKAGE_BUILDER_PLACEHOLDER_REVIEWERS],
)
def test_fabricated_package_builder_review_cannot_back_a_human_review_pin(
    builder: str, reviewer: str
) -> None:
    # A ``human_review`` pin is backed by an actual ``ReviewArtifact`` carrying
    # ``review_origin="human"`` (ADR 0206 §2; acceptance #5; HELPER iter-5 review), not loose
    # scalar fields. The fabricated package-builder review (every per-language placeholder
    # reviewer, ``review_origin="package_builder"`` by model-level default) is a valid
    # ReviewArtifact but its origin is not human, so it cannot pin a rule's meaning as
    # human-reviewed.
    fabricated = ReviewArtifact(
        review_id="RVW-REQ-AUTH-001-001",
        reviewer=reviewer,
        decision="approved",
        reviewed_hashes={"requirement_ir": _VALID_HASH},
        checklist=ReviewChecklist(
            controlled_form_matches_intent="pass",
            claim_shape_matches_controlled_form="pass",
            source_spans_present="pass",
            assumptions_explicit="pass",
            bindings_justified="pass",
            evidence_level_appropriate="pass",
            unsupported_claims_hidden="pass",
        ),
        timestamp="2026-06-26T05:22:13Z",
    )
    assert fabricated.review_origin == "package_builder"
    with pytest.raises(ValidationError, match="must be backed by a real human review event"):
        PinningProvenance(
            kind="human_review",
            review_event=fabricated,
            timestamp="2026-06-26T05:22:13Z",
        )


def test_a_real_human_review_can_back_a_human_review_pin() -> None:
    # Contrast: a real human review event (review_origin="human", non-placeholder reviewer) backs a
    # ``human_review`` pin, and the pin's reference accessors are derived from that event.
    event = _real_human_review_event()
    pin = PinningProvenance(
        kind="human_review",
        review_event=event,
        timestamp="2026-06-26T05:22:13Z",
    )
    assert pin.kind == "human_review"
    assert pin.review_event is event
    assert pin.review_id == event.review_id == "RVW-REQ-AUTH-001-001"
    assert pin.reviewer == event.reviewer == "reviewer@example.org"
    assert pin.reviewed_artifact_hash == _VALID_HASH
