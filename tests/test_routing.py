import json
from pathlib import Path

from nlreq.cli import main
from nlreq.jsonutil import read_json, write_json
from nlreq.package import build_package
from nlreq.routing import (
    AdapterRegistryArtifact,
    RoutingPolicyArtifact,
    build_routing_report,
    routing_report_markdown,
)


FIXTURES = Path(__file__).parent / "fixtures" / "requirements"


def test_routing_report_selects_matching_gateable_adapter(tmp_path: Path) -> None:
    package_root = _package_root(tmp_path, requirement_id="REQ-AUTH-001")

    report = build_routing_report(
        package_root,
        registry=_registry(),
        policy=_policy(),
        changed_paths=["src/auth.py"],
        requirement_ids=["REQ-AUTH-001"],
    )

    assert report["summary"]["selected"] == 1
    route = report["routes"][0]
    assert route["decision"] == "selected"
    assert route["adapter"] == "command"
    assert route["minimum_evidence"] == ["TEST_VALIDATED"]


def test_routing_report_classifies_missing_adapter(tmp_path: Path) -> None:
    package_root = _package_root(tmp_path, requirement_id="REQ-AUTH-001")

    report = build_routing_report(
        package_root,
        registry=_registry(adapters=[]),
        policy=_policy(adapter="command"),
        changed_paths=["src/auth.py"],
    )

    assert report["summary"]["missing_adapter"] == 1
    assert report["findings"][0]["category"] == "missing_adapter"


def test_routing_report_classifies_unsupported_claim(tmp_path: Path) -> None:
    package_root = _package_root(
        tmp_path,
        requirement_id="REQ-STATE-001",
        fixture="state_postcondition.nlreq",
        claim_kind="state_postcondition",
    )

    report = build_routing_report(
        package_root,
        registry=_registry(),
        policy=_policy(requirement_id_patterns=["REQ-STATE-*"]),
        changed_paths=["src/auth.py"],
    )

    assert report["summary"]["unsupported_claim"] == 1
    assert "does not support claim kind state_postcondition" in report["routes"][0]["reason"]


def test_routing_report_classifies_ambiguous_and_out_of_scope_routes(tmp_path: Path) -> None:
    package_root = _package_root(tmp_path, requirement_id="REQ-AUTH-001")
    registry = _registry(
        adapters=[
            _adapter("command"),
            _adapter("command-shadow"),
        ]
    )
    ambiguous_policy = _policy(adapter=None)
    out_of_scope_policy = _policy()

    ambiguous = build_routing_report(
        package_root,
        registry=registry,
        policy=ambiguous_policy,
        changed_paths=["src/auth.py"],
    )
    out_of_scope = build_routing_report(
        package_root,
        registry=registry,
        policy=out_of_scope_policy,
        changed_paths=["docs/readme.md"],
    )

    assert ambiguous["summary"]["ambiguous_route"] == 1
    assert out_of_scope["summary"]["out_of_scope"] == 1


def test_routing_report_marks_non_gateable_adapter_report_only(tmp_path: Path) -> None:
    package_root = _package_root(tmp_path, requirement_id="REQ-AUTH-001")
    registry = _registry(
        adapters=[
            _adapter(
                "trace",
                target_kind="runtime_trace",
                evidence=["TRACE_VALIDATED"],
                gateable=False,
            )
        ]
    )
    policy = RoutingPolicyArtifact.model_validate(
        {
            "rules": [
                {
                    "name": "runtime-trace",
                    "adapter": "trace",
                    "target_kind": "runtime_trace",
                    "minimum_evidence": ["TRACE_VALIDATED"],
                    "requirement_id_patterns": ["REQ-AUTH-*"],
                }
            ]
        }
    )

    report = build_routing_report(
        package_root,
        registry=registry,
        policy=policy,
    )

    assert report["summary"]["report_only"] == 1
    assert report["routes"][0]["decision"] == "report_only"


def test_route_adapters_cli_validates_and_writes_reports(tmp_path: Path, capsys) -> None:
    package_root = _package_root(tmp_path, requirement_id="REQ-AUTH-001")
    registry = tmp_path / "adapter-registry.json"
    policy = tmp_path / "routing-policy.json"
    out = tmp_path / "routing.json"
    markdown_out = tmp_path / "routing.md"
    write_json(registry, _registry())
    write_json(policy, _policy())

    registry_exit = main(["validate-adapter-registry", str(registry)])
    policy_exit = main(["validate-routing-policy", str(policy)])
    route_exit = main(
        [
            "route-adapters",
            str(package_root),
            "--adapter-registry",
            str(registry),
            "--routing-policy",
            str(policy),
            "--changed-path",
            "src/auth.py",
            "--out",
            str(out),
            "--markdown-out",
            str(markdown_out),
        ]
    )

    output = capsys.readouterr().out

    assert registry_exit == 0
    assert policy_exit == 0
    assert route_exit == 0
    assert "Adapter registry: valid" in output
    assert "Routing policy: valid" in output
    assert read_json(out)["summary"]["selected"] == 1
    assert "# NLReq Adapter Routing Report" in markdown_out.read_text()


def test_routing_report_markdown_renders_findings(tmp_path: Path) -> None:
    package_root = _package_root(tmp_path, requirement_id="REQ-AUTH-001")
    report = build_routing_report(
        package_root,
        registry=_registry(adapters=[]),
        policy=_policy(),
        changed_paths=["src/auth.py"],
    )

    markdown = routing_report_markdown(report)

    assert "| warning | missing_adapter | REQ-AUTH-001 |" in markdown


def _package_root(
    tmp_path: Path,
    *,
    requirement_id: str,
    fixture: str = "authorization_precondition.nlreq",
    claim_kind: str = "authorization_precondition",
) -> Path:
    package_root = tmp_path / "requirements"
    build_package(
        controlled_text=(FIXTURES / fixture).read_text(),
        output_dir=package_root / requirement_id,
        requirement_id=requirement_id,
        title="Routed requirement",
        claim_kind=claim_kind,
    )
    return package_root


def _registry(adapters: list[dict[str, object]] | None = None) -> AdapterRegistryArtifact:
    return AdapterRegistryArtifact.model_validate(
        {
            "registry_version": "0.1",
            "adapters": [_adapter("command")] if adapters is None else adapters,
        }
    )


def _adapter(
    adapter_id: str,
    *,
    target_kind: str = "command_test_runner",
    evidence: list[str] | None = None,
    gateable: bool = True,
) -> dict[str, object]:
    return {
        "adapter_id": adapter_id,
        "target_kind": target_kind,
        "supported_claim_kinds": ["authorization_precondition", "state_precondition"],
        "supported_evidence": evidence or ["TEST_VALIDATED"],
        "conformance": {"status": "pass", "suite_version": "0.1"},
        "gateable": gateable,
    }


def _policy(
    *,
    adapter: str | None = "command",
    requirement_id_patterns: list[str] | None = None,
) -> RoutingPolicyArtifact:
    raw: dict[str, object] = {
        "routing_version": "0.1",
        "rules": [
            {
                "name": "command-auth",
                "path_patterns": ["src/**/*.py"],
                "requirement_id_patterns": requirement_id_patterns or ["REQ-AUTH-*"],
                "target_kind": "command_test_runner",
                "minimum_evidence": ["TEST_VALIDATED"],
            }
        ],
    }
    if adapter is not None:
        raw["rules"][0]["adapter"] = adapter  # type: ignore[index]
    return RoutingPolicyArtifact.model_validate(raw)
