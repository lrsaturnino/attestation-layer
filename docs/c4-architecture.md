# C4 Architecture Diagrams

These diagrams describe the current NL Requirement Attestation Layer
implementation in this worktree. They cover phases 0 through 17, including the
Phase 17 Protobuf/gRPC adapter.

The diagrams follow the C4 model (system context, containers, components, and a
dynamic view) and are drawn as Mermaid flowcharts so they render inline on
GitHub. Each element box shows a name, its element type and technology where
relevant, and a description; fill colors distinguish people, systems,
containers, components, datastores, and external systems; and each relationship
has a precise label.

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

```mermaid
flowchart TB
    reviewer["Human reviewer<br/>Person<br/>Reviews controlled requirements, assumptions, bindings, generated package artifacts, gate findings, and agent handoff summaries before accepting evidence."]:::person
    specifier["Specifier or requirement author<br/>Person<br/>Writes controlled natural-language requirements and supplies requirement ids, claim kinds, titles, assumptions, and reviewed adapter metadata."]:::person
    coderAgent["Coder agent<br/>Person<br/>Consumes implementation tasks and package constraints, changes implementation files, and must not mutate reviewed package artifacts."]:::person
    verifierAgent["Verifier agent<br/>Person<br/>Consumes verifier handoffs, gate reports, retry payloads, and package hashes to decide whether implementation work is ready for review."]:::person

    subgraph attestationBoundary["NL Requirement Attestation Layer"]
        attestation["Attestation Layer CLI and library<br/>System<br/>Deterministic Python implementation that parses controlled requirements, binds symbols through adapters, runs evidence backends, emits reviewed package artifacts, and produces adoption, gate, routing, continuous-attestation, and agent workflow reports."]:::system
    end

    targetRepo["Target project repository<br/>External system<br/>Implementation source, tests, OpenAPI/GraphQL/JSON Schema/AsyncAPI/Protobuf contracts, TLA models, command-check configuration, and normalized runtime traces that adapters inspect."]:::external
    ciSystem["CI or scheduled automation<br/>External system<br/>Runs attestation commands in shadow, soft-gate, hard-gate, continuous, routing, command-evidence, and trace-validation workflows."]:::external
    packageStore["Requirement package directory<br/>External system<br/>File-system directory containing reviewed immutable package artifacts such as IR, bindings, assumptions, review, tasks, adapter results, evidence, status, traces, counterexamples, and implementation specs."]:::external
    externalTools["External verification tools<br/>External system<br/>Pytest, generated Python property checks, bounded command runners, custom TLA checker commands, and Z3-backed SMT checks used as deterministic evidence backends."]:::external

    specifier -->|"Submits controlled requirements and adapter configuration to create or refresh packages (CLI)"| attestation
    reviewer -->|"Runs validation, reviews reports, and accepts or rejects evidence decisions (CLI and Markdown/JSON)"| attestation
    coderAgent -->|"Requests implementation tasks with requirement constraints and immutable package hashes (JSON artifact)"| attestation
    verifierAgent -->|"Requests verifier handoffs with gate findings, retry payloads, and continuous-attestation context (JSON and Markdown artifacts)"| attestation
    ciSystem -->|"Executes report, gate, routing, trace, command, TLA, and continuous workflows on repository changes or schedules (CLI)"| attestation
    attestation -->|"Reads source files, tests, API contracts, models, command configs, and trace artifacts without trusting them as reviewed specs (File system)"| targetRepo
    attestation -->|"Writes and validates reviewed requirement package artifacts with stable hashes and status decisions (JSON and Markdown files)"| packageStore
    attestation -->|"Invokes deterministic evidence backends and records bounded results, hashes, failures, and counterexamples (Subprocess or library call)"| externalTools
    ciSystem -->|"Publishes reports and package snapshots for review and audit (Artifacts)"| packageStore

    classDef person fill:#08427b,stroke:#052e56,color:#ffffff
    classDef system fill:#1168bd,stroke:#0b4884,color:#ffffff
    classDef external fill:#8b8b8b,stroke:#5f5f5f,color:#ffffff
```

## Level 2 - Containers

```mermaid
flowchart TB
    operator["Operator, reviewer, CI, or agent<br/>Person<br/>Runs commands and consumes JSON/Markdown artifacts for specification review, CI reporting, gates, routing, continuous attestation, and agent workflows."]:::person

    subgraph attestationBoundary["NL Requirement Attestation Layer"]
        cli["nlreq CLI<br/>Container: Python argparse command-line application<br/>Single command surface for parsing, packaging, validating, conformance, adapters, gates, routing, continuous attestation, trace validation, command evidence, TLA checks, and agent artifacts."]:::container
        core["Requirement core<br/>Container: Python library<br/>Adapter-neutral parser, IR model, source-span provenance, binding diagnostics, package integrity validation, evidence aggregation, pure status decisions, and JSON schema generation."]:::container
        adapterLayer["Adapter layer<br/>Container: Python adapter implementations<br/>Deterministic adapter interface and concrete adapters for generic symbols, Python packages, OpenAPI, GraphQL, JSON Schema, AsyncAPI, command checks, runtime traces, TLA models, and local Protobuf/gRPC."]:::container
        evidenceBackends["Evidence backends<br/>Container: Python, Z3, subprocess tools<br/>Core SMT checks, self-consistency checks, pytest execution, generated property checks, command execution, runtime trace validation, and TLA/model-checking command execution."]:::container
        reporting["Reporting and gates<br/>Container: Python report builders<br/>Builds package indexes, CI shadow reports, soft gates, hard gates, routing reports, continuous attestation reports, trace validation reports, command result reports, and TLA result reports."]:::container
        agentWorkflow["Agent workflow artifacts<br/>Container: Python JSON/Markdown emitters<br/>Creates implementation task payloads, verifier handoffs, PR-comment Markdown, and append-only audit entries for specifier, coder, verifier, and reviewer roles."]:::container
        packageArtifacts["Requirement packages and reports<br/>Container (datastore): JSON and Markdown files<br/>Durable artifact set containing reviewed requirement IR, bindings, assumptions, review metadata, verification tasks, adapter results, generated tests, counterexamples, normalized traces, evidence, status, implementation specs, and reports."]:::containerDb
    end

    targetRepo["Target project files<br/>External system<br/>Source, tests, API contracts, schema documents, command-check config, TLA models, and trace artifacts inspected by configured adapters."]:::external
    tooling["External deterministic tools<br/>External system<br/>Pytest, Python interpreters, command-line checks, TLA checker commands, and Z3 used to produce bounded evidence results."]:::external

    operator -->|"Runs phase-specific commands and supplies paths, requirement ids, policies, adapters, and output locations (CLI arguments)"| cli
    cli -->|"Parses controlled text, validates IR/package schemas, computes evidence objects, and decides pure status (In-process Python calls)"| core
    cli -->|"Constructs configured adapters and asks them to resolve symbols, validate bindings, generate tasks, and collect evidence (Adapter interface)"| adapterLayer
    cli -->|"Requests package indexes, CI reports, soft gates, hard gates, routing reports, continuous runs, trace reports, command results, and TLA result reports (In-process Python calls)"| reporting
    cli -->|"Requests implementation tasks, verifier handoffs, PR comments, and audit entries (In-process Python calls)"| agentWorkflow
    core -->|"Reads and writes package artifacts with stable JSON serialization and reviewed hashes (File system)"| packageArtifacts
    adapterLayer -->|"Reads target artifacts needed for deterministic symbol discovery and evidence freshness checks (File system)"| targetRepo
    adapterLayer -->|"Creates backend tasks and normalizes backend results into evidence claims (Verification tasks)"| evidenceBackends
    evidenceBackends -->|"Executes bounded checks and captures exit codes, stdout, counterexamples, hashes, and timeouts (Subprocess or library call)"| tooling
    reporting -->|"Loads package artifacts and emits report artifacts without mutating reviewed packages (JSON and Markdown files)"| packageArtifacts
    agentWorkflow -->|"Reads package summaries and artifact hashes, then writes agent-specific workflow artifacts (JSON and Markdown files)"| packageArtifacts

    classDef person fill:#08427b,stroke:#052e56,color:#ffffff
    classDef system fill:#1168bd,stroke:#0b4884,color:#ffffff
    classDef container fill:#438dd5,stroke:#2a6496,color:#ffffff
    classDef containerDb fill:#2e6da4,stroke:#1d4a70,color:#ffffff
    classDef component fill:#4b9bea,stroke:#2f74b5,color:#ffffff
    classDef external fill:#8b8b8b,stroke:#5f5f5f,color:#ffffff
```

## Level 3 - Core Package Components

```mermaid
flowchart TB
    subgraph coreBoundary["Requirement core container"]
        parser["Controlled-language parser<br/>Component: Lark grammar and parser module<br/>Parses restricted natural-language requirements into deterministic AST and IR structures with normalized source spans."]:::component
        models["Typed IR and artifact models<br/>Component: Pydantic models<br/>Defines RequirementIR, claims, predicates, symbol bindings, verification tasks, backend results, evidence claims, reviews, traces, and status decisions."]:::component
        bindings["Binding diagnostics<br/>Component: Python binding module<br/>Builds symbol references from IR, calls the selected adapter, records resolved bindings, and separates unbound symbols from ambiguous symbols."]:::component
        packageBuilder["Package builder<br/>Component: Python package module<br/>Writes generic requirement packages with requirement markdown, source diff, IR, bindings, assumptions, review metadata, verification tasks, evidence, status, implementation spec, and SMT files."]:::component
        packageValidator["Package validator<br/>Component: Python validation module<br/>Reloads package artifacts, recomputes deterministic outputs, checks reviewed hashes, detects stale artifacts, and returns current IR, evidence, and status."]:::component
        evidenceAggregator["Evidence aggregator<br/>Component: Python evidence logic<br/>Combines static binding evidence, consistency checks, SMT checks, adapter task results, generated tests, traces, counterexamples, and unsupported claim metadata into EvidenceObject."]:::component
        statusDecision["Pure status decision<br/>Component: Python status module<br/>Maps evidence objects to deterministic final statuses without reading files, running tools, or depending on CI context."]:::component
        schemaGeneration["Schema generation and drift guard<br/>Component: Pydantic JSON Schema plus script<br/>Generates committed JSON schemas for package and auxiliary artifacts and checks schema drift in tests and CI."]:::component
        smtBackend["Core consistency and SMT backend<br/>Component: Python plus Z3<br/>Checks supported claim consistency and emits/checks SMT artifacts for adapter-neutral requirement shapes."]:::component
    end

    packageArtifacts["Requirement package artifacts<br/>Container (datastore): JSON, Markdown, and SMT files<br/>Reviewed artifact set used as the durable boundary between specification review, evidence validation, gate enforcement, and agent workflows."]:::containerDb
    adapterLayer["Selected adapter<br/>Container: Adapter interface implementation<br/>Configured adapter that resolves symbols and produces adapter-specific verification tasks for the target artifact."]:::container

    parser -->|"Creates typed IR objects with source-span provenance (Pydantic validation)"| models
    packageBuilder -->|"Parses controlled text supplied by CLI or tests (Controlled text)"| parser
    packageBuilder -->|"Requests symbol binding against the selected adapter before writing package artifacts (SymbolRef list)"| bindings
    bindings -->|"Resolves action, actor, target, value, event, state, or quantity references (Adapter.resolve_symbols)"| adapterLayer
    packageBuilder -->|"Assembles evidence claims from static binding diagnostics and backend results (Evidence inputs)"| evidenceAggregator
    evidenceAggregator -->|"Runs consistency and SMT checks for supported claim shapes (RequirementIR)"| smtBackend
    evidenceAggregator -->|"Provides complete EvidenceObject for pure status calculation (EvidenceObject)"| statusDecision
    statusDecision -->|"Returns accepted, refused, review, timeout, or needs-coverage status with reason and next actions (StatusDecision)"| packageBuilder
    packageBuilder -->|"Writes artifacts that must match committed schemas and stable serialization rules (JSON artifacts)"| schemaGeneration
    packageBuilder -->|"Creates immutable package artifact set for review and future validation (File writes)"| packageArtifacts
    packageValidator -->|"Reads reviewed package artifacts and validates freshness and integrity (File reads)"| packageArtifacts
    packageValidator -->|"Recomputes current adapter bindings to detect stale or invalid binding artifacts (RequirementIR without bindings)"| bindings
    packageValidator -->|"Recomputes expected evidence from current task results and package content (BackendResultsArtifact)"| evidenceAggregator
    packageValidator -->|"Recomputes status from the validated evidence object (EvidenceObject)"| statusDecision
    schemaGeneration -->|"Fails validation tests when committed schemas drift from typed models (Schema drift check)"| packageValidator

    classDef person fill:#08427b,stroke:#052e56,color:#ffffff
    classDef system fill:#1168bd,stroke:#0b4884,color:#ffffff
    classDef container fill:#438dd5,stroke:#2a6496,color:#ffffff
    classDef containerDb fill:#2e6da4,stroke:#1d4a70,color:#ffffff
    classDef component fill:#4b9bea,stroke:#2f74b5,color:#ffffff
    classDef external fill:#8b8b8b,stroke:#5f5f5f,color:#ffffff
```

## Level 3 - Adapter and Evidence Components

```mermaid
flowchart TB
    subgraph adapterBoundary["Adapter layer container"]
        adapterInterface["Adapter contract and conformance suite<br/>Component: Python protocol and tests<br/>Defines required adapter methods for symbol resolution, binding validation, evidence capabilities, task generation, task execution, and result collection."]:::component
        genericAdapter["Generic static-symbol adapter<br/>Component: Python dictionary-backed adapter<br/>Reference adapter for Phase 0 that resolves known symbols, exposes ambiguity fixtures, and produces static symbol evidence."]:::component
        pythonAdapter["Python package adapter<br/>Component: Python AST/import inspection plus pytest/property tasks<br/>Indexes Python modules, functions, classes, and methods; validates symbols; creates symbol, pytest, and generated property tasks with source hashes."]:::component
        openapiAdapter["OpenAPI adapter<br/>Component: JSON/YAML declaration parser<br/>Indexes paths, operations, parameters, schemas, security schemes, auth metadata, state transitions, and response declarations for declaration-level API evidence."]:::component
        graphqlAdapter["GraphQL schema adapter<br/>Component: SDL subset parser<br/>Indexes GraphQL operations, fields, principals, auth metadata, state transitions, and response declarations for declaration-level schema evidence."]:::component
        jsonSchemaAdapter["JSON Schema adapter<br/>Component: JSON document parser<br/>Indexes schemas, reviewed actions, principals, properties, states, quantities, and numeric/state declaration metadata for payload and data contract evidence."]:::component
        asyncApiAdapter["AsyncAPI adapter<br/>Component: JSON AsyncAPI parser<br/>Indexes operations, channels, messages, events, principals, and reviewed event-emission metadata for event-contract evidence."]:::component
        commandAdapter["Command/test-runner adapter<br/>Component: Reviewed command runner<br/>Links requirements to explicit command checks, hashes target and test paths, runs bounded commands, and records TEST_VALIDATED evidence or counterexamples."]:::component
        traceValidator["Runtime trace validator<br/>Component: Normalized trace validator<br/>Validates supported runtime observations over normalized traces and records TRACE_VALIDATED results only for acceptable redaction and documented claim shapes."]:::component
        tlaAdapter["TLA/model-checking adapter<br/>Component: Model config plus checker command runner<br/>Links requirements to reviewed TLA models, records model/config hashes, runs bounded checker commands, and emits BOUNDED_CHECKED evidence or counterexamples."]:::component
        protobufAdapter["Protobuf/gRPC adapter<br/>Component: Deterministic .proto subset parser<br/>Indexes schemas, messages, fields, RPCs, principals, state transitions, and reviewed RPC-level options for declaration-level gRPC evidence."]:::component
    end

    targetArtifacts["Target artifacts<br/>External system<br/>Python code, tests, OpenAPI, GraphQL, JSON Schema, AsyncAPI, Protobuf, command checks, traces, and TLA models supplied by the repository."]:::external
    testAndModelTools["Backend tools<br/>External system<br/>Pytest, Python interpreter, command-line tools, trace data, TLA checker commands, and Z3."]:::external
    packageArtifacts["Requirement package artifacts<br/>Container (datastore): JSON and Markdown files<br/>Package artifacts that store bindings, tasks, backend results, counterexamples, traces, evidence, status, and review hashes."]:::containerDb

    adapterInterface -->|"Defines behavior validated by conformance tests (Adapter API)"| genericAdapter
    adapterInterface -->|"Defines behavior validated by Python conformance tests (Adapter API)"| pythonAdapter
    adapterInterface -->|"Defines behavior validated by OpenAPI conformance tests (Adapter API)"| openapiAdapter
    adapterInterface -->|"Defines behavior validated by GraphQL conformance tests (Adapter API)"| graphqlAdapter
    adapterInterface -->|"Defines behavior validated by JSON Schema conformance tests (Adapter API)"| jsonSchemaAdapter
    adapterInterface -->|"Defines behavior validated by AsyncAPI conformance tests (Adapter API)"| asyncApiAdapter
    adapterInterface -->|"Defines behavior validated by command adapter conformance tests (Adapter API)"| commandAdapter
    adapterInterface -->|"Defines behavior validated by TLA package and checker tests (Adapter API)"| tlaAdapter
    adapterInterface -->|"Defines behavior validated by local Protobuf conformance tests (Adapter API)"| protobufAdapter

    pythonAdapter -->|"Reads Python package source and test paths to index symbols and compute source/test hashes (File system)"| targetArtifacts
    openapiAdapter -->|"Reads OpenAPI documents and resolves declaration-level operation/security/response symbols (JSON or YAML)"| targetArtifacts
    graphqlAdapter -->|"Reads GraphQL SDL and resolves declaration-level operation/field symbols (GraphQL SDL)"| targetArtifacts
    jsonSchemaAdapter -->|"Reads JSON Schema documents and resolves property/action/quantity symbols (JSON Schema)"| targetArtifacts
    asyncApiAdapter -->|"Reads AsyncAPI documents and resolves operation/message/channel/event symbols (JSON AsyncAPI)"| targetArtifacts
    commandAdapter -->|"Reads reviewed command-check configuration and target/test path hashes (JSON config and files)"| targetArtifacts
    traceValidator -->|"Reads normalized trace artifacts and requirement package metadata (JSON traces)"| targetArtifacts
    tlaAdapter -->|"Reads reviewed TLA model configuration, modules, and checker config files (TLA files and JSON config)"| targetArtifacts
    protobufAdapter -->|"Reads .proto schemas and resolves declaration-level RPC/message/option symbols (Protobuf schema)"| targetArtifacts

    pythonAdapter -->|"Runs scoped pytest and generated property tasks under deterministic task payload hashes (Subprocess)"| testAndModelTools
    commandAdapter -->|"Runs reviewed command checks with timeout and expected exit code (Subprocess)"| testAndModelTools
    tlaAdapter -->|"Runs model-checking command with reviewed bounds and expected exit code (Subprocess)"| testAndModelTools
    traceValidator -->|"Compares observed trace events with supported requirement claims and package metadata (Package and trace JSON)"| packageArtifacts
    adapterInterface -->|"Defines task, result, evidence, generated-test, counterexample, and trace artifact contracts stored by concrete adapters (JSON artifact contract)"| packageArtifacts

    classDef person fill:#08427b,stroke:#052e56,color:#ffffff
    classDef system fill:#1168bd,stroke:#0b4884,color:#ffffff
    classDef container fill:#438dd5,stroke:#2a6496,color:#ffffff
    classDef containerDb fill:#2e6da4,stroke:#1d4a70,color:#ffffff
    classDef component fill:#4b9bea,stroke:#2f74b5,color:#ffffff
    classDef external fill:#8b8b8b,stroke:#5f5f5f,color:#ffffff
```

## Dynamic View - Package, Validation, and Gate Flow

```mermaid
flowchart TB
    author["Requirement author or CI job<br/>Person<br/>Provides controlled text, requirement metadata, adapter configuration, gate policy, and output paths."]:::person
    cli["nlreq CLI<br/>Container: Python CLI<br/>Coordinates parsing, adapter selection, package generation, validation, reporting, gates, routing, and agent artifacts."]:::container
    parser["Controlled-language parser<br/>Component: Lark parser<br/>Turns reviewed controlled text into deterministic AST and RequirementIR with source spans."]:::component
    adapter["Configured adapter<br/>Component: Adapter interface implementation<br/>Resolves symbols, validates bindings, generates verification tasks, and normalizes backend results for the target artifact."]:::component
    backends["Evidence backends<br/>Component: Core SMT, pytest, command runner, trace validator, TLA checker<br/>Execute deterministic checks and return backend results with hashes, evidence levels, failures, timeouts, and counterexamples."]:::component
    status["Pure status decision<br/>Component: Python status module<br/>Calculates the final package status from the EvidenceObject only."]:::component
    pkg["Requirement package artifacts<br/>Container (datastore): JSON, Markdown, SMT files<br/>Durable reviewed package artifacts used by validation, gates, reports, continuous attestation, routing, and agent workflows."]:::containerDb
    gates["Reports, gates, routing, and agents<br/>Component: Python report builders<br/>Revalidate packages, classify findings, enforce soft or hard gates, route adapters, emit continuous reports, and produce agent tasks or handoffs."]:::component
    reviewer["Reviewer or verifier<br/>Person<br/>Reviews package status, evidence, gate findings, retry payloads, and audit entries."]:::person

    author -->|"1. Runs package or adapter-specific package command with controlled text and reviewed metadata (CLI)"| cli
    cli -->|"2. Parses controlled requirement and validates claim kind (Controlled text)"| parser
    cli -->|"3. Requests deterministic symbol resolution and task generation for configured target (Adapter API)"| adapter
    adapter -->|"4. Runs adapter-specific or core verification tasks with stable input hashes (VerificationTask payloads)"| backends
    backends -->|"5. Returns normalized backend results, counterexamples, timeouts, and achieved evidence levels (BackendResult list)"| cli
    cli -->|"6. Builds EvidenceObject and asks for pure status decision (EvidenceObject)"| status
    status -->|"7. Returns accepted, refused, review-needed, timeout, or needs-coverage status (StatusDecision)"| cli
    cli -->|"8. Writes package artifacts with reviewed hashes and stable serialization (File system)"| pkg
    gates -->|"9. Reloads packages and recomputes validation against current adapters and policies (File system)"| pkg
    cli -->|"10. Runs package-index, CI, soft-gate, hard-gate, continuous, routing, trace, command, TLA, and agent workflows (CLI command dispatch)"| gates
    gates -->|"11. Presents findings, summaries, retry payloads, and audit metadata for review (JSON and Markdown)"| reviewer
    reviewer -->|"12. Reruns validation or requests follow-up package, gate, trace, command, TLA, or agent artifacts (CLI)"| cli

    classDef person fill:#08427b,stroke:#052e56,color:#ffffff
    classDef system fill:#1168bd,stroke:#0b4884,color:#ffffff
    classDef container fill:#438dd5,stroke:#2a6496,color:#ffffff
    classDef containerDb fill:#2e6da4,stroke:#1d4a70,color:#ffffff
    classDef component fill:#4b9bea,stroke:#2f74b5,color:#ffffff
    classDef external fill:#8b8b8b,stroke:#5f5f5f,color:#ffffff
```

## Rendering

Render the Mermaid blocks with any Mermaid-compatible renderer such as GitHub,
the Mermaid Live Editor, or the Mermaid CLI. The diagrams use the stable
flowchart syntax with `subgraph` boundaries and `classDef` colors for C4
element types, which renders inline on GitHub (unlike Mermaid's experimental
native C4 diagram types). The diagrams intentionally keep the rendered boxes
descriptive, so they are more verbose than thumbnail architecture sketches.
