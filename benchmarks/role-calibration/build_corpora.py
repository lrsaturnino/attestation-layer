"""Generate the four non-drafting role-calibration corpora (scope §5, ADR 0204 §4).

Each corpus is a DISCRIMINATOR corpus (not a release bar): it mixes faithful / planted-FA /
planted-FR cases so the recorded run proves the harness discriminates — a constant-zero
instrument would pass vacuously. The live FA/FR measurement is operator-side (``benchmark-role
--run --llm-client <scheme>``); these committed corpora are the CI-safe, deterministic analog of
the drafting release corpus's recorded run.

Run ``uv run python benchmarks/role-calibration/build_corpora.py`` to regenerate the four
``<role>.corpus.json`` files. ``tests/test_role_calibration.py`` asserts each committed corpus
round-trips through this generator (no silent drift), mirroring the translation corpus contract.
"""
from __future__ import annotations

import json
from pathlib import Path

from nlreq.role_calibration import (
    ROLE_CALIBRATION_SCHEMA_VERSION,
    AuditCalibrationCase,
    AuditCalibrationCorpus,
    DecompositionCalibrationCase,
    DecompositionCalibrationCorpus,
    ExtractionCalibrationCase,
    ExtractionCalibrationCorpus,
    ImpactCalibrationCase,
    ImpactCalibrationCorpus,
)
from nlreq.audit_client import AuditVerdict

OUT_DIR = Path(__file__).resolve().parent

# Two DSL v3 controlled texts (distinct domains) reused for decomposition + audit. Each lowers to
# a FormalClaim; inverting the premise polarity yields a divergent-but-valid claim (the FA twin).
_AUTH = (
    "requirement authorization_precondition:\nscope withdrawal\n"
    "when account is not authorized\nthen withdraw must reject before settled\n"
)
_AUTH_INV = _AUTH.replace("when account is not authorized", "when account is authorized")
_PROC = (
    "requirement authorization_precondition:\nscope purchase_order\n"
    "when buyer is not authorized\nthen place_order must reject before ordered\n"
)
_PROC_INV = _PROC.replace("when buyer is not authorized", "when buyer is authorized")


def _decomposition_corpus() -> DecompositionCalibrationCorpus:
    """Decomposition: faithful re-expression matches the gold signature; an inverted premise is
    FA (a valid but divergent claim); a refuses-IR is FR (a lowerable input refused at the claim
    level). The harness marks the FR case's IR unsupported, so recorded_dsl_text is the faithful
    text and ``fault_kind`` drives the refusal."""
    cases: list[DecompositionCalibrationCase] = []
    for domain, faithful, divergent in [
        ("authorization", _AUTH, _AUTH_INV),
        ("procurement", _PROC, _PROC_INV),
    ]:
        # 2 faithful, 2 FA (divergent), 2 FR (refuses) per domain.
        for i in range(2):
            cases.append(DecompositionCalibrationCase(
                case_id=f"decomp-{domain}-faithful-{i+1}", title=f"{domain} faithful {i+1}",
                domain=domain, controlled_text=faithful, recorded_dsl_text=faithful, fault_kind="faithful",
            ))
            cases.append(DecompositionCalibrationCase(
                case_id=f"decomp-{domain}-fa-{i+1}", title=f"{domain} false-acceptance {i+1}",
                domain=domain, controlled_text=faithful, recorded_dsl_text=divergent, fault_kind="false_acceptance",
            ))
            cases.append(DecompositionCalibrationCase(
                case_id=f"decomp-{domain}-fr-{i+1}", title=f"{domain} false-refusal {i+1}",
                domain=domain, controlled_text=faithful, recorded_dsl_text=faithful, fault_kind="false_refusal",
            ))
    return DecompositionCalibrationCorpus(
        schema_version=ROLE_CALIBRATION_SCHEMA_VERSION, corpus_id="decomposition-calibration", version="0.1", cases=cases,
    )


def _audit_corpus() -> AuditCalibrationCorpus:
    """Audit: gold=passed for a faithful IR summary, gold=failed for one with an invented premise.
    Faithful: recorded verdict == gold. FA: gold=failed but recorded=passed (auditor missed the
    fault). FR: gold=passed but recorded=failed (auditor false-alarmed)."""
    passed = AuditVerdict(covers_all_clauses=True, invented_premises=[], verdict="passed")
    failed = AuditVerdict(covers_all_clauses=False, invented_premises=["invented-premise-not-in-text"], verdict="failed")
    cases: list[AuditCalibrationCase] = []
    for domain, controlled in [("authorization", _AUTH), ("procurement", _PROC)]:
        for i in range(2):
            cases.append(AuditCalibrationCase(
                case_id=f"audit-{domain}-faithful-{i+1}", title=f"{domain} faithful {i+1}",
                domain=domain, controlled_text=controlled, ir_summary="faithful IR summary",
                gold_verdict="passed", recorded_verdict=passed, fault_kind="faithful",
            ))
            cases.append(AuditCalibrationCase(
                case_id=f"audit-{domain}-fa-{i+1}", title=f"{domain} missed-fault {i+1}",
                domain=domain, controlled_text=controlled, ir_summary="IR with an invented premise",
                gold_verdict="failed", recorded_verdict=passed, fault_kind="false_acceptance",
            ))
            cases.append(AuditCalibrationCase(
                case_id=f"audit-{domain}-fr-{i+1}", title=f"{domain} false-alarm {i+1}",
                domain=domain, controlled_text=controlled, ir_summary="faithful IR summary",
                gold_verdict="passed", recorded_verdict=failed, fault_kind="false_refusal",
            ))
    return AuditCalibrationCorpus(
        schema_version=ROLE_CALIBRATION_SCHEMA_VERSION, corpus_id="audit-calibration", version="0.1", cases=cases,
    )


def _impact_corpus() -> ImpactCalibrationCorpus:
    """Impact: gold = authoritative affected set. Faithful: estimate == gold. FA: estimate
    over-claims a module not in gold. FR: estimate misses a module in gold."""
    cases: list[ImpactCalibrationCase] = []
    domains = [
        ("payments", "The payment service must reject refunds over the daily limit.",
         ["refund"], ["payments", "ledger", "notify", "audit"], ["payments", "ledger"]),
        ("inventory", "The inventory service must block stock moves below zero.",
         ["move"], ["inventory", "warehouse", "notify", "audit"], ["inventory", "warehouse"]),
    ]
    for domain, prose, symbols, candidates, gold in domains:
        extra = [m for m in candidates if m not in gold][0]  # a module NOT in gold (over-claim)
        missing = gold[1]  # a module IN gold to drop (under-claim)
        for i in range(2):
            cases.append(ImpactCalibrationCase(
                case_id=f"impact-{domain}-faithful-{i+1}", title=f"{domain} faithful {i+1}",
                domain=domain, prose=prose, symbols=symbols, candidate_modules=candidates,
                gold_affected_modules=gold, recorded_estimate=json.dumps(gold), fault_kind="faithful",
            ))
            cases.append(ImpactCalibrationCase(
                case_id=f"impact-{domain}-fa-{i+1}", title=f"{domain} over-claim {i+1}",
                domain=domain, prose=prose, symbols=symbols, candidate_modules=candidates,
                gold_affected_modules=gold, recorded_estimate=json.dumps(sorted(set(gold) | {extra})),
                fault_kind="false_acceptance",
            ))
            cases.append(ImpactCalibrationCase(
                case_id=f"impact-{domain}-fr-{i+1}", title=f"{domain} under-claim {i+1}",
                domain=domain, prose=prose, symbols=symbols, candidate_modules=candidates,
                gold_affected_modules=gold, recorded_estimate=json.dumps([m for m in gold if m != missing]),
                fault_kind="false_refusal",
            ))
    return ImpactCalibrationCorpus(
        schema_version=ROLE_CALIBRATION_SCHEMA_VERSION, corpus_id="impact-calibration", version="0.1", cases=cases,
    )


def _extraction_corpus() -> ExtractionCalibrationCorpus:
    """Extraction: gold = correct invariant set. Faithful: proposed == gold. FA: proposed adds an
    invented invariant. FR: proposed misses a gold invariant."""
    cases: list[ExtractionCalibrationCase] = []
    domains = [
        ("payments", "payments", "func refund() { if amount > LIMIT { reject } }",
         [{"name": "S_refund_limit", "tla": "refund_amount <= LIMIT"}]),
        ("inventory", "inventory", "func move() { if stock < 0 { block } }",
         [{"name": "S_nonnegative_stock", "tla": "stock >= 0"}]),
    ]
    for domain, module, code, gold in domains:
        invented = {"name": f"S_invented_{domain}", "tla": "false"}
        for i in range(2):
            cases.append(ExtractionCalibrationCase(
                case_id=f"extract-{domain}-faithful-{i+1}", title=f"{domain} faithful {i+1}",
                domain=domain, module_id=module, code_presentation=code, language="go",
                gold_invariants=gold, recorded_estimate=json.dumps({"invariants": gold}),
                fault_kind="faithful",
            ))
            cases.append(ExtractionCalibrationCase(
                case_id=f"extract-{domain}-fa-{i+1}", title=f"{domain} invented {i+1}",
                domain=domain, module_id=module, code_presentation=code, language="go",
                gold_invariants=gold, recorded_estimate=json.dumps({"invariants": gold + [invented]}),
                fault_kind="false_acceptance",
            ))
            cases.append(ExtractionCalibrationCase(
                case_id=f"extract-{domain}-fr-{i+1}", title=f"{domain} missed {i+1}",
                domain=domain, module_id=module, code_presentation=code, language="go",
                gold_invariants=gold, recorded_estimate=json.dumps({"invariants": []}),
                fault_kind="false_refusal",
            ))
    return ExtractionCalibrationCorpus(
        schema_version=ROLE_CALIBRATION_SCHEMA_VERSION, corpus_id="extraction-calibration", version="0.1", cases=cases,
    )


def build_all() -> dict[str, object]:
    return {
        "decomposition": _decomposition_corpus(),
        "audit": _audit_corpus(),
        "impact": _impact_corpus(),
        "extraction": _extraction_corpus(),
    }


def main() -> int:
    for role, corpus in build_all().items():
        path = OUT_DIR / f"{role}.corpus.json"
        path.write_text(json.dumps(corpus.model_dump(mode="json"), indent=2, sort_keys=True) + "\n")
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
