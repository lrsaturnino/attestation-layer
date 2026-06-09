"""Self-contained Slither analysis driver, executed under Slither's own interpreter.

Slither is installed in its own environment (e.g. a pipx venv) and is not importable from the
project environment, so :mod:`nlreq.slither_client` runs this file as a subprocess with the
interpreter that *does* have Slither. The file therefore imports ONLY ``slither`` and the standard
library — never anything from ``nlreq``.

It compiles each target with Slither's real analysis engine and emits, between sentinel markers on
stdout, a JSON inventory of every contract/function/event/modifier (inheritance-resolved, with
overload-distinguishing signatures and source locations) plus the real internal/external call
edges. The sentinel markers let the client recover the JSON even when Slither logs warnings to
stdout. On any failure it emits an ``error`` payload and exits non-zero so the client falls back to
static resolution.
"""

from __future__ import annotations

import json
import sys
import traceback


JSON_BEGIN = "===NLREQ_SLITHER_JSON_BEGIN==="
JSON_END = "===NLREQ_SLITHER_JSON_END==="


def _slither_version():
    try:
        from importlib.metadata import version

        return version("slither-analyzer")
    except Exception:
        return None


def _source_span(element):
    mapping = getattr(element, "source_mapping", None)
    if mapping is None:
        return None, None, None
    filename = getattr(mapping, "filename", None)
    name = None
    if filename is not None:
        name = getattr(filename, "short", None) or getattr(filename, "used", None)
    return name, getattr(mapping, "start", None), getattr(mapping, "length", None)


def _callee_function(internal_call):
    # Across Slither versions an internal call is either a Function or an operation carrying one.
    return getattr(internal_call, "function", None) or internal_call


def _add_symbol(symbols, key_set, *, name, kind, signature, container, declarer, visibility, element):
    file, start, length = _source_span(element)
    key = (kind, container, signature, file, start)
    if key in key_set:
        return
    key_set.add(key)
    symbols.append(
        {
            "name": name,
            "kind": kind,
            "signature": signature,
            "container": container,
            "declarer": declarer,
            "visibility": visibility,
            "file": file,
            "start": start,
            "length": length,
        }
    )


def _analyze(targets):
    from slither import Slither

    symbols: list[dict] = []
    symbol_keys: set = set()
    edges: list[dict] = []
    edge_keys: set = set()
    files: set = set()

    for target in targets:
        slither = Slither(target)
        for contract in slither.contracts:
            contract_file, contract_start, contract_length = _source_span(contract)
            if contract_file:
                files.add(contract_file)
            kind = "contract"
            if getattr(contract, "is_interface", False):
                kind = "interface"
            elif getattr(contract, "is_library", False):
                kind = "library"
            _add_symbol(
                symbols,
                symbol_keys,
                name=contract.name,
                kind=kind,
                signature=contract.name,
                container=None,
                declarer=contract.name,
                visibility=None,
                element=contract,
            )
            for function in contract.functions:
                declarer = getattr(function, "contract_declarer", None)
                _add_symbol(
                    symbols,
                    symbol_keys,
                    name=function.name,
                    kind="function",
                    signature=function.full_name,
                    container=contract.name,
                    declarer=declarer.name if declarer else contract.name,
                    visibility=getattr(function, "visibility", None),
                    element=function,
                )
            for modifier in getattr(contract, "modifiers", []):
                declarer = getattr(modifier, "contract_declarer", None)
                _add_symbol(
                    symbols,
                    symbol_keys,
                    name=modifier.name,
                    kind="modifier",
                    signature=modifier.full_name,
                    container=contract.name,
                    declarer=declarer.name if declarer else contract.name,
                    visibility=getattr(modifier, "visibility", None),
                    element=modifier,
                )
            for event in getattr(contract, "events", []):
                # Use the event's true declaring contract so an event inherited by several contracts
                # collapses to one definition (not one false duplicate per deriving contract).
                event_declarer = getattr(getattr(event, "contract", None), "name", None)
                _add_symbol(
                    symbols,
                    symbol_keys,
                    name=event.name,
                    kind="event",
                    signature=event.full_name,
                    container=contract.name,
                    declarer=event_declarer or contract.name,
                    visibility=None,
                    element=event,
                )
            # Real call edges, attributed in the analyzing contract's context (so an inherited
            # call surfaces under the deriving contract, resolved to the base that declares it).
            for function in contract.functions:
                caller_file, _, _ = _source_span(function)
                for internal_call in getattr(function, "internal_calls", []):
                    callee = _callee_function(internal_call)
                    callee_signature = getattr(callee, "full_name", None) or getattr(
                        callee, "name", None
                    )
                    if not callee_signature:
                        continue
                    callee_declarer = getattr(callee, "contract_declarer", None)
                    callee_file, _, _ = _source_span(callee)
                    edge = {
                        "caller_contract": contract.name,
                        "caller_signature": function.full_name,
                        "caller_file": caller_file,
                        "callee_contract": callee_declarer.name if callee_declarer else None,
                        "callee_signature": callee_signature,
                        "callee_name": getattr(callee, "name", callee_signature),
                        "callee_file": callee_file,
                        "kind": "internal",
                    }
                    key = (
                        edge["caller_contract"],
                        edge["caller_signature"],
                        edge["callee_contract"],
                        edge["callee_signature"],
                    )
                    if key not in edge_keys:
                        edge_keys.add(key)
                        edges.append(edge)
                for high_level in getattr(function, "high_level_calls", []):
                    # high_level_calls entries are (contract, function/var) tuples across versions.
                    callee = None
                    callee_contract = None
                    if isinstance(high_level, (tuple, list)) and high_level:
                        callee_contract = getattr(high_level[0], "name", None)
                        callee = high_level[-1]
                    callee_signature = getattr(callee, "full_name", None) or getattr(
                        callee, "name", None
                    )
                    if not callee_signature:
                        continue
                    callee_file, _, _ = _source_span(callee)
                    edge = {
                        "caller_contract": contract.name,
                        "caller_signature": function.full_name,
                        "caller_file": caller_file,
                        "callee_contract": callee_contract,
                        "callee_signature": callee_signature,
                        "callee_name": getattr(callee, "name", callee_signature),
                        "callee_file": callee_file,
                        "kind": "external",
                    }
                    key = (
                        edge["caller_contract"],
                        edge["caller_signature"],
                        edge["callee_contract"],
                        edge["callee_signature"],
                    )
                    if key not in edge_keys:
                        edge_keys.add(key)
                        edges.append(edge)

    return {
        "slither_version": _slither_version(),
        "files": sorted(files),
        "symbols": symbols,
        "edges": edges,
    }


def main(argv: list[str]) -> int:
    if not argv:
        print(JSON_BEGIN)
        print(json.dumps({"error": "no targets supplied"}))
        print(JSON_END)
        return 1
    try:
        payload = _analyze(argv)
    except Exception as exc:  # surfaced to the client as a fallback signal
        print(JSON_BEGIN)
        print(
            json.dumps(
                {"error": f"{type(exc).__name__}: {exc}", "traceback": traceback.format_exc()}
            )
        )
        print(JSON_END)
        return 1
    print(JSON_BEGIN)
    print(json.dumps(payload))
    print(JSON_END)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
