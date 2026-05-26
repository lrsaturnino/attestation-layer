# Examples

Committed requirement packages live under `requirements/`.

| Requirement | Claim Kind | Status | Purpose |
|---|---|---|---|
| `REQ-AUTH-001` | `authorization_precondition` | `ACCEPTED_WITH_EVIDENCE` | Unauthorized operation is rejected before state changes. |
| `REQ-STATE-001` | `state_postcondition` | `ACCEPTED_WITH_EVIDENCE` | Approved operation sets accepted status. |
| `REQ-NUM-001` | `numeric_invariant` | `ACCEPTED_WITH_EVIDENCE` | Counter increments within limit. |
| `REQ-REFUSED-UNBOUND-001` | `authorization_precondition` | `REFUSED_UNBOUND_SYMBOLS` | Negative fixture for refusal provenance. |

Validate all committed examples:

```bash
uv run nlreq validate-all requirements
```

Build an adoption index:

```bash
uv run nlreq package-index requirements
```

Build a shadow CI report:

```bash
uv run nlreq ci-report requirements
```

Run the soft gate against an accepted package:

```bash
uv run nlreq soft-gate requirements --requirement-id REQ-AUTH-001
```

Run the soft gate against the refused negative fixture:

```bash
uv run nlreq soft-gate requirements --requirement-id REQ-REFUSED-UNBOUND-001
```
