from pathlib import Path

from nlreq.agent_workflow import (
    agent_pr_comment_markdown,
    build_agent_implementation_task,
    build_agent_verifier_handoff,
)
from nlreq.cli import main
from nlreq.jsonutil import read_json
from nlreq.package import build_package


FIXTURES = Path(__file__).parent / "fixtures" / "requirements"


def test_agent_implementation_task_summarizes_approved_packages(tmp_path: Path) -> None:
    package_root = tmp_path / "requirements"
    build_package(
        controlled_text=(FIXTURES / "authorization_precondition.nlreq").read_text(),
        output_dir=package_root / "REQ-AUTH-001",
        requirement_id="REQ-AUTH-001",
        title="Unauthorized operation is rejected before state changes",
        claim_kind="authorization_precondition",
    )

    task = build_agent_implementation_task(
        package_root,
        requirement_ids=["REQ-AUTH-001"],
        workflow_id="WF-001",
        step_id="coder-task",
        created_at="2026-06-01T00:00:00Z",
        allowed_paths=["src/auth.py"],
        reviewer_constraints=["do not change public API"],
    )

    assert task["artifact_kind"] == "agent_implementation_task"
    assert task["ready"] is True
    assert task["implementation_scope"]["allowed_paths"] == ["src/auth.py"]
    assert task["packages"][0]["requirement_id"] == "REQ-AUTH-001"
    assert task["packages"][0]["artifacts"]["requirement.ir.json"].startswith("sha256:")
    assert task["packages"][0]["required_evidence"][0]["id"] == "C-static"


def test_agent_implementation_task_blocks_refused_or_missing_packages(tmp_path: Path) -> None:
    package_root = tmp_path / "requirements"
    build_package(
        controlled_text=(FIXTURES / "unbound_symbol.nlreq").read_text(),
        output_dir=package_root / "REQ-REFUSED-UNBOUND-001",
        requirement_id="REQ-REFUSED-UNBOUND-001",
        title="Unbound operator example",
        claim_kind="authorization_precondition",
    )

    task = build_agent_implementation_task(
        package_root,
        requirement_ids=["REQ-REFUSED-UNBOUND-001", "REQ-MISSING-001"],
        workflow_id="WF-002",
    )

    assert task["ready"] is False
    assert {blocker["category"] for blocker in task["blockers"]} == {
        "status",
        "missing_package",
    }


def test_agent_verifier_handoff_builds_retry_payloads_for_failed_checks(tmp_path: Path) -> None:
    package_root = tmp_path / "requirements"
    build_package(
        controlled_text=(FIXTURES / "unbound_symbol.nlreq").read_text(),
        output_dir=package_root / "REQ-REFUSED-UNBOUND-001",
        requirement_id="REQ-REFUSED-UNBOUND-001",
        title="Unbound operator example",
        claim_kind="authorization_precondition",
    )

    handoff = build_agent_verifier_handoff(
        package_root,
        requirement_ids=["REQ-REFUSED-UNBOUND-001"],
        workflow_id="WF-003",
        step_id="verify",
        created_at="2026-06-01T00:00:00Z",
    )

    assert handoff["artifact_kind"] == "agent_verifier_handoff"
    assert handoff["result"] == "blocked"
    assert handoff["summary"]["retry_payloads"] == 1
    retry = handoff["retry_payloads"][0]
    assert retry["requirement_id"] == "REQ-REFUSED-UNBOUND-001"
    assert retry["failed_checks"] == ["C-static"]
    assert retry["backend_results"][0]["backend"] == "generic_adapter"


def test_agent_pr_comment_markdown_prioritizes_findings_and_retry_payloads(
    tmp_path: Path,
) -> None:
    package_root = tmp_path / "requirements"
    build_package(
        controlled_text=(FIXTURES / "unbound_symbol.nlreq").read_text(),
        output_dir=package_root / "REQ-REFUSED-UNBOUND-001",
        requirement_id="REQ-REFUSED-UNBOUND-001",
        title="Unbound operator example",
        claim_kind="authorization_precondition",
    )
    handoff = build_agent_verifier_handoff(
        package_root,
        requirement_ids=["REQ-REFUSED-UNBOUND-001"],
        workflow_id="WF-004",
    )

    markdown = agent_pr_comment_markdown(handoff)

    assert "# NLReq Agent Verification Handoff" in markdown
    assert "| soft_gate | blocker | status | REQ-REFUSED-UNBOUND-001 |" in markdown
    assert "### REQ-REFUSED-UNBOUND-001" in markdown


def test_agent_workflow_cli_commands_write_artifacts(tmp_path: Path, capsys) -> None:
    package_root = tmp_path / "requirements"
    task_out = tmp_path / "agent-task.json"
    handoff_out = tmp_path / "agent-handoff.json"
    comment_out = tmp_path / "agent-comment.md"
    audit_log = tmp_path / "agent-audit.json"
    build_package(
        controlled_text=(FIXTURES / "authorization_precondition.nlreq").read_text(),
        output_dir=package_root / "REQ-AUTH-001",
        requirement_id="REQ-AUTH-001",
        title="Unauthorized operation is rejected before state changes",
        claim_kind="authorization_precondition",
    )

    task_exit = main(
        [
            "agent-task",
            str(package_root),
            "--requirement-id",
            "REQ-AUTH-001",
            "--workflow-id",
            "WF-CLI",
            "--allowed-path",
            "src/auth.py",
            "--out",
            str(task_out),
        ]
    )
    verify_exit = main(
        [
            "agent-verify",
            str(package_root),
            "--requirement-id",
            "REQ-AUTH-001",
            "--workflow-id",
            "WF-CLI",
            "--out",
            str(handoff_out),
            "--markdown-out",
            str(comment_out),
        ]
    )
    comment_exit = main(["agent-pr-comment", str(handoff_out), "--out", str(comment_out)])
    audit_exit = main(
        [
            "agent-audit",
            "--log",
            str(audit_log),
            "--workflow-id",
            "WF-CLI",
            "--step-id",
            "verify",
            "--agent-role",
            "verifier",
            "--tool",
            "nlreq agent-verify",
            "--input-package",
            str(package_root / "REQ-AUTH-001"),
            "--output-artifact",
            str(handoff_out),
            "--decision-status",
            "pass",
        ]
    )

    output = capsys.readouterr().out

    assert task_exit == 0
    assert verify_exit == 0
    assert comment_exit == 0
    assert audit_exit == 0
    assert "Agent implementation task:" in output
    assert "Agent verifier handoff:" in output
    assert read_json(task_out)["ready"] is True
    assert read_json(handoff_out)["result"] == "pass"
    assert "# NLReq Agent Verification Handoff" in comment_out.read_text()
    audit_entries = read_json(audit_log)
    assert len(audit_entries) == 1
    assert audit_entries[0]["input_packages"][0]["requirement_id"] == "REQ-AUTH-001"
    assert audit_entries[0]["output_artifacts"][0]["hash"].startswith("sha256:")
