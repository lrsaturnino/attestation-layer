from __future__ import annotations

import json
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


HTTP_METHODS = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}
REJECTION_STATUSES = ("401", "403")


class OpenApiAdapter(Adapter):
    adapter_id = "openapi"
    target_kind = "openapi_document"

    def __init__(self, document_path: Path, *, document_name: str | None = None) -> None:
        self.document_path = Path(document_path)
        if not self.document_path.is_file():
            raise ValueError(f"OpenAPI document does not exist: {self.document_path}")
        self.document_text = self.document_path.read_text()
        self.document_hash = sha256_text(self.document_text)
        self.document = _load_openapi_document(self.document_path, self.document_text)
        self.document_name = document_name or self.document_path.stem
        self._symbols = _build_symbol_index(self.document, self.document_name)
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
                description="OpenAPI symbol exists in the parsed document.",
            ),
            EvidenceCapability(
                evidence_level=EvidenceLevel.TYPE_CHECKED,
                description="OpenAPI path, operation, parameter, schema, and security shape is validated.",
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
            "document": self.document_name,
            "document_path": self.document_path.as_posix(),
            "document_hash": self.document_hash,
            "requirement_id": ir.requirement_id,
            "task": "symbol_shape",
            "bindings": bindings,
        }
        tasks = [
            VerificationTask(
                id="OPENAPI-SYMBOLS",
                backend="adapter",
                description=f"Validate OpenAPI symbol bindings for {ir.requirement_id}.",
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
            raise TypeError(f"unsupported OpenAPI adapter task result: {type(result).__name__}")
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
        candidates = exact_candidates
        if not candidates and ref.name == "actor":
            candidates = [
                symbol
                for symbol in self._symbols
                if symbol.metadata.get("kind") == "security_scheme"
            ]
        candidates = [
            symbol for symbol in candidates if _matches_expected_type(symbol, ref.expected_type)
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
            if ref.name == "actor":
                return SymbolResolution(
                    ref=ref,
                    status="unresolved",
                    reason="no OpenAPI security scheme can represent actor",
                )
            return SymbolResolution(ref=ref, status="unresolved", reason="symbol not found")
        if len(candidates) > 1:
            return SymbolResolution(
                ref=ref,
                status="ambiguous",
                symbols=candidates,
                reason="multiple OpenAPI symbols matched",
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
                "document": self.document_name,
                "document_path": self.document_path.as_posix(),
                "document_hash": self.document_hash,
                "requirement_id": ir.requirement_id,
                "task": "auth_rejection",
                "operation": ir.claim.action,
                "operation_symbol": operation.symbol,
                "expected_rejection_statuses": list(REJECTION_STATUSES),
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
                id="OPENAPI-AUTH-REJECTION",
                backend="adapter",
                description=f"Validate OpenAPI security and rejection responses for {ir.requirement_id}.",
                input_hash=sha256_json(payload),
                payload=payload,
            )

        if _is_success_response_claim(ir):
            operation = ir.bindings.get(ir.claim.action)
            if operation is None or operation.adapter != self.adapter_id:
                return None
            actor_ref = _first_condition_arg(ir, "approved")
            payload = {
                "adapter": self.adapter_id,
                "document": self.document_name,
                "document_path": self.document_path.as_posix(),
                "document_hash": self.document_hash,
                "requirement_id": ir.requirement_id,
                "task": "success_response",
                "operation": ir.claim.action,
                "operation_symbol": operation.symbol,
                "expected_success_status_class": "2xx",
            }
            if actor_ref:
                payload["actor"] = actor_ref
                actor = ir.bindings.get(actor_ref)
                if actor is not None and actor.adapter == self.adapter_id:
                    payload["actor_symbol"] = actor.symbol
            return VerificationTask(
                id="OPENAPI-SUCCESS-RESPONSE",
                backend="adapter",
                description=f"Validate OpenAPI success response declarations for {ir.requirement_id}.",
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
                "document_hash": self.document_hash,
            },
        )

    def _run_auth_rejection_task(self, task: VerificationTask) -> BackendResult:
        operation = self._symbol_named(task.payload.get("operation_symbol"), "action")
        if operation is None:
            return _invalid_openapi_result(task, "operation_symbol does not resolve to an action")
        actor_symbol = task.payload.get("actor_symbol")
        actor_scheme = str(actor_symbol) if isinstance(actor_symbol, str) else ""
        security = _security_requirements(operation)
        security_schemes = _security_scheme_names(security)
        responses = _response_statuses(operation)
        rejection_responses = [status for status in responses if status in REJECTION_STATUSES]
        transition_valid = True
        transition_symbol = task.payload.get("state_transition_symbol")
        if "state_transition" in task.payload:
            transition = self._symbol_named(transition_symbol, "state_transition")
            transition_valid = (
                transition is not None
                and transition.metadata.get("path") == operation.metadata.get("path")
                and transition.metadata.get("method") == operation.metadata.get("method")
            )

        problems: list[str] = []
        if not actor_scheme:
            problems.append("actor_symbol is missing")
        elif actor_scheme not in security_schemes:
            problems.append(f"operation security does not reference {actor_scheme}")
        if not rejection_responses:
            problems.append("operation does not declare a 401 or 403 response")
        if not transition_valid:
            problems.append("state transition binding does not belong to the operation")

        return BackendResult(
            backend=self.adapter_id,
            status="invalid" if problems else "valid",
            evidence_level=EvidenceLevel.STATICALLY_RESOLVED,
            details={
                **_task_details(task),
                "operation_symbol": operation.name,
                "security_schemes": security_schemes,
                "actor_symbol": actor_scheme or None,
                "rejection_responses": rejection_responses,
                "state_transition_symbol": transition_symbol,
                "document_hash": self.document_hash,
                "problems": problems,
            },
        )

    def _run_success_response_task(self, task: VerificationTask) -> BackendResult:
        operation = self._symbol_named(task.payload.get("operation_symbol"), "action")
        if operation is None:
            return _invalid_openapi_result(task, "operation_symbol does not resolve to an action")
        responses = _response_statuses(operation)
        success_responses = [status for status in responses if _is_success_status(status)]
        actor_symbol = task.payload.get("actor_symbol")
        actor_scheme = str(actor_symbol) if isinstance(actor_symbol, str) else ""
        security_schemes = _security_scheme_names(_security_requirements(operation))

        problems: list[str] = []
        if not success_responses:
            problems.append("operation does not declare a 2xx response")
        if "actor" in task.payload:
            if not actor_scheme:
                problems.append("actor_symbol is missing")
            elif actor_scheme not in security_schemes:
                problems.append(f"operation security does not reference {actor_scheme}")

        return BackendResult(
            backend=self.adapter_id,
            status="invalid" if problems else "valid",
            evidence_level=EvidenceLevel.STATICALLY_RESOLVED,
            details={
                **_task_details(task),
                "operation_symbol": operation.name,
                "security_schemes": security_schemes,
                "actor_symbol": actor_scheme or None,
                "success_responses": success_responses,
                "document_hash": self.document_hash,
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


def supported_openapi_claim(ir: RequirementIR) -> bool:
    return _is_auth_rejection_claim(ir) or _is_success_response_claim(ir)


def _load_openapi_document(path: Path, text: str) -> dict[str, Any]:
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as json_exc:
        if path.suffix.lower() not in {".yaml", ".yml"}:
            raise ValueError(f"OpenAPI document must be valid JSON: {json_exc}") from json_exc
        raw = _parse_simple_yaml(text)
    if not isinstance(raw, dict):
        raise ValueError("OpenAPI document root must be an object")
    if "openapi" not in raw:
        raise ValueError("OpenAPI document is missing the openapi version field")
    if not isinstance(raw.get("paths"), dict):
        raise ValueError("OpenAPI document paths must be an object")
    return raw


def _build_symbol_index(document: dict[str, Any], document_name: str) -> list[Symbol]:
    symbols: list[Symbol] = []
    _add_symbol(
        symbols,
        name=document_name,
        symbol_type="api_document",
        metadata={"kind": "api_document", "openapi": str(document.get("openapi", ""))},
    )

    components = document.get("components", {})
    if isinstance(components, dict):
        schemas = components.get("schemas", {})
        if isinstance(schemas, dict):
            for name, schema in sorted(schemas.items()):
                _add_symbol(
                    symbols,
                    name=str(name),
                    symbol_type="schema",
                    metadata={
                        "kind": "component_schema",
                        "schema_type": schema.get("type") if isinstance(schema, dict) else None,
                    },
                )
        security_schemes = components.get("securitySchemes", {})
        if isinstance(security_schemes, dict):
            for name, scheme in sorted(security_schemes.items()):
                metadata = {"kind": "security_scheme"}
                if isinstance(scheme, dict):
                    metadata.update(
                        {
                            "scheme_type": scheme.get("type"),
                            "scheme": scheme.get("scheme"),
                            "in": scheme.get("in"),
                        }
                    )
                _add_symbol(symbols, name=str(name), symbol_type="principal", metadata=metadata)

    paths = document["paths"]
    global_security = _normalise_security(document.get("security"))
    for path, path_item in sorted(paths.items()):
        if not isinstance(path_item, dict):
            continue
        path_text = str(path)
        _add_symbol(
            symbols,
            name=path_text,
            symbol_type="path",
            metadata={"kind": "path", "path": path_text},
        )
        path_parameters = _parameters(path_item.get("parameters"))
        for method, operation in sorted(path_item.items()):
            if method not in HTTP_METHODS or not isinstance(operation, dict):
                continue
            operation_id = operation.get("operationId")
            operation_name = str(operation_id) if isinstance(operation_id, str) and operation_id else (
                f"{method.upper()} {path_text}"
            )
            operation_metadata = {
                "kind": "operation",
                "operation_id": operation_name,
                "method": method.upper(),
                "path": path_text,
                "responses": _response_keys(operation.get("responses")),
                "security": _normalise_security(
                    operation["security"] if "security" in operation else global_security
                ),
                "security_source": "operation" if "security" in operation else "global",
            }
            _add_symbol(
                symbols,
                name=operation_name,
                symbol_type="action",
                metadata=operation_metadata,
            )
            method_path_name = f"{method.upper()} {path_text}"
            if method_path_name != operation_name:
                _add_symbol(
                    symbols,
                    name=method_path_name,
                    symbol_type="action",
                    metadata={**operation_metadata, "alias_for": operation_name},
                )
            for parameter in [*path_parameters, *_parameters(operation.get("parameters"))]:
                _add_parameter_symbol(symbols, parameter, method.upper(), path_text, operation_name)
            request_refs = _schema_refs_from_request_body(operation.get("requestBody"))
            if request_refs:
                _add_symbol(
                    symbols,
                    name=f"{operation_name}.request",
                    symbol_type="request_schema",
                    metadata={
                        "kind": "request_schema",
                        "operation": operation_name,
                        "method": method.upper(),
                        "path": path_text,
                        "schema_refs": request_refs,
                    },
                )
            for status, refs in _response_schema_refs(operation.get("responses")).items():
                _add_symbol(
                    symbols,
                    name=f"{operation_name}.response.{status}",
                    symbol_type="response_schema",
                    metadata={
                        "kind": "response_schema",
                        "operation": operation_name,
                        "method": method.upper(),
                        "path": path_text,
                        "status": status,
                        "schema_refs": refs,
                    },
                )
            for transition in _state_transition_names(operation):
                _add_symbol(
                    symbols,
                    name=transition,
                    symbol_type="state_transition",
                    metadata={
                        "kind": "state_transition",
                        "operation": operation_name,
                        "method": method.upper(),
                        "path": path_text,
                    },
                )
    return sorted(symbols, key=_symbol_sort_key)


def _add_parameter_symbol(
    symbols: list[Symbol],
    parameter: dict[str, Any],
    method: str,
    path: str,
    operation_name: str,
) -> None:
    name = parameter.get("name")
    if not isinstance(name, str) or not name:
        return
    _add_symbol(
        symbols,
        name=name,
        symbol_type="parameter",
        metadata={
            "kind": "parameter",
            "operation": operation_name,
            "method": method,
            "path": path,
            "in": parameter.get("in"),
            "required": bool(parameter.get("required", False)),
        },
    )


def _add_symbol(
    symbols: list[Symbol],
    *,
    name: str,
    symbol_type: str,
    metadata: dict[str, Any],
) -> None:
    symbols.append(
        Symbol(
            name=name,
            symbol_type=symbol_type,
            metadata={key: value for key, value in metadata.items() if value is not None},
        )
    )


def _index_symbols(symbols: list[Symbol]) -> dict[str, list[Symbol]]:
    indexed: dict[str, list[Symbol]] = {}
    for symbol in symbols:
        indexed.setdefault(symbol.name, []).append(symbol)
    return {name: sorted(values, key=_symbol_sort_key) for name, values in indexed.items()}


def _symbol_sort_key(symbol: Symbol) -> tuple[str, str, str, str]:
    return (
        symbol.name,
        symbol.symbol_type,
        str(symbol.metadata.get("path", "")),
        str(symbol.metadata.get("method", "")),
    )


def _matches_expected_type(symbol: Symbol, expected_type: str | None) -> bool:
    if expected_type is None:
        return True
    if symbol.symbol_type == expected_type:
        return True
    if expected_type == "action" and symbol.symbol_type == "operation":
        return True
    return False


def _parameters(raw: object) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


def _response_keys(raw: object) -> list[str]:
    if not isinstance(raw, dict):
        return []
    return sorted(str(key) for key in raw)


def _normalise_security(raw: object) -> list[dict[str, list[str]]]:
    if not isinstance(raw, list):
        return []
    requirements: list[dict[str, list[str]]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        requirement: dict[str, list[str]] = {}
        for name, scopes in sorted(item.items()):
            if isinstance(scopes, list):
                requirement[str(name)] = [str(scope) for scope in scopes]
            else:
                requirement[str(name)] = []
        requirements.append(requirement)
    return requirements


def _security_requirements(operation: Symbol) -> list[dict[str, list[str]]]:
    raw = operation.metadata.get("security", [])
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


def _security_scheme_names(security: list[dict[str, list[str]]]) -> list[str]:
    names = sorted({str(name) for requirement in security for name in requirement})
    return names


def _response_statuses(operation: Symbol) -> list[str]:
    raw = operation.metadata.get("responses", [])
    if not isinstance(raw, list):
        return []
    return [str(status) for status in raw]


def _is_success_status(status: str) -> bool:
    normalized = status.upper()
    return (len(normalized) == 3 and normalized.startswith("2") and normalized[1:].isdigit()) or (
        len(normalized) == 3 and normalized[0] == "2" and normalized[1:] == "XX"
    )


def _schema_refs_from_request_body(raw: object) -> list[str]:
    if not isinstance(raw, dict):
        return []
    return _schema_refs_from_content(raw.get("content"))


def _response_schema_refs(raw: object) -> dict[str, list[str]]:
    if not isinstance(raw, dict):
        return {}
    refs: dict[str, list[str]] = {}
    for status, response in sorted(raw.items()):
        if not isinstance(response, dict):
            continue
        schema_refs = _schema_refs_from_content(response.get("content"))
        if schema_refs:
            refs[str(status)] = schema_refs
    return refs


def _schema_refs_from_content(raw: object) -> list[str]:
    if not isinstance(raw, dict):
        return []
    refs: list[str] = []
    for media in raw.values():
        if isinstance(media, dict):
            refs.extend(_schema_refs(media.get("schema")))
    return sorted(set(refs))


def _schema_refs(raw: object) -> list[str]:
    if not isinstance(raw, dict):
        return []
    refs: list[str] = []
    ref = raw.get("$ref")
    if isinstance(ref, str):
        refs.append(ref.rsplit("/", 1)[-1])
    for key in ("items", "allOf", "anyOf", "oneOf"):
        value = raw.get(key)
        if isinstance(value, dict):
            refs.extend(_schema_refs(value))
        if isinstance(value, list):
            for item in value:
                refs.extend(_schema_refs(item))
    return refs


def _state_transition_names(operation: dict[str, Any]) -> list[str]:
    raw = operation.get("x-nlreq-state-transition")
    if isinstance(raw, str) and raw:
        return [raw]
    raw_many = operation.get("x-nlreq-state-transitions")
    if isinstance(raw_many, list):
        return sorted(str(item) for item in raw_many if isinstance(item, str) and item)
    return []


def _is_auth_rejection_claim(ir: RequirementIR) -> bool:
    return ir.claim.expected.kind in {"rejected", "rejected_before"} and any(
        predicate.op == "not_authorized" for predicate in ir.claim.condition
    )


def _is_success_response_claim(ir: RequirementIR) -> bool:
    return ir.claim.expected.kind == "succeed" and any(
        predicate.op == "approved" for predicate in ir.claim.condition
    )


def _first_condition_arg(ir: RequirementIR, predicate_op: str) -> str | None:
    for predicate in ir.claim.condition:
        if predicate.op != predicate_op:
            continue
        for arg in predicate.args:
            if arg.kind == "identifier":
                return str(arg.value)
    return None


def _task_details(task: VerificationTask, **extra: object) -> dict[str, object]:
    return {
        "task_id": task.id,
        "task_input_hash": task.input_hash,
        **extra,
    }


def _invalid_openapi_result(task: VerificationTask, reason: str) -> BackendResult:
    return BackendResult(
        backend="openapi",
        status="invalid",
        evidence_level=EvidenceLevel.STATICALLY_RESOLVED,
        details=_task_details(task, reason=reason),
    )


@dataclass(frozen=True)
class _YamlLine:
    indent: int
    content: str


def _parse_simple_yaml(text: str) -> Any:
    lines: list[_YamlLine] = []
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if "\t" in raw[: len(raw) - len(raw.lstrip())]:
            raise ValueError("YAML indentation must use spaces")
        indent = len(raw) - len(raw.lstrip(" "))
        lines.append(_YamlLine(indent=indent, content=raw.strip()))
    if not lines:
        return {}
    value, index = _parse_yaml_block(lines, 0, lines[0].indent)
    if index != len(lines):
        raise ValueError("unsupported YAML indentation")
    return value


def _parse_yaml_block(lines: list[_YamlLine], index: int, indent: int) -> tuple[Any, int]:
    if index >= len(lines):
        return {}, index
    if lines[index].indent < indent:
        return {}, index
    if lines[index].content.startswith("- "):
        return _parse_yaml_sequence(lines, index, indent)
    return _parse_yaml_mapping(lines, index, indent)


def _parse_yaml_mapping(lines: list[_YamlLine], index: int, indent: int) -> tuple[dict[str, Any], int]:
    result: dict[str, Any] = {}
    while index < len(lines):
        line = lines[index]
        if line.indent < indent:
            break
        if line.indent > indent:
            raise ValueError(f"unexpected YAML indentation before {line.content!r}")
        if line.content.startswith("- "):
            break
        key, raw_value = _split_yaml_key_value(line.content)
        if raw_value:
            result[key] = _parse_yaml_scalar(raw_value)
            index += 1
            continue
        if index + 1 < len(lines) and lines[index + 1].indent > indent:
            result[key], index = _parse_yaml_block(lines, index + 1, lines[index + 1].indent)
        else:
            result[key] = {}
            index += 1
    return result, index


def _parse_yaml_sequence(lines: list[_YamlLine], index: int, indent: int) -> tuple[list[Any], int]:
    items: list[Any] = []
    while index < len(lines):
        line = lines[index]
        if line.indent < indent:
            break
        if line.indent != indent or not line.content.startswith("- "):
            break
        item_text = line.content[2:].strip()
        if not item_text:
            if index + 1 < len(lines) and lines[index + 1].indent > indent:
                item, index = _parse_yaml_block(lines, index + 1, lines[index + 1].indent)
            else:
                item = {}
                index += 1
            items.append(item)
            continue
        if _yaml_looks_like_pair(item_text):
            key, raw_value = _split_yaml_key_value(item_text)
            item = {key: _parse_yaml_scalar(raw_value)} if raw_value else {key: {}}
            index += 1
            if index < len(lines) and lines[index].indent > indent:
                extra, index = _parse_yaml_block(lines, index, lines[index].indent)
                if not isinstance(extra, dict):
                    raise ValueError("YAML sequence mapping continuation must be a mapping")
                item.update(extra)
            items.append(item)
            continue
        items.append(_parse_yaml_scalar(item_text))
        index += 1
    return items, index


def _split_yaml_key_value(content: str) -> tuple[str, str]:
    if ":" not in content:
        raise ValueError(f"expected YAML key/value pair: {content!r}")
    key, raw_value = content.split(":", 1)
    key = _strip_yaml_quotes(key.strip())
    if not key:
        raise ValueError("YAML key cannot be empty")
    return key, raw_value.strip()


def _yaml_looks_like_pair(content: str) -> bool:
    return ":" in content and not content.startswith(("'", '"'))


def _parse_yaml_scalar(value: str) -> Any:
    if value == "":
        return ""
    if value in {"[]", "[ ]"}:
        return []
    if value in {"{}", "{ }"}:
        return {}
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered in {"null", "~"}:
        return None
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [_parse_yaml_scalar(part.strip()) for part in inner.split(",")]
    if value.startswith(("'", '"')) and value.endswith(("'", '"')):
        return _strip_yaml_quotes(value)
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    if re.fullmatch(r"-?\d+\.\d+", value):
        return float(value)
    return value


def _strip_yaml_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] == '"':
        try:
            return str(json.loads(value))
        except json.JSONDecodeError:
            return value[1:-1]
    if len(value) >= 2 and value[0] == value[-1] == "'":
        return value[1:-1]
    return value
