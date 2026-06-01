import json
from pathlib import Path

from nlreq.cli import main
from nlreq.dsl_v2 import DslV2Parser
from nlreq.impact import ImpactAnalysisArtifact
from nlreq.models import RequirementIR
from nlreq.parser import RequirementParser
from nlreq.system_checker import check_requirement_set_consistency, check_system_consistency
from nlreq.system_spec import SystemSpecRegistry
from nlreq.translator import LoweredFormalArtifact, lower_ir_v2_to_tla


DSL = (
    "For every redemption:\n"
    "when wallet is authorized\n"
    "and requested_amount <= spendable_balance\n"
    "then finalize_redemption must emit redemption_finalized within 6 hours.\n"
)


def test_system_consistency_returns_valid_for_fresh_specs_and_lowered_requirement(
    tmp_path: Path,
) -> None:
    result = check_system_consistency(
        requirement=_ir(),
        lowered=lower_ir_v2_to_tla(_ir()),
        registry=_registry(tmp_path),
        impact=_impact(),
        project_root=tmp_path,
    )

    assert result.result.status == "valid"
    assert result.result.evidence_level == "CONSISTENCY_CHECKED"


def test_system_consistency_returns_counterexample_marker(tmp_path: Path) -> None:
    result = check_system_consistency(
        requirement=_ir(),
        lowered=lower_ir_v2_to_tla(_ir()),
        registry=_registry(tmp_path, marker="\\* NLREQ_COUNTEREXAMPLE:REQ-SYS-001\n"),
        impact=_impact(),
        project_root=tmp_path,
    )

    assert result.result.status == "counterexample"
    assert result.counterexamples[0].metadata["spec_id"] == "spec:redemption"


def test_system_consistency_returns_timeout_marker(tmp_path: Path) -> None:
    result = check_system_consistency(
        requirement=_ir(),
        lowered=lower_ir_v2_to_tla(_ir()),
        registry=_registry(tmp_path, marker="\\* NLREQ_TIMEOUT\n"),
        impact=_impact(),
        project_root=tmp_path,
    )

    assert result.result.status == "timeout"


def test_system_consistency_returns_unsupported_for_stale_spec(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    data = registry.model_dump(mode="json")
    data["specs"][0]["freshness"] = "stale"

    result = check_system_consistency(
        requirement=_ir(),
        lowered=lower_ir_v2_to_tla(_ir()),
        registry=SystemSpecRegistry.model_validate(data),
        impact=_impact(),
        project_root=tmp_path,
    )

    assert result.result.status == "unsupported"


def test_system_consistency_returns_unsupported_for_refused_lowering(tmp_path: Path) -> None:
    lowered = lower_ir_v2_to_tla(_ir())
    refused = LoweredFormalArtifact.model_validate(
        lowered.model_copy(update={"status": "refused", "content": None, "content_hash": None})
        .model_dump(mode="json", exclude_none=True)
    )

    result = check_system_consistency(
        requirement=_ir(),
        lowered=refused,
        registry=_registry(tmp_path),
        impact=_impact(),
        project_root=tmp_path,
    )

    assert result.result.status == "unsupported"


def test_requirement_set_consistency_detects_opposite_predicates() -> None:
    parser = RequirementParser()
    approved = parser.parse_ir(
        "For every operation request:\n"
        "if actor is approved\n"
        "then operation must succeed.\n",
        requirement_id="REQ-APPROVED",
        title="Approved",
        claim_kind="state_precondition",
    )
    not_approved = parser.parse_ir(
        "For every operation request:\n"
        "if actor is not approved\n"
        "then operation must be rejected.\n",
        requirement_id="REQ-NOT-APPROVED",
        title="Not approved",
        claim_kind="state_precondition",
    )

    report = check_requirement_set_consistency([approved, not_approved])

    assert report.result == "contradiction"
    assert report.contradictions[0].contradiction_type == "opposite_predicate"


def test_system_consistency_cli(tmp_path: Path, capsys) -> None:
    ir = _ir()
    lowered = lower_ir_v2_to_tla(ir)
    registry = _registry(tmp_path)
    impact = _impact()
    ir_path = tmp_path / "requirement.ir.json"
    lowered_path = tmp_path / "lowered.json"
    registry_path = tmp_path / "registry.json"
    impact_path = tmp_path / "impact.json"
    out = tmp_path / "system-result.json"
    ir_path.write_text(json.dumps(ir.model_dump(mode="json"), indent=2))
    lowered_path.write_text(json.dumps(lowered.model_dump(mode="json", exclude_none=True), indent=2))
    registry_path.write_text(json.dumps(registry.model_dump(mode="json"), indent=2))
    impact_path.write_text(json.dumps(impact.model_dump(mode="json"), indent=2))

    exit_code = main(
        [
            "system-consistency-check",
            "--requirement-ir",
            str(ir_path),
            "--lowered",
            str(lowered_path),
            "--registry",
            str(registry_path),
            "--impact",
            str(impact_path),
            "--project-root",
            str(tmp_path),
            "--out",
            str(out),
        ]
    )

    output = capsys.readouterr().out

    assert exit_code == 0
    assert "System consistency result:" in output
    assert json.loads(out.read_text())["result"]["status"] == "valid"


def _ir():
    return DslV2Parser().parse_ir(DSL, requirement_id="REQ-SYS-001", title="System check")


def _impact() -> ImpactAnalysisArtifact:
    return ImpactAnalysisArtifact(
        adapter_id="python-source",
        language="python",
        input_symbols=["finalize_redemption"],
        affected_modules=["redemption"],
    )


def _registry(tmp_path: Path, *, marker: str = "") -> SystemSpecRegistry:
    specs = tmp_path / "specs"
    specs.mkdir(exist_ok=True)
    (specs / "Redemption.tla").write_text(
        "---- MODULE Redemption ----\nRedemptionInvariant == TRUE\n" + marker + "====\n"
    )
    return SystemSpecRegistry.model_validate(
        {
            "schema_version": "0.1",
            "specs": [
                {
                    "spec_id": "spec:redemption",
                    "module_ids": ["redemption"],
                    "formalism": "tla",
                    "path": "specs/Redemption.tla",
                    "version": "1",
                    "review_status": "reviewed",
                    "freshness": "fresh",
                }
            ],
        }
    )
