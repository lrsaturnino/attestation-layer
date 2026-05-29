from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .adapter import Adapter
from .jsonutil import sha256_json, sha256_text
from .models import (
    BackendResult,
    EvidenceCapability,
    EvidenceLevel,
    RequirementIR,
    Symbol,
    SymbolBinding,
    SymbolRef,
    SymbolResolution,
    ValidationResult,
    VerificationTask,
)


OPERATION_TYPES = {"Query", "Mutation", "Subscription"}
AUTH_DIRECTIVES = {"auth", "authenticated", "requiresAuth", "requires_auth"}
STATE_CHANGE_DIRECTIVES = {"stateChange", "state_change", "changesState"}


@dataclass(frozen=True)
class GraphQlField:
    parent_type: str
    name: str
    return_type: str
    directives: dict[str, dict[str, str]]


class GraphQlAdapter(Adapter):
    adapter_id = "graphql"
    target_kind = "graphql_schema"

    def __init__(self, schema_path: Path, *, schema_name: str | None = None) -> None:
        self.schema_path = Path(schema_path)
        if not self.schema_path.is_file():
            raise ValueError(f"GraphQL schema does not exist: {self.schema_path}")
        self.schema_text = self.schema_path.read_text()
        self.schema_hash = sha256_text(self.schema_text)
        self.schema_name = schema_name or self.schema_path.stem
        self._fields = _parse_graphql_fields(self.schema_text)
        self._symbols = _build_symbol_index(self._fields, self.schema_name, self.schema_hash)
        self._symbols_by_name = _index_symbols(self._symbols)

    def resolve_symbols(self, refs: list[SymbolRef]) -> list[SymbolResolution]:
        return [self._resolve_symbol(ref) for ref in refs]

    def validate_binding(self, binding: SymbolBinding) -> ValidationResult:
        if binding.adapter != self.adapter_id:
            return ValidationResult(
                valid=False,
                reason=f"binding adapter mismatch: expected {self.adapter_id}, found {binding.adapter}",
            )
        candidates = self._symbols_by_name.get(binding.symbol, [])
        if not candidates:
            return ValidationResult(valid=False, reason="binding symbol not found")
        if not any(symbol.symbol_type == binding.symbol_type for symbol in candidates):
            found = ", ".join(sorted({symbol.symbol_type for symbol in candidates}))
            return ValidationResult(
                valid=False,
                reason=f"binding type mismatch: expected {binding.symbol_type}, found {found}",
            )
        return ValidationResult(valid=True)

    def available_evidence(self, symbols: list[Symbol]) -> list[EvidenceCapability]:
        if not symbols:
            return []
        return [
            EvidenceCapability(
                evidence_level=EvidenceLevel.STATICALLY_RESOLVED,
                description="GraphQL symbol exists in the parsed schema.",
            ),
            EvidenceCapability(
                evidence_level=EvidenceLevel.TYPE_CHECKED,
                description="GraphQL operation, return type, directive, and state-change declarations are parsed.",
            ),
        ]

    def generate_tasks(self, ir: RequirementIR) -> list[VerificationTask]:
        bindings = [
            {
                "requirement_ref": name,
                "symbol": binding.symbol,
                "symbol_type": binding.symbol_type,
            }
            for name, binding in sorted(ir.bindings.items())
            if binding.adapter == self.adapter_id
        ]
        symbol_payload = {
            "adapter": self.adapter_id,
            "schema": self.schema_name,
            "schema_path": self.schema_path.as_posix(),
            "schema_hash": self.schema_hash,
            "requirement_id": ir.requirement_id,
            "task": "symbol_shape",
            "bindings": bindings,
        }
        tasks = [
            VerificationTask(
                id="GRAPHQL-SYMBOLS",
                backend="adapter",
                description=f"Validate GraphQL symbol bindings for {ir.requirement_id}.",
                input_hash=sha256_json(symbol_payload),
                payload=symbol_payload,
            )
        ]
        claim_task = self._claim_task_for_ir(ir)
        if claim_task is not None:
            tasks.append(claim_task)
        return tasks

    def collect_evidence(self, task_results: list[object]) -> list[BackendResult]:
        collected: list[BackendResult] = []
        for result in task_results:
            if isinstance(result, BackendResult):
                collected.append(result)
                continue
            if isinstance(result, dict):
                collected.append(BackendResult.model_validate(result))
                continue
            raise TypeError(f"unsupported GraphQL adapter task result: {type(result).__name__}")
        return collected

    def run_task(self, task: VerificationTask) -> BackendResult:
        task_kind = task.payload.get("task")
        if task_kind == "symbol_shape":
            return self._run_symbol_shape_task(task)
        if task_kind == "auth_rejection":
            return self._run_auth_rejection_task(task)
        if task_kind == "success_response":
            return self._run_success_response_task(task)
        return BackendResult(
            backend=self.adapter_id,
            status="unsupported",
            details={"task_id": task.id, "task": task_kind},
        )

    def symbols(self) -> list[Symbol]:
        return sorted(self._symbols, key=_symbol_sort_key)

    def _resolve_symbol(self, ref: SymbolRef) -> SymbolResolution:
        exact_candidates = list(self._symbols_by_name.get(ref.name, []))
        candidates = [
            symbol for symbol in exact_candidates if _matches_expected_type(symbol, ref.expected_type)
        ]
        if not candidates and ref.name == "actor":
            candidates = [
                symbol
                for symbol in self._symbols
                if symbol.symbol_type == "principal"
                and _matches_expected_type(symbol, ref.expected_type)
            ]
        candidates = sorted(candidates, key=_symbol_sort_key)
        if not candidates:
            if exact_candidates:
                found = ", ".join(sorted({symbol.symbol_type for symbol in exact_candidates}))
                return SymbolResolution(
                    ref=ref,
                    status="unresolved",
                    reason=f"expected {ref.expected_type}, found {found}",
                )
            return SymbolResolution(ref=ref, status="unresolved", reason="symbol not found")
        if len(candidates) > 1:
            return SymbolResolution(
                ref=ref,
                status="ambiguous",
                symbols=candidates,
                reason="multiple GraphQL symbols matched",
            )
        return SymbolResolution(ref=ref, status="resolved", symbols=candidates)

    def _claim_task_for_ir(self, ir: RequirementIR) -> VerificationTask | None:
        if _is_auth_rejection_claim(ir):
            operation = ir.bindings.get(ir.claim.action)
            if operation is None or operation.adapter != self.adapter_id:
                return None
            actor_ref = _first_condition_arg(ir, "not_authorized")
            payload = {
                "adapter": self.adapter_id,
                "schema": self.schema_name,
                "schema_path": self.schema_path.as_posix(),
                "schema_hash": self.schema_hash,
                "requirement_id": ir.requirement_id,
                "task": "auth_rejection",
                "operation": ir.claim.action,
                "operation_symbol": operation.symbol,
                "required_auth_directives": sorted(AUTH_DIRECTIVES),
            }
            if actor_ref:
                payload["actor"] = actor_ref
                actor = ir.bindings.get(actor_ref)
                if actor is not None and actor.adapter == self.adapter_id:
                    payload["actor_symbol"] = actor.symbol
            if ir.claim.expected.target:
                payload["state_transition"] = ir.claim.expected.target
                transition = ir.bindings.get(ir.claim.expected.target)
                if transition is not None and transition.adapter == self.adapter_id:
                    payload["state_transition_symbol"] = transition.symbol
            return VerificationTask(
                id="GRAPHQL-AUTH-REJECTION",
                backend="adapter",
                description=f"Validate GraphQL auth and state-change declarations for {ir.requirement_id}.",
                input_hash=sha256_json(payload),
                payload=payload,
            )

        if _is_success_response_claim(ir):
            operation = ir.bindings.get(ir.claim.action)
            if operation is None or operation.adapter != self.adapter_id:
                return None
            payload = {
                "adapter": self.adapter_id,
                "schema": self.schema_name,
                "schema_path": self.schema_path.as_posix(),
                "schema_hash": self.schema_hash,
                "requirement_id": ir.requirement_id,
                "task": "success_response",
                "operation": ir.claim.action,
                "operation_symbol": operation.symbol,
            }
            return VerificationTask(
                id="GRAPHQL-SUCCESS-RESPONSE",
                backend="adapter",
                description=f"Validate GraphQL operation return shape for {ir.requirement_id}.",
                input_hash=sha256_json(payload),
                payload=payload,
            )
        return None

    def _run_symbol_shape_task(self, task: VerificationTask) -> BackendResult:
        invalid: list[dict[str, str]] = []
        bindings = task.payload.get("bindings", [])
        if not isinstance(bindings, list):
            return BackendResult(
                backend=self.adapter_id,
                status="invalid",
                evidence_level=EvidenceLevel.TYPE_CHECKED,
                details=_task_details(task, reason="bindings payload must be a list"),
            )
        for raw in bindings:
            if not isinstance(raw, dict):
                invalid.append({"symbol": "<invalid>", "reason": "binding payload must be an object"})
                continue
            symbol_name = str(raw.get("symbol", ""))
            expected_type = str(raw.get("symbol_type", ""))
            candidates = self._symbols_by_name.get(symbol_name, [])
            if not candidates:
                invalid.append({"symbol": symbol_name, "reason": "symbol not found"})
                continue
            if not any(symbol.symbol_type == expected_type for symbol in candidates):
                found = ", ".join(sorted({symbol.symbol_type for symbol in candidates}))
                invalid.append(
                    {
                        "symbol": symbol_name,
                        "reason": f"expected {expected_type}, found {found}",
                    }
                )
        return BackendResult(
            backend=self.adapter_id,
            status="invalid" if invalid else "valid",
            evidence_level=EvidenceLevel.TYPE_CHECKED,
            details={
                **_task_details(task),
                "validated_bindings": len(bindings) - len(invalid),
                "invalid_bindings": invalid,
                "schema_hash": self.schema_hash,
            },
        )

    def _run_auth_rejection_task(self, task: VerificationTask) -> BackendResult:
        operation = self._symbol_named(task.payload.get("operation_symbol"), "action")
        if operation is None:
            return _invalid_graphql_result(task, "operation_symbol does not resolve to an action")
        directives = operation.metadata.get("directives", {})
        if not isinstance(directives, dict):
            directives = {}
        auth_directives = sorted(set(directives).intersection(AUTH_DIRECTIVES))
        transition_symbol = task.payload.get("state_transition_symbol")
        transition_valid = True
        if "state_transition" in task.payload:
            transition = self._symbol_named(transition_symbol, "state_transition")
            operation_symbol = str(operation.metadata.get("alias_for") or operation.name)
            transition_valid = (
                transition is not None
                and transition.metadata.get("operation_symbol") == operation_symbol
            )

        problems: list[str] = []
        if not auth_directives:
            problems.append("operation does not declare an auth directive")
        if not transition_valid:
            problems.append("state transition binding does not belong to the operation")

        return BackendResult(
            backend=self.adapter_id,
            status="invalid" if problems else "valid",
            evidence_level=EvidenceLevel.STATICALLY_RESOLVED,
            details={
                **_task_details(task),
                "operation_symbol": operation.name,
                "auth_directives": auth_directives,
                "state_transition_symbol": transition_symbol,
                "schema_hash": self.schema_hash,
                "problems": problems,
            },
        )

    def _run_success_response_task(self, task: VerificationTask) -> BackendResult:
        operation = self._symbol_named(task.payload.get("operation_symbol"), "action")
        if operation is None:
            return _invalid_graphql_result(task, "operation_symbol does not resolve to an action")
        return_type = str(operation.metadata.get("return_type") or "")
        problems = [] if return_type else ["operation does not declare a return type"]
        return BackendResult(
            backend=self.adapter_id,
            status="invalid" if problems else "valid",
            evidence_level=EvidenceLevel.STATICALLY_RESOLVED,
            details={
                **_task_details(task),
                "operation_symbol": operation.name,
                "return_type": return_type,
                "schema_hash": self.schema_hash,
                "problems": problems,
            },
        )

    def _symbol_named(self, value: object, symbol_type: str) -> Symbol | None:
        if not isinstance(value, str):
            return None
        for symbol in self._symbols_by_name.get(value, []):
            if symbol.symbol_type == symbol_type:
                return symbol
        return None


def supported_graphql_claim(ir: RequirementIR) -> bool:
    return _is_auth_rejection_claim(ir) or _is_success_response_claim(ir)


def _parse_graphql_fields(schema_text: str) -> list[GraphQlField]:
    fields: list[GraphQlField] = []
    text = _strip_graphql_comments(schema_text)
    for type_match in re.finditer(
        r"\b(type|interface)\s+([A-Za-z_][A-Za-z0-9_]*)[^{]*\{(?P<body>.*?)\}",
        text,
        flags=re.DOTALL,
    ):
        parent_type = type_match.group(2)
        for line in type_match.group("body").splitlines():
            line = line.strip().rstrip(",")
            if not line or line.startswith("@"):
                continue
            field = _parse_graphql_field(parent_type, line)
            if field is not None:
                fields.append(field)
    if not fields:
        raise ValueError("GraphQL schema contains no parseable type or interface fields")
    return fields


def _parse_graphql_field(parent_type: str, line: str) -> GraphQlField | None:
    match = re.match(
        r"^(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*(?:\([^)]*\))?\s*:\s*(?P<return>[!\[\]A-Za-z_][!\[\]A-Za-z0-9_]*)\s*(?P<directives>.*)$",
        line,
    )
    if not match:
        return None
    return GraphQlField(
        parent_type=parent_type,
        name=match.group("name"),
        return_type=match.group("return"),
        directives=_parse_directives(match.group("directives")),
    )


def _parse_directives(text: str) -> dict[str, dict[str, str]]:
    directives: dict[str, dict[str, str]] = {}
    for match in re.finditer(r"@([A-Za-z_][A-Za-z0-9_]*)(?:\(([^)]*)\))?", text):
        directives[match.group(1)] = _parse_directive_args(match.group(2) or "")
    return directives


def _parse_directive_args(text: str) -> dict[str, str]:
    args: dict[str, str] = {}
    for match in re.finditer(
        r"([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(?:\"([^\"]*)\"|([A-Za-z_][A-Za-z0-9_]*))",
        text,
    ):
        args[match.group(1)] = match.group(2) if match.group(2) is not None else match.group(3)
    return args


def _build_symbol_index(
    fields: list[GraphQlField],
    schema_name: str,
    schema_hash: str,
) -> list[Symbol]:
    symbols: list[Symbol] = [
        Symbol(
            name=schema_name,
            symbol_type="graphql_schema",
            metadata={"kind": "graphql_schema", "schema_hash": schema_hash},
        )
    ]
    auth_seen = False
    for field in fields:
        if field.parent_type in OPERATION_TYPES:
            operation_symbol = f"{field.parent_type}.{field.name}"
            metadata = {
                "kind": "operation",
                "operation_type": field.parent_type,
                "field": field.name,
                "return_type": field.return_type,
                "directives": field.directives,
            }
            symbols.append(Symbol(name=operation_symbol, symbol_type="action", metadata=metadata))
            if operation_symbol != field.name:
                symbols.append(
                    Symbol(
                        name=field.name,
                        symbol_type="action",
                        metadata={**metadata, "alias_for": operation_symbol},
                    )
                )
            if set(field.directives).intersection(AUTH_DIRECTIVES) and not auth_seen:
                symbols.append(
                    Symbol(
                        name="actor",
                        symbol_type="principal",
                        metadata={
                            "kind": "auth_principal",
                            "operation_symbol": operation_symbol,
                            "directives": sorted(set(field.directives).intersection(AUTH_DIRECTIVES)),
                        },
                    )
                )
                auth_seen = True
            for transition_name in _state_transition_names(field):
                symbols.append(
                    Symbol(
                        name=transition_name,
                        symbol_type="state_transition",
                        metadata={
                            "kind": "state_transition",
                            "operation_symbol": operation_symbol,
                            "field": field.name,
                        },
                    )
                )
        else:
            symbols.append(
                Symbol(
                    name=f"{field.parent_type}.{field.name}",
                    symbol_type="field",
                    metadata={
                        "kind": "field",
                        "parent_type": field.parent_type,
                        "return_type": field.return_type,
                        "directives": field.directives,
                    },
                )
            )
    return sorted(symbols, key=_symbol_sort_key)


def _state_transition_names(field: GraphQlField) -> list[str]:
    names: list[str] = []
    for directive_name, args in field.directives.items():
        if directive_name not in STATE_CHANGE_DIRECTIVES:
            continue
        for key in ("name", "target", "event", "transition"):
            if key in args:
                names.append(args[key])
                break
        else:
            names.append(f"{field.name}_state_change")
    return sorted(set(names))


def _index_symbols(symbols: list[Symbol]) -> dict[str, list[Symbol]]:
    indexed: dict[str, list[Symbol]] = {}
    for symbol in symbols:
        indexed.setdefault(symbol.name, []).append(symbol)
    return {key: sorted(value, key=_symbol_sort_key) for key, value in indexed.items()}


def _task_details(task: VerificationTask, **extra: Any) -> dict[str, Any]:
    return {
        "task_id": task.id,
        "task_input_hash": task.input_hash,
        "schema": task.payload.get("schema"),
        "schema_path": task.payload.get("schema_path"),
        "schema_hash": task.payload.get("schema_hash"),
        **extra,
    }


def _invalid_graphql_result(task: VerificationTask, reason: str) -> BackendResult:
    return BackendResult(
        backend="graphql",
        status="invalid",
        evidence_level=EvidenceLevel.STATICALLY_RESOLVED,
        details=_task_details(task, reason=reason),
    )


def _is_auth_rejection_claim(ir: RequirementIR) -> bool:
    return (
        ir.claim.kind == "authorization_precondition"
        and ir.claim.expected.kind == "rejected_before"
        and any(predicate.op == "not_authorized" for predicate in ir.claim.condition)
    )


def _is_success_response_claim(ir: RequirementIR) -> bool:
    return ir.claim.expected.kind == "succeed"


def _first_condition_arg(ir: RequirementIR, op: str) -> str | None:
    for predicate in ir.claim.condition:
        if predicate.op != op:
            continue
        for arg in predicate.args:
            if arg.kind == "identifier":
                return str(arg.value)
    return None


def _matches_expected_type(symbol: Symbol, expected_type: str | None) -> bool:
    if expected_type is None:
        return True
    if symbol.symbol_type == expected_type:
        return True
    if expected_type == "action" and symbol.symbol_type == "action":
        return True
    return False


def _symbol_sort_key(symbol: Symbol) -> tuple[str, str]:
    return (symbol.name, symbol.symbol_type)


def _strip_graphql_comments(text: str) -> str:
    return "\n".join(line.split("#", 1)[0] for line in text.splitlines())
