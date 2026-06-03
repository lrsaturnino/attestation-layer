from nlreq.real_evidence import (
    FINAL_REAL_EVIDENCE_PHASES,
    MILESTONE_NAMES,
    RealEvidenceArtifactRef,
    build_claude_convo_gap_assessment,
    build_milestone_evidence_report,
    build_phase_evidence_report,
    gap_closure_plan_markdown,
)


def test_real_evidence_phase_registry_covers_milestones_15_to_20() -> None:
    phases = [plan.phase for plan in FINAL_REAL_EVIDENCE_PHASES]
    adrs = [plan.required_adr for plan in FINAL_REAL_EVIDENCE_PHASES]

    assert phases == list(range(151, 193))
    assert adrs == list(range(160, 202))
    assert {plan.milestone for plan in FINAL_REAL_EVIDENCE_PHASES} == set(MILESTONE_NAMES)
    assert all(plan.required_artifact_types for plan in FINAL_REAL_EVIDENCE_PHASES)


def test_phase151_blocks_missing_approved_rewrite_and_scaffold_evidence() -> None:
    plan = _phase_plan(151)
    missing = build_phase_evidence_report(
        phase=151,
        evidence=[
            _artifact(
                plan.required_artifact_types[0],
                phase=151,
                index=0,
            )
        ],
    )
    scaffold = build_phase_evidence_report(
        phase=151,
        evidence=[
            _artifact(artifact_type, phase=151, index=index, real_evidence=False)
            for index, artifact_type in enumerate(plan.required_artifact_types)
        ],
    )

    assert missing.result == "blocked"
    assert "approved_controlled_rewrite" in missing.blockers[0]
    assert scaffold.result == "blocked"
    assert any("scaffold" in blocker for blocker in scaffold.blockers)


def test_phase_reports_need_review_for_unreviewed_or_non_replayable_artifacts() -> None:
    plan = _phase_plan(153)
    report = build_phase_evidence_report(
        phase=153,
        evidence=[
            _artifact(
                artifact_type,
                phase=153,
                index=index,
                reviewed=index != 0,
                replayable=index != 1,
            )
            for index, artifact_type in enumerate(plan.required_artifact_types)
        ],
    )

    assert report.result == "needs_review"
    assert any("not reviewed" in blocker for blocker in report.blockers)
    assert any("not replayable" in blocker for blocker in report.blockers)


def test_milestone15_passes_when_all_phase_artifacts_are_real_reviewed_and_replayable() -> None:
    phase_reports = [
        build_phase_evidence_report(
            phase=plan.phase,
            evidence=_phase_artifacts(plan),
        )
        for plan in FINAL_REAL_EVIDENCE_PHASES
        if plan.milestone == 15
    ]
    milestone = build_milestone_evidence_report(
        milestone=15,
        phase_reports=phase_reports,
    )

    assert milestone.result == "passed"
    assert milestone.phase_count == 6
    assert milestone.passed_phase_count == 6
    assert milestone.blockers == []


def test_missing_phase_blocks_milestone_and_final_assessment_requests_followup_plan() -> None:
    milestone15_reports = [
        build_phase_evidence_report(
            phase=plan.phase,
            evidence=_phase_artifacts(plan),
        )
        for plan in FINAL_REAL_EVIDENCE_PHASES
        if plan.milestone == 15 and plan.phase != 156
    ]
    milestone15 = build_milestone_evidence_report(
        milestone=15,
        phase_reports=milestone15_reports,
    )
    assessment = build_claude_convo_gap_assessment(
        milestone_reports=[milestone15],
        target_context_doc_hash="sha256:claude",
        roadmap_hash="sha256:roadmap",
    )
    plan_markdown = gap_closure_plan_markdown(assessment)

    assert milestone15.result == "blocked"
    assert milestone15.missing_phases == [156]
    assert assessment.result == "blocked"
    assert assessment.next_plan_required is True
    assert "phase 156" in "\n".join(assessment.important_missing_features)
    assert "Release publication remains blocked" in plan_markdown


def test_all_milestones_15_to_20_align_with_claude_target_when_all_phases_pass() -> None:
    milestone_reports = []
    for milestone in MILESTONE_NAMES:
        phase_reports = [
            build_phase_evidence_report(
                phase=plan.phase,
                evidence=_phase_artifacts(plan),
            )
            for plan in FINAL_REAL_EVIDENCE_PHASES
            if plan.milestone == milestone
        ]
        milestone_reports.append(
            build_milestone_evidence_report(
                milestone=milestone,
                phase_reports=phase_reports,
            )
        )

    assessment = build_claude_convo_gap_assessment(
        milestone_reports=milestone_reports,
        target_context_doc_hash="sha256:claude",
        roadmap_hash="sha256:roadmap",
    )

    assert all(report.result == "passed" for report in milestone_reports)
    assert assessment.result == "aligned"
    assert assessment.closeness_score == 1.0
    assert assessment.implemented_phase_count == len(FINAL_REAL_EVIDENCE_PHASES)
    assert assessment.next_plan_required is False
    assert assessment.important_missing_features == []


def _phase_plan(phase: int):
    return next(plan for plan in FINAL_REAL_EVIDENCE_PHASES if plan.phase == phase)


def _phase_artifacts(plan):
    return [
        _artifact(artifact_type, phase=plan.phase, index=index)
        for index, artifact_type in enumerate(plan.required_artifact_types)
    ]


def _artifact(
    artifact_type: str,
    *,
    phase: int,
    index: int,
    real_evidence: bool = True,
    reviewed: bool = True,
    replayable: bool = True,
) -> RealEvidenceArtifactRef:
    return RealEvidenceArtifactRef(
        artifact_type=artifact_type,
        artifact_hash=f"sha256:phase-{phase}-{index}",
        real_evidence=real_evidence,
        reviewed=reviewed,
        replayable=replayable,
        signed=True,
        producer_id=f"producer-{phase}",
    )
