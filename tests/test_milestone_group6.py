import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from nlreq.artifact_store import (
    ArtifactStoreManifest,
    export_replay_bundle,
    lookup_artifact,
    put_artifact,
)
from nlreq.benchmark_corpus import BenchmarkCaseResult, BenchmarkCorpus
from nlreq.benchmark_reporting import build_benchmark_evaluation_report
from nlreq.ci_pr_gate import build_ci_pr_gate_report, ci_pr_gate_markdown
from nlreq.end_to_end_gate import EndToEndGateBlocker, EndToEndRequirementGateReport
from nlreq.gate import GatePolicy, GatePolicyWaiverRules, GateWaiver
from nlreq.models import SourceSpan
from nlreq.policy_governance import build_waiver_audit_report
from nlreq.signed_evidence import (
    ProducerKey,
    ProducerKeyRegistry,
    sign_evidence_payload,
    verify_signed_evidence,
)
from nlreq.verification_cache import (
    VerificationCacheIndex,
    build_verification_cache_key,
    cache_key_hash,
    lookup_cache,
    record_cache_artifact,
)


def test_phase73_artifact_store_retains_and_exports_hash_linked_records(tmp_path: Path) -> None:
    source = tmp_path / "counterexample.json"
    source.write_text(json.dumps({"backend": "apalache", "status": "counterexample"}))
    store_root = tmp_path / "store"

    record = put_artifact(
        store_root=store_root,
        source_path=source,
        logical_name="raw-counterexample",
        raw=True,
    )
    manifest = ArtifactStoreManifest(store_id="local", records=[record])

    lookup = lookup_artifact(
        store_root=store_root,
        manifest=manifest,
        artifact_hash=record.artifact_hash,
    )
    assert lookup.status == "found"
    assert lookup.record is not None
    assert lookup.record.raw is True

    missing = lookup_artifact(
        store_root=store_root,
        manifest=manifest,
        artifact_hash="sha256:" + "0" * 64,
    )
    assert missing.status == "missing"

    bundle = export_replay_bundle(
        store_root=store_root,
        manifest=manifest,
        bundle_root=tmp_path / "bundle",
        bundle_id="bundle-1",
    )
    assert [item.artifact_hash for item in bundle.records] == [record.artifact_hash]


def test_phase74_signed_evidence_detects_tampering_and_untrusted_keys() -> None:
    payload = {"requirement_id": "REQ-G6-SIGN-001", "decision": "accepted"}
    envelope = sign_evidence_payload(
        payload=payload,
        producer_id="producer.apalache",
        key_id="local-key",
        secret="correct horse battery staple",
        envelope_id="env-1",
    )
    registry = ProducerKeyRegistry(
        keys=[
            ProducerKey(
                key_id="local-key",
                producer_id="producer.apalache",
                trusted_for_high_assurance=True,
            )
        ]
    )

    valid = verify_signed_evidence(
        envelope=envelope,
        registry=registry,
        secrets_by_key_id={"local-key": "correct horse battery staple"},
        require_high_assurance_trust=True,
    )
    assert valid.result == "valid"

    tampered = envelope.model_copy(
        update={"payload": {"requirement_id": "REQ-G6-SIGN-001", "decision": "refused"}}
    )
    invalid = verify_signed_evidence(
        envelope=tampered,
        registry=registry,
        secrets_by_key_id={"local-key": "correct horse battery staple"},
    )
    assert invalid.result == "invalid"
    assert "payload hash does not match envelope" in invalid.reasons

    untrusted_registry = ProducerKeyRegistry(
        keys=[ProducerKey(key_id="local-key", producer_id="producer.apalache")]
    )
    untrusted = verify_signed_evidence(
        envelope=envelope,
        registry=untrusted_registry,
        secrets_by_key_id={"local-key": "correct horse battery staple"},
        require_high_assurance_trust=True,
    )
    assert untrusted.result == "untrusted_key"


def test_phase75_ci_pr_gate_hard_blocks_but_report_only_reports() -> None:
    gate = EndToEndRequirementGateReport(
        requirement_id="REQ-G6-CI-001",
        decision="unknown",
        downstream_action="merge",
        downstream_action_allowed=False,
        proof_status="open",
        closure_result="blocked",
        blockers=[
            EndToEndGateBlocker(
                stage="system_consistency",
                status="timeout",
                message="system consistency timed out",
                source_spans=[
                    SourceSpan(
                        document="requirement.nlreq3",
                        start_char=0,
                        end_char=10,
                        text="requirement",
                    )
                ],
            )
        ],
    )

    report_only = build_ci_pr_gate_report(gate, mode="report_only")
    hard_gate = build_ci_pr_gate_report(gate, mode="hard_gate")

    assert report_only.result == "reported"
    assert hard_gate.result == "blocked"
    assert hard_gate.next_actions == ["system consistency timed out"]
    assert "Result: `blocked`" in ci_pr_gate_markdown(hard_gate)


def test_phase76_benchmark_evaluation_tracks_false_closure_budget() -> None:
    corpus = BenchmarkCorpus.model_validate(
        {
            "corpus_id": "group-f",
            "version": "0.1",
            "cases": [
                {
                    "case_id": "accepted",
                    "title": "Accepted",
                    "description": "Known positive case.",
                    "tags": ["positive-closure"],
                    "expected": {"decision": "accepted"},
                },
                {
                    "case_id": "trace-mismatch",
                    "title": "Trace mismatch",
                    "description": "Must refuse when traces contradict the requirement.",
                    "tags": ["trace", "false-closure-risk"],
                    "expected": {"decision": "refused", "counterexample_expected": True},
                },
            ],
        }
    )
    results = [
        BenchmarkCaseResult(case_id="accepted", decision="accepted", runtime_ms=10),
        BenchmarkCaseResult(
            case_id="trace-mismatch",
            decision="accepted",
            runtime_ms=20,
            counterexample_count=0,
        ),
    ]

    report = build_benchmark_evaluation_report(
        corpus,
        results,
        false_closure_budget=0.0,
    )

    assert report.result == "failed"
    assert report.category_counts["trace"] == 1
    false_closure = next(metric for metric in report.metrics if metric.name == "false_closure_rate")
    assert false_closure.value == pytest.approx(0.5)
    assert false_closure.passed is False


def test_phase77_cache_keys_invalidate_on_tool_versions_and_policy_hash() -> None:
    base_key = build_verification_cache_key(
        stage="formal_backend",
        input_hashes={"ir": "sha256:ir"},
        tool_versions={"apalache": "0.47.0"},
        policy_hash="sha256:policy-a",
    )
    changed_tool = build_verification_cache_key(
        stage="formal_backend",
        input_hashes={"ir": "sha256:ir"},
        tool_versions={"apalache": "0.48.0"},
        policy_hash="sha256:policy-a",
    )
    changed_policy = build_verification_cache_key(
        stage="formal_backend",
        input_hashes={"ir": "sha256:ir"},
        tool_versions={"apalache": "0.47.0"},
        policy_hash="sha256:policy-b",
    )

    index = record_cache_artifact(
        VerificationCacheIndex(),
        base_key,
        artifact_hash="sha256:artifact",
        metadata={"evidence_level": "BOUNDED_CHECKED"},
    )

    assert lookup_cache(index, base_key).status == "hit"
    assert lookup_cache(index, changed_tool).status == "miss"
    assert lookup_cache(index, changed_policy).status == "miss"
    assert cache_key_hash(base_key) != cache_key_hash(changed_tool)


def test_phase78_waiver_audit_enforces_policy_expiration_duration_and_reviewed_hashes() -> None:
    now = datetime(2026, 6, 2, tzinfo=timezone.utc)
    policy = GatePolicy(
        policy_id="group-f-policy",
        waivers=GatePolicyWaiverRules(
            allow_waivers=True,
            max_duration_days=7,
            require_reviewed_hashes=True,
        ),
    )

    active = GateWaiver(
        waiver_id="active",
        requirement_ids=["REQ-G6-WAIVER-001"],
        reviewer="reviewer@example.invalid",
        reason="temporary staged rollout",
        expires_at=now + timedelta(days=3),
        reviewed_hashes={"gate-report": "sha256:reviewed"},
        linked_issue="https://example.invalid/issues/1",
    )
    too_long = active.model_copy(
        update={"waiver_id": "too-long", "expires_at": now + timedelta(days=30)}
    )
    missing_hashes = active.model_copy(update={"waiver_id": "missing-hashes", "reviewed_hashes": {}})
    unsafe = active.model_copy(update={"waiver_id": "unsafe", "may_satisfy_hard_gate": False})
    expired = active.model_copy(update={"waiver_id": "expired", "expires_at": now - timedelta(days=1)})

    report = build_waiver_audit_report(
        policy=policy,
        waivers=[active, too_long, missing_hashes, unsafe, expired],
        now=now,
    )

    findings = {finding.waiver_id: finding for finding in report.findings}
    assert report.result == "blocked"
    assert findings["active"].status == "active"
    assert findings["too-long"].status == "out_of_policy"
    assert findings["missing-hashes"].status == "out_of_policy"
    assert findings["unsafe"].status == "unsafe"
    assert findings["expired"].status == "expired"
