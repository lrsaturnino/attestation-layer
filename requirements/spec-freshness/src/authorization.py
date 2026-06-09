"""Covered source module for the spec-freshness CI demo (PC-12).

This is a small, stable, domain-neutral authorization helper whose behavior the reviewed system spec
``specs/Authorization.tla`` describes. The spec-freshness gate (``nlreq spec-freshness-check``, wired
into CI) records this file's hash in ``lockfile.json``; editing this module without re-baselining the
lockfile makes the gate block, the Cargo.lock-style staleness PC-12 enforces. Keep edits here in lock
step with a regenerated lockfile, exactly as a real covered module would require a re-validated spec.
"""

from __future__ import annotations


# The grants table the spec's safety property is stated over: an action is authorized for a role only
# when that role has been granted it. Changing this table changes the module's behavior, so the
# reviewed spec must be re-validated against the new behavior before the freshness gate clears.
_GRANTS: dict[str, frozenset[str]] = {
    "approver": frozenset({"approve", "view"}),
    "viewer": frozenset({"view"}),
}


def is_authorized(role: str, action: str) -> bool:
    """Return whether ``role`` is authorized to perform ``action``.

    A request is authorized only when the role has been granted the action; an unknown role or an
    ungranted action is never authorized. This is the behavior the reviewed spec's
    ``AuthorizedOnlyWhenGranted`` invariant constrains.
    """
    return action in _GRANTS.get(role, frozenset())
