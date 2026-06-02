# ADR 0084: CI/PR Action Gate, Report-Only Adoption, And Hard-Gate Policy

## Status

Proposed

## Context

The closure gate must integrate with normal PR workflows.

## Decision

Add a CI/PR gate report with report-only, soft-gate, and hard-gate modes. The
JSON report is authoritative; Markdown is derived.

## Consequences

Repositories can adopt in report-only mode before blocking merges.

## Validation

`nlreq ci-pr-gate` renders JSON and Markdown from end-to-end gate reports.
