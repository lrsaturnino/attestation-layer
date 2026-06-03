# Operational Real-Evidence Gap Closure Plan

## Status

Follow-up plan for real external evidence. This is not a new vocabulary layer;
it is the evidence-production pass required after phases 151-192.

## Objective

Close the remaining gap between implemented contracts and the public
real-evidence conclusion by supplying real retained artifacts for every
phase-level report in milestones 15 through 20.

## Workstreams

### 1. Translation Evidence Run

- Build or import the labeled translation release corpus.
- Run controlled rewrite replay and semantic decomposition on every case.
- Measure semantic accuracy, false acceptance, false refusal, unsupported
  fragments, and contradiction recall.
- Produce phase reports for phases 151-156 using real corpus artifacts.

### 2. Formal Backend Evidence Run

- Select non-toy reviewed TLA+ specs.
- Run Apalache and TLC with retained commands, bounds, outputs, and
  counterexamples.
- Produce reviewed system spec packages and S-and-R compatibility reports.
- Produce phase reports for phases 157-163.

### 3. Brownfield Grounding Run

- Select one real brownfield module.
- Generate impact, coverage, freshness, trace producer, trace validation, and
  remediation reports.
- Promote any generated candidate specs only through review.
- Produce phase reports for phases 164-171.

### 4. Adapter Evidence Run

- Certify Solidity, Go, TypeScript/JavaScript, Python, and Rust or Java adapters
  with retained source, impact, trace, and limitation artifacts.
- Run one cross-adapter causal trace proof.
- Produce phase reports for phases 172-179.

### 5. Replay, Benchmark, And Release Evidence Run

- Export replay bundle v3 artifacts with retention metadata.
- Enforce producer key trust, rotation, revocation, and high-assurance signing.
- Run hostile public benchmarks and produce signed leaderboard reports.
- Run the non-toy reference brownfield demo and beta pilots.
- Produce phase reports for phases 180-186.

### 6. Publication And Review Run

- Complete threat-model and TCB re-review.
- Package external reproduction and red-team review artifacts.
- Freeze public docs and schemas.
- Sign and publish the release bundle.
- Produce phase reports for phases 187-192.

## Re-Run Procedure

For each workstream:

1. Produce real retained artifacts and record their hashes.
2. Build `RealEvidencePhaseReport` objects for the affected phases.
3. Build the milestone report.
4. Build the Claude-conversation gap assessment.
5. If the assessment is still blocked, update this plan with the named blockers
   and repeat the affected workstream.

## Exit Bar

The gap closes only when the Claude-conversation gap assessment returns
`aligned`, all milestone reports pass, and no phase uses scaffold or
fixture-only evidence for a release-critical artifact.
