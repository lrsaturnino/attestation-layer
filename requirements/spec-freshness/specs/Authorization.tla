---- MODULE Authorization ----
\* Reviewed system spec S for the `authorization` covered module (PC-12 spec-freshness CI demo).
\* Safety property: a request is authorized only when its action has been granted to its role —
\* `authorized => granted`. The freshness gate records this file's hash alongside the source's; a
\* source edit that the spec has not been re-validated against makes the gate block.
VARIABLE authorized, granted

AuthorizedOnlyWhenGranted == authorized => granted

====
