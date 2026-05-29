from __future__ import annotations

import json
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


NUMERIC_JSON_TYPES = {"integer", "number"}


@dataclass(frozen=True)
class JsonSchemaProperty:
    name: str
    path: str
    schema: dict[str, Any]


@dataclass(frozen=True)
class JsonSchemaAction:
    name: str
    index: int
    sets: dict[str, Any]
    increases: dict[str, Any]
    decreases: dict[str, Any]
    metadata: dict[str, Any]


class JsonSchemaAdapter(Adapter):
    adapter_id = "json_schema"
    target_kind = "json_schema_document"

    def __init__(self, schema_path: Path, *, schema_name: str | None = None) -> None:
        self.schema_path = Path(schema_path)
        if not self.schema_path.is_file():
            raise ValueError(f"JSON Schema document does not exist: {self.schema_path}")
        self.schema_text = self.schema_path.read_text()
        self.schema_hash = sha256_text(self.schema_text)
        self.schema = _load_json_schema(self.schema_text)
        self.schema_name = schema_name or _schema_name(self.schema, self.schema_path)
        self._properties = _collect_properties(self.schema)
        self._actions = _collect_actions(self.schema)
        self._symbols = _build_symbol_index(
            self.schema_name,
            self.schema_hash,
            self._properties,
            self._actions,
        )
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
                description="JSON Schema symbol exists in the parsed document.",
            ),
            EvidenceCapability(
                evidence_level=EvidenceLevel.TYPE_CHECKED,
                description="JSON Schema property, type, const, enum, and action metadata is parsed.",
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
                id="JSON-SCHEMA-SYMBOLS",
                backend="adapter",
                description=f"Validate JSON Schema symbol bindings for {ir.requirement_id}.",
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
            raise TypeError(f"unsupported JSON Schema adapter task result: {type(result).__name__}")
        return collected

    def run_task(self, task: VerificationTask) -> BackendResult:
        task_kind = task.payload.get("task")
        if task_kind == "symbol_shape":
            return self._run_symbol_shape_task(task)
        if task_kind == "state_value":
            return self._run_state_value_task(task)
        if task_kind == "numeric_delta":
            return self._run_numeric_delta_task(task)
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
                symbol for symbol in self._symbols if symbol.symbol_type == "principal"
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
            return SymbolResolution(ref=ref, status="unresolved", reason="symbol not found")
        if len(candidates) > 1:
            return SymbolResolution(
                ref=ref,
                status="ambiguous",
                symbols=candidates,
                reason="multiple JSON Schema symbols matched",
            )
        return SymbolResolution(ref=ref, status="resolved", symbols=candidates)

    def _claim_task_for_ir(self, ir: RequirementIR) -> VerificationTask | None:
        if _is_state_value_claim(ir):
            operation = ir.bindings.get(ir.claim.action)
            target = ir.bindings.get(ir.claim.expected.target or "")
            if operation is None or target is None or operation.adapter != self.adapter_id:
                return None
            payload = {
                "adapter": self.adapter_id,
                "schema": self.schema_name,
                "schema_path": self.schema_path.as_posix(),
                "schema_hash": self.schema_hash,
                "requirement_id": ir.requirement_id,
                "task": "state_value",
                "operation": ir.claim.action,
                "operation_symbol": operation.symbol,
                "target": ir.claim.expected.target,
                "target_symbol": target.symbol,
                "expected_value": ir.claim.expected.value.value
                if ir.claim.expected.value is not None
                else None,
            }
            return VerificationTask(
                id="JSON-SCHEMA-STATE-VALUE",
                backend="adapter",
                description=f"Validate JSON Schema state value declarations for {ir.requirement_id}.",
                input_hash=sha256_json(payload),
                payload=payload,
            )

        if _is_numeric_delta_claim(ir):
            operation = ir.bindings.get(ir.claim.action)
            target = ir.bindings.get(ir.claim.expected.target or "")
            if operation is None or target is None or operation.adapter != self.adapter_id:
                return None
            payload = {
                "adapter": self.adapter_id,
                "schema": self.schema_name,
                "schema_path": self.schema_path.as_posix(),
                "schema_hash": self.schema_hash,
                "requirement_id": ir.requirement_id,
                "task": "numeric_delta",
                "operation": ir.claim.action,
                "operation_symbol": operation.symbol,
                "target": ir.claim.expected.target,
                "target_symbol": target.symbol,
                "delta_kind": ir.claim.expected.kind,
                "delta_value": ir.claim.expected.value.value
                if ir.claim.expected.value is not None
                else None,
            }
            return VerificationTask(
                id="JSON-SCHEMA-NUMERIC-DELTA",
                backend="adapter",
                description=f"Validate JSON Schema numeric delta metadata for {ir.requirement_id}.",
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

    def _run_state_value_task(self, task: VerificationTask) -> BackendResult:
        action = self._symbol_named(task.payload.get("operation_symbol"), "action")
        target = self._symbol_named_any(task.payload.get("target_symbol"), {"field", "state"})
        if action is None:
            return _invalid_json_schema_result(task, "operation_symbol does not resolve to an action")
        if target is None:
            return _invalid_json_schema_result(task, "target_symbol does not resolve to a field or state")

        expected = task.payload.get("expected_value")
        action_declares = _mapping_declares_value(action.metadata.get("sets"), target, expected)
        property_declares = _property_declares_value(target.metadata.get("property_schema"), expected)
        problems: list[str] = []
        if not action_declares and not property_declares:
            problems.append("schema does not declare the expected state value")

        return BackendResult(
            backend=self.adapter_id,
            status="invalid" if problems else "valid",
            evidence_level=EvidenceLevel.TYPE_CHECKED,
            details={
                **_task_details(task),
                "operation_symbol": action.name,
                "target_symbol": target.name,
                "expected_value": expected,
                "action_declares_value": action_declares,
                "property_declares_value": property_declares,
                "schema_hash": self.schema_hash,
                "problems": problems,
            },
        )

    def _run_numeric_delta_task(self, task: VerificationTask) -> BackendResult:
        action = self._symbol_named(task.payload.get("operation_symbol"), "action")
        target = self._symbol_named_any(task.payload.get("target_symbol"), {"field", "quantity"})
        if action is None:
            return _invalid_json_schema_result(task, "operation_symbol does not resolve to an action")
        if target is None:
            return _invalid_json_schema_result(task, "target_symbol does not resolve to a field or quantity")

        delta_kind = str(task.payload.get("delta_kind"))
        delta_value = task.payload.get("delta_value")
        metadata_key = "increases" if delta_kind == "increase" else "decreases"
        delta_declares = _mapping_declares_value(action.metadata.get(metadata_key), target, delta_value)
        numeric_target = _property_is_numeric(target.metadata.get("property_schema"))
        problems: list[str] = []
        if not numeric_target:
            problems.append("target property is not declared as numeric")
        if not delta_declares:
            problems.append("action metadata does not declare the expected numeric delta")

        return BackendResult(
            backend=self.adapter_id,
            status="invalid" if problems else "valid",
            evidence_level=EvidenceLevel.TYPE_CHECKED,
            details={
                **_task_details(task),
                "operation_symbol": action.name,
                "target_symbol": target.name,
                "delta_kind": delta_kind,
                "delta_value": delta_value,
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

    def _symbol_named_any(self, value: object, symbol_types: set[str]) -> Symbol | None:
        if not isinstance(value, str):
            return None
        for symbol in self._symbols_by_name.get(value, []):
            if symbol.symbol_type in symbol_types:
                return symbol
        return None


def supported_json_schema_claim(ir: RequirementIR) -> bool:
    return _is_state_value_claim(ir) or _is_numeric_delta_claim(ir)


def _load_json_schema(text: str) -> dict[str, Any]:
    try:
        schema = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON Schema document is not valid JSON: {exc}") from exc
    if not isinstance(schema, dict):
        raise ValueError("JSON Schema document must be a JSON object")
    return schema


def _schema_name(schema: dict[str, Any], path: Path) -> str:
    for key in ("title", "$id", "id"):
        value = schema.get(key)
        if isinstance(value, str) and value:
            return value
    return path.stem


def _collect_properties(schema: dict[str, Any], prefix: tuple[str, ...] = ()) -> list[JsonSchemaProperty]:
    raw_properties = schema.get("properties")
    if not isinstance(raw_properties, dict):
        return []
    properties: list[JsonSchemaProperty] = []
    for name, raw_schema in sorted(raw_properties.items()):
        if not isinstance(raw_schema, dict):
            continue
        path = (*prefix, str(name))
        properties.append(JsonSchemaProperty(name=str(name), path=".".join(path), schema=raw_schema))
        properties.extend(_collect_properties(raw_schema, path))
    return properties


def _collect_actions(schema: dict[str, Any]) -> list[JsonSchemaAction]:
    raw = schema.get("x-nlreq-actions", [])
    entries: list[tuple[str, dict[str, Any]]] = []
    if isinstance(raw, dict):
        for name, value in sorted(raw.items()):
            if isinstance(value, list):
                entries.extend((str(name), item) for item in value if isinstance(item, dict))
            elif isinstance(value, dict):
                entries.append((str(name), value))
    elif isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict) and isinstance(item.get("name"), str):
                entries.append((item["name"], item))

    actions: list[JsonSchemaAction] = []
    for index, (name, item) in enumerate(entries):
        actions.append(
            JsonSchemaAction(
                name=name,
                index=index,
                sets=_string_keyed_mapping(item.get("sets")),
                increases=_string_keyed_mapping(item.get("increases")),
                decreases=_string_keyed_mapping(item.get("decreases")),
                metadata={str(key): value for key, value in item.items() if key != "name"},
            )
        )
    return actions


def _build_symbol_index(
    schema_name: str,
    schema_hash: str,
    properties: list[JsonSchemaProperty],
    actions: list[JsonSchemaAction],
) -> list[Symbol]:
    symbols: list[Symbol] = [
        Symbol(
            name=schema_name,
            symbol_type="json_schema",
            metadata={"kind": "json_schema", "schema_hash": schema_hash},
        )
    ]
    for action in actions:
        symbols.append(
            Symbol(
                name=action.name,
                symbol_type="action",
                metadata={
                    "kind": "action",
                    "action_index": action.index,
                    "sets": action.sets,
                    "increases": action.increases,
                    "decreases": action.decreases,
                    **action.metadata,
                },
            )
        )
    for prop in properties:
        symbols.append(
            Symbol(
                name=prop.name,
                symbol_type=_property_symbol_type(prop),
                metadata={
                    "kind": "property",
                    "json_path": prop.path,
                    "json_type": prop.schema.get("type"),
                    "required": False,
                    "property_schema": prop.schema,
                },
            )
        )
    return sorted(symbols, key=_symbol_sort_key)


def _property_symbol_type(prop: JsonSchemaProperty) -> str:
    explicit = prop.schema.get("x-nlreq-symbol-type")
    if isinstance(explicit, str) and explicit:
        return explicit
    if prop.name == "actor":
        return "principal"
    if _property_is_numeric(prop.schema):
        return "quantity"
    if prop.name.endswith("_status") or "const" in prop.schema or "enum" in prop.schema:
        return "state"
    return "field"


def _property_is_numeric(raw_schema: object) -> bool:
    if not isinstance(raw_schema, dict):
        return False
    raw_type = raw_schema.get("type")
    if isinstance(raw_type, str):
        return raw_type in NUMERIC_JSON_TYPES
    if isinstance(raw_type, list):
        return any(item in NUMERIC_JSON_TYPES for item in raw_type)
    return False


def _property_declares_value(raw_schema: object, expected: object) -> bool:
    if not isinstance(raw_schema, dict):
        return False
    if raw_schema.get("const") == expected:
        return True
    enum = raw_schema.get("enum")
    return isinstance(enum, list) and expected in enum


def _mapping_declares_value(raw_mapping: object, target: Symbol, expected: object) -> bool:
    if not isinstance(raw_mapping, dict):
        return False
    target_names = [target.name]
    json_path = target.metadata.get("json_path")
    if isinstance(json_path, str):
        target_names.append(json_path)
    return any(raw_mapping.get(name) == expected for name in target_names)


def _string_keyed_mapping(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {str(key): item for key, item in value.items()}


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


def _invalid_json_schema_result(task: VerificationTask, reason: str) -> BackendResult:
    return BackendResult(
        backend="json_schema",
        status="invalid",
        evidence_level=EvidenceLevel.TYPE_CHECKED,
        details=_task_details(task, reason=reason),
    )


def _is_state_value_claim(ir: RequirementIR) -> bool:
    return (
        ir.claim.kind == "state_postcondition"
        and ir.claim.expected.kind == "set"
        and ir.claim.expected.target is not None
        and ir.claim.expected.value is not None
    )


def _is_numeric_delta_claim(ir: RequirementIR) -> bool:
    return (
        ir.claim.kind == "numeric_invariant"
        and ir.claim.expected.kind in {"increase", "decrease"}
        and ir.claim.expected.target is not None
        and ir.claim.expected.value is not None
    )


def _matches_expected_type(symbol: Symbol, expected_type: str | None) -> bool:
    if expected_type is None:
        return True
    return symbol.symbol_type == expected_type


def _symbol_sort_key(symbol: Symbol) -> tuple[str, str, str]:
    path = symbol.metadata.get("json_path")
    return (symbol.name, symbol.symbol_type, path if isinstance(path, str) else "")
