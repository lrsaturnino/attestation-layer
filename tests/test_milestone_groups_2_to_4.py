import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

from nlreq.adapter_certification import certify_adapter_v2
from nlreq.artifact_store import ArtifactStoreManifest, lookup_artifact, put_artifact
from nlreq.benchmark_corpus import BenchmarkCaseResult, BenchmarkCorpus
from nlreq.benchmark_v2 import build_benchmark_v2_report
from nlreq.conclusion_certification import build_conclusion_certification_report
from nlreq.dsl_v2 import DslV2Parser
from nlreq.formal_backend import (
    ApalacheBackend,
    FormalBackendExecution,
    TlcProductionBackend,
    build_formal_backend_request,
    check_formal_backend,
    existing_formal_boundaries,
)
from nlreq.gate import GatePolicy, GatePolicyWaiverRules, GateWaiver
from nlreq.jsonutil import write_json
from nlreq.models import NormalizedTrace, NormalizedTraceArtifact, SymbolRef, TraceEvent
from nlreq.policy_v2 import build_waiver_audit_report
from nlreq.production_source_adapters import SoliditySourceAdapter
from nlreq.public_sdk import build_default_public_documentation_index
from nlreq.reference_demo import ReferenceDemoManifest, build_reference_demo_report
from nlreq.runtime_trace_sdk import (
    TraceExtractionRequest,
    TraceProducerRegistration,
    TraceProducerRegistry,
    producer_from_registry,
)
from nlreq.signed_evidence import (
    ProducerKey,
    ProducerKeyRegistry,
    sign_evidence_payload,
    verify_signed_evidence,
)
from nlreq.source_adapter import SourceManifest
from nlreq.spec_drift import CodeSpecManifest
from nlreq.spec_freshness import (
    build_spec_freshness_lockfile,
    validate_spec_freshness_lockfile,
)
from nlreq.system_spec import SystemSpecRegistry
from nlreq.threat_model import build_default_threat_model
from nlreq.tla_projection_v2 import build_tla_projection_v2_report
from nlreq.trace_normalization_v2 import RawTraceArtifact, normalize_raw_traces_v2


def test_production_backends_are_registered_and_missing_tool_is_unsupported(tmp_path: Path) -> None:
    ir = _dsl_v2_ir()

    boundaries = {boundary["backend_id"] for boundary in existing_formal_boundaries()}
    assert {"apalache", "tlc"}.issubset(boundaries)

    request = build_formal_backend_request(
        ir,
        backend_id=ApalacheBackend.backend_id,
        execution=FormalBackendExecution(
            checker_id="apalache",
            command=["definitely-missing-nlreq-apalache", "check", "{module}"],
            artifact_dir=tmp_path.as_posix(),
        ),
    )
    response = check_formal_backend(request)

    assert response.result.status == "unsupported"
    assert response.result.evidence_level is None
    assert response.result.details["tool_missing"] is True
    assert (tmp_path / "Req_REQ_DSL_V2_001.tla").is_file()


def test_tlc_production_backend_accepts_custom_checker_command(tmp_path: Path) -> None:
    request = build_formal_backend_request(
        _dsl_v2_ir(),
        backend_id=TlcProductionBackend.backend_id,
        execution=FormalBackendExecution(
            checker_id="custom-tlc",
            command=["python", "-c", "print('verification successful')"],
            artifact_dir=tmp_path.as_posix(),
        ),
    )

    response = check_formal_backend(request)

    assert response.result.status == "valid"
    assert response.result.evidence_level.value == "BOUNDED_CHECKED"


def test_tla_projection_v2_records_bounds_and_refuses_unsupported_fragments() -> None:
    report = build_tla_projection_v2_report(_dsl_v2_ir())

    assert report.result == "projected"
    assert report.lowered.status == "lowered"
    assert report.semantic_rules


def test_spec_freshness_lockfile_blocks_changed_source(tmp_path: Path) -> None:
    source_hash = _write(tmp_path / "auth.py", "def authorize(): return True\n")
    spec_hash = _write(tmp_path / "specs" / "Auth.tla", "---- MODULE Auth ----\n====\n")
    manifest = CodeSpecManifest.model_validate(
        {
            "schema_version": "0.1",
            "entries": [
                {
                    "module_id": "auth",
                    "source_paths": ["auth.py"],
                    "spec_ids": ["spec:auth"],
                    "recorded_source_hashes": {"auth.py": source_hash},
                }
            ],
        }
    )
    registry = _registry(spec_hash)
    lockfile = build_spec_freshness_lockfile(
        manifest=manifest,
        registry=registry,
        project_root=tmp_path,
    )
    (tmp_path / "auth.py").write_text("def authorize(): return False\n")

    report = validate_spec_freshness_lockfile(
        manifest=manifest,
        registry=registry,
        lockfile=lockfile,
        project_root=tmp_path,
    )

    assert report.result == "blocked"
    assert report.statuses[0].changed_sources == ["auth.py"]


def test_solidity_adapter_certification_resolves_static_symbols(tmp_path: Path) -> None:
    (tmp_path / "Bridge.sol").write_text(
        "contract Bridge {\n"
        "  event Redeemed(address user);\n"
        "  function requestRedemption() public { emit Redeemed(msg.sender); }\n"
        "}\n"
    )
    manifest = SourceManifest.model_validate(
        {
            "schema_version": "0.1",
            "adapter": "solidity-source",
            "language": "solidity",
            "runtime": "evm",
            "modules": [
                {
                    "module_id": "bridge",
                    "path": "Bridge.sol",
                    "symbols": ["requestRedemption", "Redeemed"],
                }
            ],
        }
    )
    adapter = SoliditySourceAdapter(project_root=tmp_path)

    report = certify_adapter_v2(
        adapter,
        manifest,
        symbol_refs=[SymbolRef(name="requestRedemption")],
    )

    assert report.result == "certified"
    assert report.level == "static_resolution"
    assert report.resolved_symbols == 1


def test_trace_normalization_and_registered_local_extraction(tmp_path: Path) -> None:
    raw = RawTraceArtifact.model_validate(
        {
            "schema_version": "0.1",
            "traces": [
                {
                    "trace_id": "trace-1",
                    "adapter_id": "go-source",
                    "language": "go",
                    "runtime": "go",
                    "events": [
                        {
                            "event_id": "event-1",
                            "timestamp": 1,
                            "action": "Redeem",
                            "metadata": {"raw_span": "runtime-specific"},
                        }
                    ],
                }
            ],
        }
    )

    normalized_report = normalize_raw_traces_v2(raw)
    trace_path = tmp_path / "traces.json"
    write_json(trace_path, normalized_report.normalized)
    registry = TraceProducerRegistry(
        producers=[
            TraceProducerRegistration(
                producer_id="go-json",
                adapter_id="go-source",
                language="go",
                runtime="go",
                produces_normalized_schema="0.1",
            )
        ]
    )
    result = producer_from_registry(registry, "go-json").extract(
        TraceExtractionRequest(producer_id="go-json", trace_source="traces.json"),
        project_root=tmp_path,
    )

    assert normalized_report.result == "lossy_normalized"
    assert normalized_report.loss_records[0].field == "raw_span"
    assert result.status == "extracted"
    assert result.traces.root[0].adapter_id == "go-source"


def test_artifact_store_lookup_and_signed_evidence_verification(tmp_path: Path) -> None:
    payload_path = tmp_path / "evidence.json"
    write_json(payload_path, {"status": "valid"})
    record = put_artifact(
        store_root=tmp_path / "store",
        source_path=payload_path,
        logical_name="evidence",
        normalized=True,
    )
    manifest = ArtifactStoreManifest(store_id="local", records=[record])

    lookup = lookup_artifact(
        store_root=tmp_path / "store",
        manifest=manifest,
        artifact_hash=record.artifact_hash,
    )
    envelope = sign_evidence_payload(
        payload={"status": "valid"},
        producer_id="apalache",
        key_id="key-1",
        secret="secret",
        envelope_id="env-1",
    )
    verification = verify_signed_evidence(
        envelope=envelope,
        registry=ProducerKeyRegistry(
            keys=[
                ProducerKey(
                    key_id="key-1",
                    producer_id="apalache",
                    trusted_for_high_assurance=True,
                )
            ]
        ),
        secrets_by_key_id={"key-1": "secret"},
        require_high_assurance_trust=True,
    )

    assert lookup.status == "found"
    assert verification.result == "valid"


def test_benchmark_v2_waiver_audit_and_conclusion_certification() -> None:
    corpus = BenchmarkCorpus.model_validate(
        {
            "schema_version": "0.1",
            "corpus_id": "public-v2",
            "version": "2",
            "cases": [
                {
                    "case_id": "case-1",
                    "title": "Accepted",
                    "description": "accepted case",
                    "tags": ["accepted"],
                    "expected": {"decision": "accepted"},
                }
            ],
        }
    )
    benchmark = build_benchmark_v2_report(
        corpus,
        [BenchmarkCaseResult(case_id="case-1", decision="accepted")],
    )
    policy = GatePolicy(
        policy_id="policy",
        waivers=GatePolicyWaiverRules(allow_waivers=True),
    )
    waiver = GateWaiver(
        waiver_id="waiver-1",
        requirement_ids=["REQ-1"],
        reviewer="reviewer",
        reason="staged rollout",
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        linked_issue="ISSUE-1",
    )
    waiver_report = build_waiver_audit_report(policy=policy, waivers=[waiver])
    threat_model = build_default_threat_model()
    demo_manifest = ReferenceDemoManifest(
        demo_id="demo",
        title="Demo",
        source_root="demo",
        requirements=[
            ReferenceDemoRequirementLike("REQ-A", "accepted"),
            ReferenceDemoRequirementLike("REQ-R", "refused"),
        ],
    )
    demo = build_reference_demo_report(
        demo_manifest,
        existing_paths={"demo", "requirements/REQ-A.nlreq3", "requirements/REQ-R.nlreq3"},
    )
    docs = build_default_public_documentation_index()
    certification = build_conclusion_certification_report(
        release_id="conclusion-0.1",
        benchmark=benchmark,
        threat_model=threat_model,
        demo=demo,
        docs=docs,
        schemas_frozen=True,
    )

    assert benchmark.result == "passed"
    assert waiver_report.result == "passed"
    assert threat_model.result == "complete"
    assert certification.result == "certified"


def ReferenceDemoRequirementLike(requirement_id: str, decision: str) -> dict[str, str]:
    return {
        "requirement_id": requirement_id,
        "expected_decision": decision,
        "controlled_text_path": f"requirements/{requirement_id}.nlreq3",
    }


def _dsl_v2_ir():
    return DslV2Parser().parse_ir(
        (
            "For every redemption:\n"
            "when wallet is authorized\n"
            "and requested_amount <= spendable_balance\n"
            "then finalize_redemption must emit redeemed within 5 blocks.\n"
        ),
        requirement_id="REQ-DSL-V2-001",
        title="Redemption emits event within bound",
    )


def _registry(spec_hash: str) -> SystemSpecRegistry:
    return SystemSpecRegistry.model_validate(
        {
            "schema_version": "0.1",
            "specs": [
                {
                    "spec_id": "spec:auth",
                    "module_ids": ["auth"],
                    "formalism": "tla",
                    "path": "specs/Auth.tla",
                    "version": "1",
                    "review_status": "reviewed",
                    "freshness": "fresh",
                    "recorded_hash": spec_hash,
                }
            ],
        }
    )


def _write(path: Path, content: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
