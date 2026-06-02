# Milestone Group 4 Productionization And Release Digest

Milestone group 4 is roadmap Step 4, covering phases 73 through 82. It starts
after formal closure, brownfield grounding, adapter certification, and
cross-language proof aggregation have machine-readable artifacts.

## Objective

Group 4 turns the proof pipeline into an adoptable engineering control. The
gate must retain evidence, verify producer identity where required, run in CI
and PR workflows, publish benchmark accountability, cache safely, govern
waivers, document its trusted computing base, ship a reproducible brownfield
demo, and certify the conclusion release against public criteria.

## Phase Digest

| Phase | Focus | Implementation Surface |
|---:|---|---|
| 73 | Evidence artifact store | `nlreq.artifact_store`, artifact lookup schemas, `artifact-put`, `artifact-get` |
| 74 | Signed evidence | `nlreq.signed_evidence`, producer key registry, `sign-evidence`, `verify-evidence` |
| 75 | CI and PR action gate | `nlreq.ci_pr_gate`, report-only/hard-gate modes, PR Markdown renderer |
| 76 | Benchmark corpus v2 | `nlreq.benchmark_v2`, false-closure budget, category metrics |
| 77 | Performance and caching | `nlreq.verification_cache`, hash-keyed cache records and lookup semantics |
| 78 | Policy and waiver governance v2 | `nlreq.policy_v2`, waiver audit report and expiration enforcement |
| 79 | Threat model and TCB audit | `nlreq.threat_model`, TCB inventory and adversarial scenarios |
| 80 | Reference brownfield demo | `nlreq.reference_demo`, reproducibility manifest and artifact-presence check |
| 81 | Public documentation and SDK | `nlreq.public_sdk`, versioned public docs and example index |
| 82 | Conclusion release certification | `nlreq.conclusion_certification`, release criteria report |

## Required Shape

- Artifact hashes are content addresses. Missing artifacts are integrity
  failures, not warnings hidden in prose.
- Signed evidence is required only when policy asks for high assurance. Local
  unsigned developer evidence remains possible but must not be mislabeled.
- CI reports have machine-readable result fields; Markdown is only a rendering.
- Benchmark v2 tracks false closure explicitly and can budget it at zero for
  hard-gated cases.
- Cache hits are keyed by input hashes, tool versions, and optional policy hash.
  Cache reuse is disclosed and cannot upgrade assurance.
- Waivers remain visible, expire, and cannot silently convert blocked proof
  closure into closed proof closure.
- Threat model output names the TCB and residual risks for high-assurance
  claims.
- Conclusion certification is a report over evidence, not a claim that every
  natural-language or program behavior is fully verified.

## Main Risks

- Treating retained artifacts as evidence even when hashes do not resolve.
- Letting signatures imply semantic correctness.
- Allowing PR comments to become the source of truth instead of JSON reports.
- Caching across changed inputs or changed tool versions.
- Normalizing waivers into an ordinary success path.
- Certifying a release without benchmark and demo reproducibility evidence.

## Exit Readiness Checklist

- Every group 4 phase has a spec and ADR.
- Artifact store, signing, CI report, benchmark v2, cache, waiver audit, threat
  model, demo, docs, and certification schemas regenerate with no drift.
- CLI exposes the main productization commands.
- Tests cover non-approving behavior for missing tools, stale freshness,
  trace normalization loss, adapter certification, artifact lookup, signature
  verification, waiver audit, and release certification.
