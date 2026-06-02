from nlreq.benchmark_corpus import BenchmarkCaseResult, BenchmarkCorpus
from nlreq.benchmark_reporting import build_benchmark_evaluation_report
from nlreq.conclusion_certification import build_conclusion_certification_report
from nlreq.public_sdk import (
    build_default_public_documentation_index,
    validate_public_documentation_index,
)
from nlreq.reference_demo import ReferenceDemoManifest, build_reference_demo_report
from nlreq.threat_model import (
    REQUIRED_TCB_CATEGORIES,
    REQUIRED_THREAT_KINDS,
    build_default_threat_model,
    threat_model_release_findings,
)


def test_phase79_threat_model_has_complete_release_tcb_and_benchmark_threats() -> None:
    report = build_default_threat_model()

    assert report.result == "complete"
    assert threat_model_release_findings(report) == []
    assert set(REQUIRED_TCB_CATEGORIES).issubset({component.category for component in report.tcb})
    assert set(REQUIRED_THREAT_KINDS).issubset({scenario.threat for scenario in report.scenarios})
    assert set(REQUIRED_THREAT_KINDS).issubset(
        {scenario.threat for scenario in report.scenarios if scenario.benchmark_required}
    )

    broken = report.model_copy(update={"tcb": report.tcb[:-1]})

    assert any("missing TCB categories" in finding for finding in threat_model_release_findings(broken))


def test_phase80_reference_demo_checks_artifacts_outcomes_and_commands() -> None:
    manifest = _reference_demo_manifest()
    existing_paths = {
        "demo",
        "demo/specs/Auth.tla",
        "demo/traces/auth.json",
        "requirements/REQ-A.nlreq3",
        "requirements/REQ-R.nlreq3",
        "reports/REQ-A.gate.json",
        "reports/REQ-R.gate.json",
    }

    good = build_reference_demo_report(
        manifest,
        existing_paths=existing_paths,
        actual_decisions_by_requirement={"REQ-A": "accepted", "REQ-R": "refused"},
    )
    mismatched = build_reference_demo_report(
        manifest,
        existing_paths=existing_paths,
        actual_decisions_by_requirement={"REQ-A": "accepted", "REQ-R": "accepted"},
    )
    missing_artifact = build_reference_demo_report(
        manifest,
        existing_paths=existing_paths - {"demo/traces/auth.json"},
        actual_decisions_by_requirement={"REQ-A": "accepted", "REQ-R": "refused"},
    )

    assert good.result == "reproducible"
    assert good.has_accept_and_refuse is True
    assert good.command_count == 1
    assert mismatched.result == "blocked"
    assert mismatched.decision_mismatches == ["REQ-R"]
    assert missing_artifact.result == "blocked"
    assert missing_artifact.missing_artifacts == ["demo/traces/auth.json"]


def test_phase81_public_docs_index_validates_paths_schemas_and_audiences() -> None:
    index = build_default_public_documentation_index(version="0.1")
    existing_paths = {doc.path for doc in index.docs} | {example.path for example in index.examples}
    existing_schemas = {schema_ref for doc in index.docs for schema_ref in doc.schema_refs}

    report = validate_public_documentation_index(
        index,
        existing_paths=existing_paths,
        existing_schemas=existing_schemas,
    )
    missing = validate_public_documentation_index(
        index,
        existing_paths=existing_paths - {"docs/operator-guide.md"},
        existing_schemas=existing_schemas - {"ci-pr-gate-report.schema.json"},
    )

    assert report.result == "passed"
    assert report.checked_docs == 4
    assert report.checked_examples == 2
    assert missing.result == "blocked"
    assert missing.missing_docs == ["docs/operator-guide.md"]
    assert missing.missing_schema_refs == ["operator-guide:ci-pr-gate-report.schema.json"]


def test_phase82_conclusion_certification_passes_and_blocks_release_inputs() -> None:
    benchmark = _passing_benchmark()
    threat_model = build_default_threat_model()
    demo = build_reference_demo_report(
        _reference_demo_manifest(),
        existing_paths={
            "demo",
            "demo/specs/Auth.tla",
            "demo/traces/auth.json",
            "requirements/REQ-A.nlreq3",
            "requirements/REQ-R.nlreq3",
            "reports/REQ-A.gate.json",
            "reports/REQ-R.gate.json",
        },
        actual_decisions_by_requirement={"REQ-A": "accepted", "REQ-R": "refused"},
    )
    docs = build_default_public_documentation_index()

    certified = build_conclusion_certification_report(
        release_id="conclusion-0.1",
        benchmark=benchmark,
        threat_model=threat_model,
        demo=demo,
        docs=docs,
        schemas_frozen=True,
    )
    incomplete_threat_model = threat_model.model_copy(update={"tcb": threat_model.tcb[:-1]})
    blocked = build_conclusion_certification_report(
        release_id="conclusion-0.1",
        benchmark=benchmark,
        threat_model=incomplete_threat_model,
        demo=demo,
        docs=docs,
        schemas_frozen=False,
    )

    assert certified.result == "certified"
    assert certified.blocking_findings == []
    assert blocked.result == "blocked"
    assert any(finding.startswith("threat-model:") for finding in blocked.blocking_findings)
    assert "schema-freeze: schema freeze evidence was not provided" in blocked.blocking_findings


def _passing_benchmark():
    corpus = BenchmarkCorpus.model_validate(
        {
            "schema_version": "0.1",
            "corpus_id": "public-release",
            "version": "2",
            "cases": [
                {
                    "case_id": "accepted",
                    "title": "Accepted",
                    "description": "accepted case",
                    "tags": ["positive-closure"],
                    "expected": {"decision": "accepted"},
                },
                {
                    "case_id": "refused",
                    "title": "Refused",
                    "description": "refused case",
                    "tags": ["false-closure-risk"],
                    "expected": {"decision": "refused"},
                },
            ],
        }
    )
    return build_benchmark_evaluation_report(
        corpus,
        [
            BenchmarkCaseResult(case_id="accepted", decision="accepted"),
            BenchmarkCaseResult(case_id="refused", decision="refused"),
        ],
    )


def _reference_demo_manifest() -> ReferenceDemoManifest:
    return ReferenceDemoManifest.model_validate(
        {
            "demo_id": "demo",
            "title": "Reference Demo",
            "source_root": "demo",
            "system_specs": ["demo/specs/Auth.tla"],
            "trace_artifacts": ["demo/traces/auth.json"],
            "commands": [["nlreq", "requirement-gate", "requirements/REQ-A.nlreq3"]],
            "requirements": [
                {
                    "requirement_id": "REQ-A",
                    "expected_decision": "accepted",
                    "controlled_text_path": "requirements/REQ-A.nlreq3",
                    "expected_report_path": "reports/REQ-A.gate.json",
                },
                {
                    "requirement_id": "REQ-R",
                    "expected_decision": "refused",
                    "controlled_text_path": "requirements/REQ-R.nlreq3",
                    "expected_report_path": "reports/REQ-R.gate.json",
                },
            ],
            "reproducibility_notes": ["Use the checked-in schema set and local fixtures."],
        }
    )
