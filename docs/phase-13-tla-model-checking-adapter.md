# Phase 13 TLA+ Model-Checking Adapter

Phase 13 should add the first formal/model-checking adapter for reviewed TLA+
specs and bounded state-machine evidence.

This phase is implemented in the reference CLI as `tla-package`,
`tla-validate`, and `tla-check`.

## Purpose

The phase should let the Attestation Layer say:

```text
This reviewed requirement is linked to this reviewed TLA+ model,
checked with this config, bounds, constants, and model-checker version,
and no violation was found within that model scope.
```

It should not say:

```text
The production implementation is proven correct.
The bounded model is an inductive proof.
The TLA+ model perfectly represents the code.
```

TLA+ evidence is design/model evidence unless a later integration explicitly
links implementation traces or code to the model.

## Why This Comes After Phase 12

Phase 10 creates broad test-command evidence. Phase 11 creates runtime trace
evidence. Phase 12 makes adapter selection deterministic. Once those practical
layers exist, TLA+ can enter as a high-assurance adapter for critical paths
without becoming the default tool for every requirement.

The intended sequence is:

```text
reviewed requirement
  -> reviewed TLA+ model and config
  -> TLC or Apalache run
  -> bounded result or counterexample
  -> evidence object
  -> gates, continuous reports, and agent handoff
```

## Relationship To Specula

Specula should inform Phase 13, but Phase 13 should not delegate trust to the
whole Specula pipeline.

Specula is useful for:

- TLA+ workflow methodology;
- reviewed model structure such as `base.tla`, `MC.tla`, `MC.cfg`, and
  `MC_hunt_*.cfg`;
- TLC execution patterns;
- TLC output and counterexample parsing;
- trace-validation/debugging methods;
- bug classification and confirmation practices;
- and examples from existing case studies.

The `nlreq` Phase 13 adapter should wrap any reused Specula tool output into
Attestation Layer artifacts. That means package hashes, model/config hashes,
checker metadata, bounded result semantics, normalized counterexamples,
evidence objects, and status decisions remain owned by `nlreq`.

Specula-generated TLA+ may be accepted as a draft input only after review. It
does not become gateable evidence just because an agent produced it.

## Planned CLI Shape

Example package build:

```bash
uv run nlreq tla-package tests/fixtures/requirements/authorization_precondition.nlreq \
  --out /tmp/REQ-AUTH-TLA-001 \
  --requirement-id REQ-AUTH-TLA-001 \
  --title "Unauthorized operation is rejected before state changes" \
  --claim-kind authorization_precondition \
  --model-config docs/examples/tla-models.example.json
```

Example validation:

```bash
uv run nlreq tla-validate /tmp/REQ-AUTH-TLA-001 \
  --model-config docs/examples/tla-models.example.json
```

Example evidence run:

```bash
uv run nlreq tla-check requirements \
  --requirement-id REQ-AUTH-001 \
  --model-config docs/examples/tla-models.example.json \
  --out /tmp/nlreq-tla-results.json \
  --markdown-out /tmp/nlreq-tla-results.md
```

Model checking remains explicit and reproducible: model/config files are
project-root-relative, commands are argv arrays, and results are bound to
recorded model/config hashes.

## Planned Model Config

```json
{
  "schema_version": "0.1",
  "adapter": "tla",
  "models": [
    {
      "model_id": "authorization-state-machine",
      "requirement_ids": ["REQ-AUTH-001"],
      "module": "specs/models/Authorization.tla",
      "config": "specs/models/Authorization.cfg",
      "checker": "tlc",
      "command": [
        "tlc2.TLC",
        "-config",
        "specs/models/Authorization.cfg",
        "specs/models/Authorization.tla"
      ],
      "properties": ["UnauthorizedRejectedBeforeStateChange"],
      "bounds": {
        "actors": 3,
        "resources": 3,
        "steps": 10
      },
      "requested_evidence": "BOUNDED_CHECKED"
    }
  ]
}
```

Commands must be argv arrays, not shell strings. Model files and configs must be
hashed before their results can satisfy evidence.

## Evidence Semantics

The adapter may produce `BOUNDED_CHECKED` only when:

- the model checker command completes successfully;
- the module and config are hashed;
- bounds, constants, and checked properties are recorded;
- the requirement id is explicitly linked to the property;
- the checker reports no invariant/property violation within the configured
  scope;
- and the result is fresh for the model/config hashes.

The adapter must not produce `PROVEN_INDUCTIVE` in the first implementation.
That evidence level requires a true inductive proof artifact from a future proof
backend.

## Counterexamples

Failed checks should produce structured counterexamples:

```json
{
  "kind": "model_check_counterexample",
  "requirement_id": "REQ-AUTH-001",
  "model_id": "authorization-state-machine",
  "property": "UnauthorizedRejectedBeforeStateChange",
  "states": [
    {
      "index": 0,
      "variables": {
        "authorized": false,
        "stateChanged": false
      }
    },
    {
      "index": 1,
      "action": "StateChange",
      "variables": {
        "authorized": false,
        "stateChanged": true
      }
    }
  ]
}
```

The exact structure can evolve, but it must be small enough for CI reports and
agent handoffs.

## Integration Points

Phase 13 should integrate with:

- adapter registry and routing, so model-checking adapters are selected only for
  requirements that need them;
- package index and CI reports, so model evidence and counterexamples are
  visible;
- hard gates, so critical paths can require `BOUNDED_CHECKED`;
- continuous attestation, so model/config drift and checker regressions are
  reported;
- agent verifier handoffs, so model failures escalate with reviewer context;
- selected Specula tools, when they are deterministic and wrapped into `nlreq`
  evidence artifacts;
- and future trace validation, so observed traces may later be checked against
  reviewed models.

## Safety Rules

- Do not generate or accept a TLA+ model without review metadata.
- Do not claim proof from bounded model checking.
- Do not hide model bounds, constants, or checker versions.
- Do not let raw checker output be the only counterexample format.
- Do not treat Specula's agentic workflow output as evidence without
  normalization into Attestation Layer artifacts.
- Do not mutate reviewed packages in place.
- Do not route all requirements to TLA+ by default.
- Do not treat model evidence as implementation evidence unless a separate
  adapter links code or traces to the model.

## Success Criterion

Phase 13 succeeds when:

- a reviewed requirement can be linked to a reviewed TLA+ model/config;
- model files and configs are hash-addressed;
- a model-checker command produces deterministic result artifacts;
- passing checks can satisfy `BOUNDED_CHECKED`;
- failures and timeouts produce structured backend results and counterexamples;
- package index, gates, continuous reports, and agent handoffs can consume the
  model-checking evidence;
- and existing generic, Python, OpenAPI, command/test-runner, trace, and routing
  workflows remain compatible.

## Boundary

This phase is not full proof automation, free-form NL-to-TLA+ generation, or
implementation correctness. It adds honest bounded model-checking evidence for
reviewed models.
