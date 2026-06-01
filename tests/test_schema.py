import subprocess
import sys
from pathlib import Path


def test_schema_generation_has_no_drift() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/check_schema_drift.py"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_auxiliary_artifact_schemas_are_committed() -> None:
    schema_dir = Path("schemas")

    assert (schema_dir / "adapter-registry.schema.json").exists()
    assert (schema_dir / "agnostic-wedge-report.schema.json").exists()
    assert (schema_dir / "assumptions.schema.json").exists()
    assert (schema_dir / "backend-agreement-report.schema.json").exists()
    assert (schema_dir / "backend-results.schema.json").exists()
    assert (schema_dir / "benchmark-corpus.schema.json").exists()
    assert (schema_dir / "benchmark-results.schema.json").exists()
    assert (schema_dir / "benchmark-run-report.schema.json").exists()
    assert (schema_dir / "bindings.schema.json").exists()
    assert (schema_dir / "budgeted-verification-outcome.schema.json").exists()
    assert (schema_dir / "command-checks.schema.json").exists()
    assert (schema_dir / "command-results.schema.json").exists()
    assert (schema_dir / "controlled-draft.schema.json").exists()
    assert (schema_dir / "closure-gate-report.schema.json").exists()
    assert (schema_dir / "code-spec-manifest.schema.json").exists()
    assert (schema_dir / "counterexamples.schema.json").exists()
    assert (schema_dir / "delta-report.schema.json").exists()
    assert (schema_dir / "end-to-end-requirement-gate.schema.json").exists()
    assert (schema_dir / "evidence-producer-mapping.schema.json").exists()
    assert (schema_dir / "evidence-producer-validation.schema.json").exists()
    assert (schema_dir / "formal-backend-request.schema.json").exists()
    assert (schema_dir / "formal-backend-response.schema.json").exists()
    assert (schema_dir / "gate-policy.schema.json").exists()
    assert (schema_dir / "impact-analysis.schema.json").exists()
    assert (schema_dir / "impact-analysis-v2.schema.json").exists()
    assert (schema_dir / "generated-tests.schema.json").exists()
    assert (schema_dir / "normalized-traces.schema.json").exists()
    assert (schema_dir / "proof-dispatch-plan.schema.json").exists()
    assert (schema_dir / "proof-object.schema.json").exists()
    assert (schema_dir / "requirement-ir-0.2.schema.json").exists()
    assert (schema_dir / "requirement-ir-migration.schema.json").exists()
    assert (schema_dir / "requirement-set-consistency.schema.json").exists()
    assert (schema_dir / "requirement-self-consistency.schema.json").exists()
    assert (schema_dir / "review.schema.json").exists()
    assert (schema_dir / "routing-policy.schema.json").exists()
    assert (schema_dir / "source-call-graph.schema.json").exists()
    assert (schema_dir / "source-code-presentation.schema.json").exists()
    assert (schema_dir / "source-manifest.schema.json").exists()
    assert (schema_dir / "source-symbol-resolution.schema.json").exists()
    assert (schema_dir / "spec-drift-report.schema.json").exists()
    assert (schema_dir / "spec-extraction-workbench.schema.json").exists()
    assert (schema_dir / "spec-coverage-report.schema.json").exists()
    assert (schema_dir / "system-spec-registry.schema.json").exists()
    assert (schema_dir / "system-spec-registry-report.schema.json").exists()
    assert (schema_dir / "system-consistency-result.schema.json").exists()
    assert (schema_dir / "trace-replay-report.schema.json").exists()
    assert (schema_dir / "trace-validation-results.schema.json").exists()
    assert (schema_dir / "trace-alignment-report.schema.json").exists()
    assert (schema_dir / "translation-agreement-input.schema.json").exists()
    assert (schema_dir / "translation-agreement-report.schema.json").exists()
    assert (schema_dir / "lowered-formal-artifact.schema.json").exists()
    assert (schema_dir / "model-checker-run.schema.json").exists()
    assert (schema_dir / "model-checker-runs.schema.json").exists()
    assert (schema_dir / "tla-model-config.schema.json").exists()
    assert (schema_dir / "tla-results.schema.json").exists()
    assert (schema_dir / "verification-budget-policy.schema.json").exists()
    assert (schema_dir / "verification-budget-report.schema.json").exists()
    assert (schema_dir / "verification-tasks.schema.json").exists()
    assert (schema_dir / "waiver.schema.json").exists()
