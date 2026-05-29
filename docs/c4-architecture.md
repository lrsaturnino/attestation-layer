# C4 Architecture Diagrams

These diagrams describe the current NL Requirement Attestation Layer
implementation in this worktree. They cover phases 0 through 17, including the
Phase 17 Protobuf/gRPC adapter.

The diagrams use C4-PlantUML notation so each element has a name, technology
where relevant, and a description, and each relationship has a precise label.

## Implemented Scope

| Phase | Implemented Capability | Primary Entry Points |
|---|---|---|
| 0 | Adapter-neutral parser, IR, generic adapter, package builder, schemas, SMT checks, status decisions, and conformance suite. | `nlreq parse`, `ir`, `package`, `validate`, `validate-all`, `conformance` |
| 1 | Python package adapter with deterministic symbol discovery and pytest-backed tasks. | `python-conformance`, `python-package`, `python-validate` |
| 2 | Python adapter evidence packages with adapter results and freshness checks. | `python-package`, `python-validate` |
| 3 | Adoption reporting, package indexes, CI shadow reports, and review checklist template. | `package-index`, `ci-report`, `review-template` |
| 4 | Soft gate over referenced requirements. | `soft-gate` |
| 5 | Scoped hard gate with policy and waiver evaluation. | `hard-gate` |
| 6 | Stronger backend artifacts, generated Python property checks, source hashes, counterexamples, and trace schemas. | `python-package --property-checks`, `decide-status` |
| 7 | OpenAPI declaration-level adapter and package flow. | `openapi-conformance`, `openapi-package`, `openapi-validate` |
| 8 | Continuous attestation reports, package freshness, deltas, and trace artifact ingestion. | `continuous-attestation` |
| 9 | Agent implementation tasks, verifier handoffs, PR comments, and audit entries. | `agent-task`, `agent-verify`, `agent-pr-comment`, `agent-audit` |
| 10 | Command/test-runner adapter with reviewed command checks and bounded execution. | `command-conformance`, `command-package`, `command-validate`, `command-evidence` |
| 11 | Runtime trace validation over normalized traces for supported claims. | `trace-validate`, `continuous-attestation --trace-validation` |
| 12 | Adapter registry, routing policy, and deterministic route reports. | `validate-adapter-registry`, `validate-routing-policy`, `route-adapters` |
| 13 | TLA/model-checking adapter with model/config hashes and bounded check results. | `tla-package`, `tla-validate`, `tla-check` |
| 14 | GraphQL schema adapter and package flow. | `graphql-conformance`, `graphql-package`, `graphql-validate` |
| 15 | JSON Schema adapter and package flow. | `json-schema-conformance`, `json-schema-package`, `json-schema-validate` |
| 16 | AsyncAPI adapter and package flow. | `asyncapi-conformance`, `asyncapi-package`, `asyncapi-validate` |
| 17 | Protobuf/gRPC adapter and package flow. | `protobuf-conformance`, `protobuf-package`, `protobuf-validate` |

## Level 1 - System Context

```plantuml
@startuml
!include https://raw.githubusercontent.com/plantuml-stdlib/C4-PlantUML/master/C4_Context.puml

LAYOUT_WITH_LEGEND()
title NL Requirement Attestation Layer - C4 Level 1 System Context

Person(reviewer, "Human reviewer", "Reviews controlled requirements, assumptions, bindings, generated package artifacts, gate findings, and agent handoff summaries before accepting evidence.")
Person(specifier, "Specifier or requirement author", "Writes controlled natural-language requirements and supplies requirement ids, claim kinds, titles, assumptions, and reviewed adapter metadata.")
Person(coderAgent, "Coder agent", "Consumes implementation tasks and package constraints, changes implementation files, and must not mutate reviewed package artifacts.")
Person(verifierAgent, "Verifier agent", "Consumes verifier handoffs, gate reports, retry payloads, and package hashes to decide whether implementation work is ready for review.")

System_Boundary(attestationBoundary, "NL Requirement Attestation Layer") {
  System(attestation, "Attestation Layer CLI and library", "Deterministic Python implementation that parses controlled requirements, binds symbols through adapters, runs evidence backends, emits reviewed package artifacts, and produces adoption, gate, routing, continuous-attestation, and agent workflow reports.")
}

System_Ext(targetRepo, "Target project repository", "Implementation source, tests, OpenAPI/GraphQL/JSON Schema/AsyncAPI/Protobuf contracts, TLA models, command-check configuration, and normalized runtime traces that adapters inspect.")
System_Ext(ciSystem, "CI or scheduled automation", "Runs attestation commands in shadow, soft-gate, hard-gate, continuous, routing, command-evidence, and trace-validation workflows.")
System_Ext(packageStore, "Requirement package directory", "File-system directory containing reviewed immutable package artifacts such as IR, bindings, assumptions, review, tasks, adapter results, evidence, status, traces, counterexamples, and implementation specs.")
System_Ext(externalTools, "External verification tools", "Pytest, generated Python property checks, bounded command runners, custom TLA checker commands, and Z3-backed SMT checks used as deterministic evidence backends.")

Rel(specifier, attestation, "Submits controlled requirements and adapter configuration to create or refresh packages", "CLI")
Rel(reviewer, attestation, "Runs validation, reviews reports, and accepts or rejects evidence decisions", "CLI and Markdown/JSON")
Rel(coderAgent, attestation, "Requests implementation tasks with requirement constraints and immutable package hashes", "JSON artifact")
Rel(verifierAgent, attestation, "Requests verifier handoffs with gate findings, retry payloads, and continuous-attestation context", "JSON and Markdown artifacts")
Rel(ciSystem, attestation, "Executes report, gate, routing, trace, command, TLA, and continuous workflows on repository changes or schedules", "CLI")
Rel(attestation, targetRepo, "Reads source files, tests, API contracts, models, command configs, and trace artifacts without trusting them as reviewed specs", "File system")
Rel(attestation, packageStore, "Writes and validates reviewed requirement package artifacts with stable hashes and status decisions", "JSON and Markdown files")
Rel(attestation, externalTools, "Invokes deterministic evidence backends and records bounded results, hashes, failures, and counterexamples", "Subprocess or library call")
Rel(ciSystem, packageStore, "Publishes reports and package snapshots for review and audit", "Artifacts")

@enduml
```

## Level 2 - Containers

```plantuml
@startuml
!include https://raw.githubusercontent.com/plantuml-stdlib/C4-PlantUML/master/C4_Container.puml

LAYOUT_WITH_LEGEND()
title NL Requirement Attestation Layer - C4 Level 2 Containers

Person(operator, "Operator, reviewer, CI, or agent", "Runs commands and consumes JSON/Markdown artifacts for specification review, CI reporting, gates, routing, continuous attestation, and agent workflows.")

System_Boundary(attestation, "NL Requirement Attestation Layer") {
  Container(cli, "nlreq CLI", "Python argparse command-line application", "Single command surface for parsing, packaging, validating, conformance, adapters, gates, routing, continuous attestation, trace validation, command evidence, TLA checks, and agent artifacts.")
  Container(core, "Requirement core", "Python library", "Adapter-neutral parser, IR model, source-span provenance, binding diagnostics, package integrity validation, evidence aggregation, pure status decisions, and JSON schema generation.")
  Container(adapterLayer, "Adapter layer", "Python adapter implementations", "Deterministic adapter interface and concrete adapters for generic symbols, Python packages, OpenAPI, GraphQL, JSON Schema, AsyncAPI, command checks, runtime traces, TLA models, and local Protobuf/gRPC.")
  Container(evidenceBackends, "Evidence backends", "Python, Z3, subprocess tools", "Core SMT checks, self-consistency checks, pytest execution, generated property checks, command execution, runtime trace validation, and TLA/model-checking command execution.")
  Container(reporting, "Reporting and gates", "Python report builders", "Builds package indexes, CI shadow reports, soft gates, hard gates, routing reports, continuous attestation reports, trace validation reports, command result reports, and TLA result reports.")
  Container(agentWorkflow, "Agent workflow artifacts", "Python JSON/Markdown emitters", "Creates implementation task payloads, verifier handoffs, PR-comment Markdown, and append-only audit entries for specifier, coder, verifier, and reviewer roles.")
  ContainerDb(packageArtifacts, "Requirement packages and reports", "JSON and Markdown files", "Durable artifact set containing reviewed requirement IR, bindings, assumptions, review metadata, verification tasks, adapter results, generated tests, counterexamples, normalized traces, evidence, status, implementation specs, and reports.")
}

System_Ext(targetRepo, "Target project files", "Source, tests, API contracts, schema documents, command-check config, TLA models, and trace artifacts inspected by configured adapters.")
System_Ext(tooling, "External deterministic tools", "Pytest, Python interpreters, command-line checks, TLA checker commands, and Z3 used to produce bounded evidence results.")

Rel(operator, cli, "Runs phase-specific commands and supplies paths, requirement ids, policies, adapters, and output locations", "CLI arguments")
Rel(cli, core, "Parses controlled text, validates IR/package schemas, computes evidence objects, and decides pure status", "In-process Python calls")
Rel(cli, adapterLayer, "Constructs configured adapters and asks them to resolve symbols, validate bindings, generate tasks, and collect evidence", "Adapter interface")
Rel(cli, reporting, "Requests package indexes, CI reports, soft gates, hard gates, routing reports, continuous runs, trace reports, command results, and TLA result reports", "In-process Python calls")
Rel(cli, agentWorkflow, "Requests implementation tasks, verifier handoffs, PR comments, and audit entries", "In-process Python calls")
Rel(core, packageArtifacts, "Reads and writes package artifacts with stable JSON serialization and reviewed hashes", "File system")
Rel(adapterLayer, targetRepo, "Reads target artifacts needed for deterministic symbol discovery and evidence freshness checks", "File system")
Rel(adapterLayer, evidenceBackends, "Creates backend tasks and normalizes backend results into evidence claims", "Verification tasks")
Rel(evidenceBackends, tooling, "Executes bounded checks and captures exit codes, stdout, counterexamples, hashes, and timeouts", "Subprocess or library call")
Rel(reporting, packageArtifacts, "Loads package artifacts and emits report artifacts without mutating reviewed packages", "JSON and Markdown files")
Rel(agentWorkflow, packageArtifacts, "Reads package summaries and artifact hashes, then writes agent-specific workflow artifacts", "JSON and Markdown files")

@enduml
```

## Level 3 - Core Package Components

```plantuml
@startuml
!include https://raw.githubusercontent.com/plantuml-stdlib/C4-PlantUML/master/C4_Component.puml

LAYOUT_WITH_LEGEND()
title NL Requirement Attestation Layer - C4 Level 3 Core Package Components

Container_Boundary(core, "Requirement core container") {
  Component(parser, "Controlled-language parser", "Lark grammar and parser module", "Parses restricted natural-language requirements into deterministic AST and IR structures with normalized source spans.")
  Component(models, "Typed IR and artifact models", "Pydantic models", "Defines RequirementIR, claims, predicates, symbol bindings, verification tasks, backend results, evidence claims, reviews, traces, and status decisions.")
  Component(bindings, "Binding diagnostics", "Python binding module", "Builds symbol references from IR, calls the selected adapter, records resolved bindings, and separates unbound symbols from ambiguous symbols.")
  Component(packageBuilder, "Package builder", "Python package module", "Writes generic requirement packages with requirement markdown, source diff, IR, bindings, assumptions, review metadata, verification tasks, evidence, status, implementation spec, and SMT files.")
  Component(packageValidator, "Package validator", "Python validation module", "Reloads package artifacts, recomputes deterministic outputs, checks reviewed hashes, detects stale artifacts, and returns current IR, evidence, and status.")
  Component(evidenceAggregator, "Evidence aggregator", "Python evidence logic", "Combines static binding evidence, consistency checks, SMT checks, adapter task results, generated tests, traces, counterexamples, and unsupported claim metadata into EvidenceObject.")
  Component(statusDecision, "Pure status decision", "Python status module", "Maps evidence objects to deterministic final statuses without reading files, running tools, or depending on CI context.")
  Component(schemaGeneration, "Schema generation and drift guard", "Pydantic JSON Schema plus script", "Generates committed JSON schemas for package and auxiliary artifacts and checks schema drift in tests and CI.")
  Component(smtBackend, "Core consistency and SMT backend", "Python plus Z3", "Checks supported claim consistency and emits/checks SMT artifacts for adapter-neutral requirement shapes.")
}

ContainerDb(packageArtifacts, "Requirement package artifacts", "JSON, Markdown, and SMT files", "Reviewed artifact set used as the durable boundary between specification review, evidence validation, gate enforcement, and agent workflows.")
Container(adapterLayer, "Selected adapter", "Adapter interface implementation", "Configured adapter that resolves symbols and produces adapter-specific verification tasks for the target artifact.")

Rel(parser, models, "Creates typed IR objects with source-span provenance", "Pydantic validation")
Rel(packageBuilder, parser, "Parses controlled text supplied by CLI or tests", "Controlled text")
Rel(packageBuilder, bindings, "Requests symbol binding against the selected adapter before writing package artifacts", "SymbolRef list")
Rel(bindings, adapterLayer, "Resolves action, actor, target, value, event, state, or quantity references", "Adapter.resolve_symbols")
Rel(packageBuilder, evidenceAggregator, "Assembles evidence claims from static binding diagnostics and backend results", "Evidence inputs")
Rel(evidenceAggregator, smtBackend, "Runs consistency and SMT checks for supported claim shapes", "RequirementIR")
Rel(evidenceAggregator, statusDecision, "Provides complete EvidenceObject for pure status calculation", "EvidenceObject")
Rel(statusDecision, packageBuilder, "Returns accepted, refused, review, timeout, or needs-coverage status with reason and next actions", "StatusDecision")
Rel(packageBuilder, schemaGeneration, "Writes artifacts that must match committed schemas and stable serialization rules", "JSON artifacts")
Rel(packageBuilder, packageArtifacts, "Creates immutable package artifact set for review and future validation", "File writes")
Rel(packageValidator, packageArtifacts, "Reads reviewed package artifacts and validates freshness and integrity", "File reads")
Rel(packageValidator, bindings, "Recomputes current adapter bindings to detect stale or invalid binding artifacts", "RequirementIR without bindings")
Rel(packageValidator, evidenceAggregator, "Recomputes expected evidence from current task results and package content", "BackendResultsArtifact")
Rel(packageValidator, statusDecision, "Recomputes status from the validated evidence object", "EvidenceObject")
Rel(schemaGeneration, packageValidator, "Fails validation tests when committed schemas drift from typed models", "Schema drift check")

@enduml
```

## Level 3 - Adapter and Evidence Components

```plantuml
@startuml
!include https://raw.githubusercontent.com/plantuml-stdlib/C4-PlantUML/master/C4_Component.puml

LAYOUT_WITH_LEGEND()
title NL Requirement Attestation Layer - C4 Level 3 Adapter and Evidence Components

Container_Boundary(adapterLayer, "Adapter layer container") {
  Component(adapterInterface, "Adapter contract and conformance suite", "Python protocol and tests", "Defines required adapter methods for symbol resolution, binding validation, evidence capabilities, task generation, task execution, and result collection.")
  Component(genericAdapter, "Generic static-symbol adapter", "Python dictionary-backed adapter", "Reference adapter for Phase 0 that resolves known symbols, exposes ambiguity fixtures, and produces static symbol evidence.")
  Component(pythonAdapter, "Python package adapter", "Python AST/import inspection plus pytest/property tasks", "Indexes Python modules, functions, classes, and methods; validates symbols; creates symbol, pytest, and generated property tasks with source hashes.")
  Component(openapiAdapter, "OpenAPI adapter", "JSON/YAML declaration parser", "Indexes paths, operations, parameters, schemas, security schemes, auth metadata, state transitions, and response declarations for declaration-level API evidence.")
  Component(graphqlAdapter, "GraphQL schema adapter", "SDL subset parser", "Indexes GraphQL operations, fields, principals, auth metadata, state transitions, and response declarations for declaration-level schema evidence.")
  Component(jsonSchemaAdapter, "JSON Schema adapter", "JSON document parser", "Indexes schemas, reviewed actions, principals, properties, states, quantities, and numeric/state declaration metadata for payload and data contract evidence.")
  Component(asyncApiAdapter, "AsyncAPI adapter", "JSON AsyncAPI parser", "Indexes operations, channels, messages, events, principals, and reviewed event-emission metadata for event-contract evidence.")
  Component(commandAdapter, "Command/test-runner adapter", "Reviewed command runner", "Links requirements to explicit command checks, hashes target and test paths, runs bounded commands, and records TEST_VALIDATED evidence or counterexamples.")
  Component(traceValidator, "Runtime trace validator", "Normalized trace validator", "Validates supported runtime observations over normalized traces and records TRACE_VALIDATED results only for acceptable redaction and documented claim shapes.")
  Component(tlaAdapter, "TLA/model-checking adapter", "Model config plus checker command runner", "Links requirements to reviewed TLA models, records model/config hashes, runs bounded checker commands, and emits BOUNDED_CHECKED evidence or counterexamples.")
  Component(protobufAdapter, "Protobuf/gRPC adapter", "Deterministic .proto subset parser", "Indexes schemas, messages, fields, RPCs, principals, state transitions, and reviewed RPC-level options for declaration-level gRPC evidence.")
}

System_Ext(targetArtifacts, "Target artifacts", "Python code, tests, OpenAPI, GraphQL, JSON Schema, AsyncAPI, Protobuf, command checks, traces, and TLA models supplied by the repository.")
System_Ext(testAndModelTools, "Backend tools", "Pytest, Python interpreter, command-line tools, trace data, TLA checker commands, and Z3.")
ContainerDb(packageArtifacts, "Requirement package artifacts", "JSON and Markdown files", "Package artifacts that store bindings, tasks, backend results, counterexamples, traces, evidence, status, and review hashes.")

Rel(adapterInterface, genericAdapter, "Defines behavior validated by conformance tests", "Adapter API")
Rel(adapterInterface, pythonAdapter, "Defines behavior validated by Python conformance tests", "Adapter API")
Rel(adapterInterface, openapiAdapter, "Defines behavior validated by OpenAPI conformance tests", "Adapter API")
Rel(adapterInterface, graphqlAdapter, "Defines behavior validated by GraphQL conformance tests", "Adapter API")
Rel(adapterInterface, jsonSchemaAdapter, "Defines behavior validated by JSON Schema conformance tests", "Adapter API")
Rel(adapterInterface, asyncApiAdapter, "Defines behavior validated by AsyncAPI conformance tests", "Adapter API")
Rel(adapterInterface, commandAdapter, "Defines behavior validated by command adapter conformance tests", "Adapter API")
Rel(adapterInterface, tlaAdapter, "Defines behavior validated by TLA package and checker tests", "Adapter API")
Rel(adapterInterface, protobufAdapter, "Defines behavior validated by local Protobuf conformance tests", "Adapter API")

Rel(pythonAdapter, targetArtifacts, "Reads Python package source and test paths to index symbols and compute source/test hashes", "File system")
Rel(openapiAdapter, targetArtifacts, "Reads OpenAPI documents and resolves declaration-level operation/security/response symbols", "JSON or YAML")
Rel(graphqlAdapter, targetArtifacts, "Reads GraphQL SDL and resolves declaration-level operation/field symbols", "GraphQL SDL")
Rel(jsonSchemaAdapter, targetArtifacts, "Reads JSON Schema documents and resolves property/action/quantity symbols", "JSON Schema")
Rel(asyncApiAdapter, targetArtifacts, "Reads AsyncAPI documents and resolves operation/message/channel/event symbols", "JSON AsyncAPI")
Rel(commandAdapter, targetArtifacts, "Reads reviewed command-check configuration and target/test path hashes", "JSON config and files")
Rel(traceValidator, targetArtifacts, "Reads normalized trace artifacts and requirement package metadata", "JSON traces")
Rel(tlaAdapter, targetArtifacts, "Reads reviewed TLA model configuration, modules, and checker config files", "TLA files and JSON config")
Rel(protobufAdapter, targetArtifacts, "Reads .proto schemas and resolves declaration-level RPC/message/option symbols", "Protobuf schema")

Rel(pythonAdapter, testAndModelTools, "Runs scoped pytest and generated property tasks under deterministic task payload hashes", "Subprocess")
Rel(commandAdapter, testAndModelTools, "Runs reviewed command checks with timeout and expected exit code", "Subprocess")
Rel(tlaAdapter, testAndModelTools, "Runs model-checking command with reviewed bounds and expected exit code", "Subprocess")
Rel(traceValidator, packageArtifacts, "Compares observed trace events with supported requirement claims and package metadata", "Package and trace JSON")
Rel(adapterInterface, packageArtifacts, "Defines task, result, evidence, generated-test, counterexample, and trace artifact contracts stored by concrete adapters", "JSON artifact contract")

@enduml
```

## Dynamic View - Package, Validation, and Gate Flow

```plantuml
@startuml
!include https://raw.githubusercontent.com/plantuml-stdlib/C4-PlantUML/master/C4_Dynamic.puml

LAYOUT_WITH_LEGEND()
title NL Requirement Attestation Layer - Dynamic View Package and Gate Flow

Person(author, "Requirement author or CI job", "Provides controlled text, requirement metadata, adapter configuration, gate policy, and output paths.")
Container(cli, "nlreq CLI", "Python CLI", "Coordinates parsing, adapter selection, package generation, validation, reporting, gates, routing, and agent artifacts.")
Component(parser, "Controlled-language parser", "Lark parser", "Turns reviewed controlled text into deterministic AST and RequirementIR with source spans.")
Component(adapter, "Configured adapter", "Adapter interface implementation", "Resolves symbols, validates bindings, generates verification tasks, and normalizes backend results for the target artifact.")
Component(backends, "Evidence backends", "Core SMT, pytest, command runner, trace validator, TLA checker", "Execute deterministic checks and return backend results with hashes, evidence levels, failures, timeouts, and counterexamples.")
Component(status, "Pure status decision", "Python status module", "Calculates the final package status from the EvidenceObject only.")
ContainerDb(pkg, "Requirement package artifacts", "JSON, Markdown, SMT files", "Durable reviewed package artifacts used by validation, gates, reports, continuous attestation, routing, and agent workflows.")
Component(gates, "Reports, gates, routing, and agents", "Python report builders", "Revalidate packages, classify findings, enforce soft or hard gates, route adapters, emit continuous reports, and produce agent tasks or handoffs.")
Person(reviewer, "Reviewer or verifier", "Reviews package status, evidence, gate findings, retry payloads, and audit entries.")

Rel(author, cli, "Runs package or adapter-specific package command with controlled text and reviewed metadata", "CLI")
Rel(cli, parser, "Parses controlled requirement and validates claim kind", "Controlled text")
Rel(cli, adapter, "Requests deterministic symbol resolution and task generation for configured target", "Adapter API")
Rel(adapter, backends, "Runs adapter-specific or core verification tasks with stable input hashes", "VerificationTask payloads")
Rel(backends, cli, "Returns normalized backend results, counterexamples, timeouts, and achieved evidence levels", "BackendResult list")
Rel(cli, status, "Builds EvidenceObject and asks for pure status decision", "EvidenceObject")
Rel(status, cli, "Returns accepted, refused, review-needed, timeout, or needs-coverage status", "StatusDecision")
Rel(cli, pkg, "Writes package artifacts with reviewed hashes and stable serialization", "File system")
Rel(gates, pkg, "Reloads packages and recomputes validation against current adapters and policies", "File system")
Rel(cli, gates, "Runs package-index, CI, soft-gate, hard-gate, continuous, routing, trace, command, TLA, and agent workflows", "CLI command dispatch")
Rel(gates, reviewer, "Presents findings, summaries, retry payloads, and audit metadata for review", "JSON and Markdown")
Rel(reviewer, cli, "Reruns validation or requests follow-up package, gate, trace, command, TLA, or agent artifacts", "CLI")

@enduml
```

## Rendering

Render the PlantUML blocks with any C4-PlantUML-compatible renderer. The
diagrams intentionally keep the rendered boxes descriptive, so they are more
verbose than thumbnail architecture sketches.
