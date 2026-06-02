# ADR 0077: Go Adapter Scope, Tooling, And Runtime Trace Semantics

## Status

Proposed

## Context

The adapter model needs a compiled service ecosystem.

## Decision

Add a Go source adapter using static function, method, and type extraction plus
normalized trace consumption.

## Consequences

Go can participate in certification and cross-language proof objects while
future gopls/runtime-trace integrations remain adapter-local.

## Validation

The shared adapter certification suite applies to Go manifests.
