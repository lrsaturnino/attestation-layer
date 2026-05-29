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


AUTH_OPTIONS = {"nlreq.auth_required", "auth_required"}
ACTOR_OPTIONS = {"nlreq.actor", "actor"}
STATE_TRANSITION_OPTIONS = {
    "nlreq.rejects_unauthorized_before",
    "rejects_unauthorized_before",
    "nlreq.state_transition",
    "state_transition",
}
SCALAR_NUMERIC_TYPES = {
    "double",
    "float",
    "int32",
    "int64",
    "uint32",
    "uint64",
    "sint32",
    "sint64",
    "fixed32",
    "fixed64",
    "sfixed32",
    "sfixed64",
}


@dataclass(frozen=True)
class ProtoField:
    message: str
    name: str
    field_type: str
    number: int
    label: str | None


@dataclass(frozen=True)
class ProtoMessage:
    name: str
    fields: list[ProtoField]


@dataclass(frozen=True)
class ProtoRpc:
    service: str
    name: str
    request_type: str
    response_type: str
    options: dict[str, Any]


@dataclass(frozen=True)
class ProtoDocument:
    package: str | None
    file_options: dict[str, Any]
    messages: list[ProtoMessage]
    rpcs: list[ProtoRpc]


class ProtobufAdapter(Adapter):
    adapter_id = "protobuf"
    target_kind = "protobuf_schema"

    def __init__(self, proto_path: Path, *, schema_name: str | None = None) -> None:
        self.proto_path = Path(proto_path)
        if not self.proto_path.is_file():
            raise ValueError(f"Protobuf schema does not exist: {self.proto_path}")
        self.proto_text = self.proto_path.read_text()
        self.proto_hash = sha256_text(self.proto_text)
        self.document = _parse_proto_document(self.proto_text)
        self.schema_name = schema_name or self.document.package or self.proto_path.stem
        self._symbols = _build_symbol_index(self.schema_name, self.proto_hash, self.document)
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
                description="Protobuf/gRPC symbol exists in the parsed schema.",
            ),
            EvidenceCapability(
                evidence_level=EvidenceLevel.TYPE_CHECKED,
                description="Protobuf service, RPC, message, field, and option declarations are parsed.",
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
            "proto_path": self.proto_path.as_posix(),
            "proto_hash": self.proto_hash,
            "requirement_id": ir.requirement_id,
            "task": "symbol_shape",
            "bindings": bindings,
        }
        tasks = [
            VerificationTask(
                id="PROTOBUF-SYMBOLS",
                backend="adapter",
                description=f"Validate Protobuf/gRPC symbol bindings for {ir.requirement_id}.",
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
            raise TypeError(f"unsupported Protobuf adapter task result: {type(result).__name__}")
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
                reason="multiple Protobuf/gRPC symbols matched",
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
                "proto_path": self.proto_path.as_posix(),
                "proto_hash": self.proto_hash,
                "requirement_id": ir.requirement_id,
                "task": "auth_rejection",
                "operation": ir.claim.action,
                "operation_symbol": operation.symbol,
                "required_auth_options": sorted(AUTH_OPTIONS),
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
                id="PROTOBUF-AUTH-REJECTION",
                backend="adapter",
                description=f"Validate Protobuf/gRPC auth and state-transition options for {ir.requirement_id}.",
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
                "proto_path": self.proto_path.as_posix(),
                "proto_hash": self.proto_hash,
                "requirement_id": ir.requirement_id,
                "task": "success_response",
                "operation": ir.claim.action,
                "operation_symbol": operation.symbol,
            }
            return VerificationTask(
                id="PROTOBUF-SUCCESS-RESPONSE",
                backend="adapter",
                description=f"Validate Protobuf/gRPC response declaration for {ir.requirement_id}.",
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
                "proto_hash": self.proto_hash,
            },
        )

    def _run_auth_rejection_task(self, task: VerificationTask) -> BackendResult:
        operation = self._symbol_named(task.payload.get("operation_symbol"), "action")
        if operation is None:
            return _invalid_protobuf_result(task, "operation_symbol does not resolve to an action")
        options = operation.metadata.get("options")
        if not isinstance(options, dict):
            options = {}
        auth_options = sorted(key for key in options if key in AUTH_OPTIONS and options[key] is True)
        transition_symbol = task.payload.get("state_transition_symbol")
        transition_valid = True
        if "state_transition" in task.payload:
            transition = self._symbol_named(transition_symbol, "state_transition")
            transition_valid = (
                transition is not None
                and transition.metadata.get("operation_symbol") == operation.name
            )

        problems: list[str] = []
        if not auth_options:
            problems.append("RPC does not declare a reviewed auth option")
        if not transition_valid:
            problems.append("state transition binding does not belong to the RPC")

        return BackendResult(
            backend=self.adapter_id,
            status="invalid" if problems else "valid",
            evidence_level=EvidenceLevel.STATICALLY_RESOLVED,
            details={
                **_task_details(task),
                "operation_symbol": operation.name,
                "auth_options": auth_options,
                "state_transition_symbol": transition_symbol,
                "proto_hash": self.proto_hash,
                "problems": problems,
            },
        )

    def _run_success_response_task(self, task: VerificationTask) -> BackendResult:
        operation = self._symbol_named(task.payload.get("operation_symbol"), "action")
        if operation is None:
            return _invalid_protobuf_result(task, "operation_symbol does not resolve to an action")
        response_type = str(operation.metadata.get("response_type") or "")
        problems = [] if response_type else ["RPC does not declare a response type"]
        return BackendResult(
            backend=self.adapter_id,
            status="invalid" if problems else "valid",
            evidence_level=EvidenceLevel.STATICALLY_RESOLVED,
            details={
                **_task_details(task),
                "operation_symbol": operation.name,
                "response_type": response_type,
                "proto_hash": self.proto_hash,
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


def supported_protobuf_claim(ir: RequirementIR) -> bool:
    return _is_auth_rejection_claim(ir) or _is_success_response_claim(ir)


def _parse_proto_document(proto_text: str) -> ProtoDocument:
    text = _strip_proto_comments(proto_text)
    package_match = re.search(r"\bpackage\s+([A-Za-z_][A-Za-z0-9_.]*)\s*;", text)
    package = package_match.group(1) if package_match else None
    file_options = _parse_options(_remove_blocks(text, ("message", "service")))
    messages = _parse_messages(text)
    rpcs = _parse_services(text)
    if not messages and not rpcs:
        raise ValueError("Protobuf schema contains no parseable messages or services")
    return ProtoDocument(package=package, file_options=file_options, messages=messages, rpcs=rpcs)


def _parse_messages(text: str) -> list[ProtoMessage]:
    messages: list[ProtoMessage] = []
    for name, body in _iter_named_blocks(text, "message"):
        fields: list[ProtoField] = []
        for match in re.finditer(
            r"\b(?:(optional|required|repeated)\s+)?([A-Za-z_][A-Za-z0-9_.]*)\s+"
            r"([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(\d+)(?:\s*\[[^\]]*\])?\s*;",
            body,
        ):
            fields.append(
                ProtoField(
                    message=name,
                    label=match.group(1),
                    field_type=match.group(2),
                    name=match.group(3),
                    number=int(match.group(4)),
                )
            )
        messages.append(ProtoMessage(name=name, fields=fields))
    return messages


def _parse_services(text: str) -> list[ProtoRpc]:
    rpcs: list[ProtoRpc] = []
    for service_name, service_body in _iter_named_blocks(text, "service"):
        for match in re.finditer(
            r"\brpc\s+([A-Za-z_][A-Za-z0-9_]*)\s*"
            r"\(\s*([A-Za-z_][A-Za-z0-9_.]*)\s*\)\s*"
            r"returns\s*\(\s*([A-Za-z_][A-Za-z0-9_.]*)\s*\)\s*"
            r"(?:\{(?P<body>.*?)\}|;)",
            service_body,
            flags=re.DOTALL,
        ):
            rpcs.append(
                ProtoRpc(
                    service=service_name,
                    name=match.group(1),
                    request_type=_short_type(match.group(2)),
                    response_type=_short_type(match.group(3)),
                    options=_parse_options(match.group("body") or ""),
                )
            )
    return rpcs


def _build_symbol_index(schema_name: str, proto_hash: str, document: ProtoDocument) -> list[Symbol]:
    symbols: list[Symbol] = [
        Symbol(
            name=schema_name,
            symbol_type="protobuf_schema",
            metadata={
                "kind": "protobuf_schema",
                "package": document.package,
                "proto_hash": proto_hash,
            },
        )
    ]
    for message in document.messages:
        symbols.append(
            Symbol(
                name=message.name,
                symbol_type="message",
                metadata={
                    "kind": "message",
                    "fields": [field.name for field in message.fields],
                },
            )
        )
        for field in message.fields:
            symbol_type = _field_symbol_type(field)
            metadata = {
                "kind": "field",
                "message": field.message,
                "field_type": field.field_type,
                "field_number": field.number,
                "label": field.label,
            }
            symbols.append(Symbol(name=field.name, symbol_type=symbol_type, metadata=metadata))
            qualified = f"{field.message}.{field.name}"
            if qualified != field.name:
                symbols.append(Symbol(name=qualified, symbol_type=symbol_type, metadata=metadata))

    actor_seen = False
    for rpc in document.rpcs:
        rpc_name = rpc.name
        metadata = {
            "kind": "rpc",
            "service": rpc.service,
            "request_type": rpc.request_type,
            "response_type": rpc.response_type,
            "options": rpc.options,
        }
        symbols.append(Symbol(name=rpc_name, symbol_type="action", metadata=metadata))
        qualified = f"{rpc.service}.{rpc_name}"
        if qualified != rpc_name:
            symbols.append(
                Symbol(
                    name=qualified,
                    symbol_type="action",
                    metadata={**metadata, "alias_for": rpc_name},
                )
            )
        actor_name = _actor_name(document.file_options, rpc.options)
        if actor_name and not actor_seen:
            symbols.append(
                Symbol(
                    name=actor_name,
                    symbol_type="principal",
                    metadata={
                        "kind": "auth_principal",
                        "operation_symbol": rpc_name,
                    },
                )
            )
            actor_seen = True
        transition = _state_transition_name(rpc.options)
        if transition:
            symbols.append(
                Symbol(
                    name=transition,
                    symbol_type="state_transition",
                    metadata={
                        "kind": "state_transition",
                        "operation_symbol": rpc_name,
                        "service": rpc.service,
                    },
                )
            )
    return sorted(symbols, key=_symbol_sort_key)


def _parse_options(text: str) -> dict[str, Any]:
    options: dict[str, Any] = {}
    for match in re.finditer(
        r"\boption\s+\(?([A-Za-z_][A-Za-z0-9_.]*)\)?\s*=\s*"
        r"(?:\"([^\"]*)\"|(true|false)|([A-Za-z_][A-Za-z0-9_.]*))\s*;",
        text,
    ):
        key = match.group(1)
        if match.group(2) is not None:
            value: Any = match.group(2)
        elif match.group(3) is not None:
            value = match.group(3) == "true"
        else:
            value = match.group(4)
        options[key] = value
    return options


def _iter_named_blocks(text: str, keyword: str) -> list[tuple[str, str]]:
    blocks: list[tuple[str, str]] = []
    pattern = re.compile(rf"\b{keyword}\s+([A-Za-z_][A-Za-z0-9_]*)\s*\{{")
    pos = 0
    while True:
        match = pattern.search(text, pos)
        if match is None:
            break
        open_brace = text.find("{", match.end() - 1)
        close_brace = _matching_brace(text, open_brace)
        if close_brace == -1:
            raise ValueError(f"unterminated {keyword} block: {match.group(1)}")
        blocks.append((match.group(1), text[open_brace + 1 : close_brace]))
        pos = close_brace + 1
    return blocks


def _matching_brace(text: str, open_brace: int) -> int:
    depth = 0
    for index in range(open_brace, len(text)):
        char = text[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index
    return -1


def _remove_blocks(text: str, keywords: tuple[str, ...]) -> str:
    result = text
    for keyword in keywords:
        spans: list[tuple[int, int]] = []
        pattern = re.compile(rf"\b{keyword}\s+[A-Za-z_][A-Za-z0-9_]*\s*\{{")
        pos = 0
        while True:
            match = pattern.search(result, pos)
            if match is None:
                break
            open_brace = result.find("{", match.end() - 1)
            close_brace = _matching_brace(result, open_brace)
            if close_brace == -1:
                break
            spans.append((match.start(), close_brace + 1))
            pos = close_brace + 1
        for start, end in reversed(spans):
            result = result[:start] + result[end:]
    return result


def _field_symbol_type(field: ProtoField) -> str:
    if field.name == "actor":
        return "principal"
    if field.field_type in SCALAR_NUMERIC_TYPES:
        return "quantity"
    if field.name.endswith("_status"):
        return "state"
    return "field"


def _actor_name(file_options: dict[str, Any], rpc_options: dict[str, Any]) -> str | None:
    for options in (rpc_options, file_options):
        for key in ACTOR_OPTIONS:
            value = options.get(key)
            if isinstance(value, str) and value:
                return value
        if any(options.get(key) is True for key in AUTH_OPTIONS):
            return "actor"
    return None


def _state_transition_name(options: dict[str, Any]) -> str | None:
    for key in STATE_TRANSITION_OPTIONS:
        value = options.get(key)
        if isinstance(value, str) and value:
            return value
    return None


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
        "proto_path": task.payload.get("proto_path"),
        "proto_hash": task.payload.get("proto_hash"),
        **extra,
    }


def _invalid_protobuf_result(task: VerificationTask, reason: str) -> BackendResult:
    return BackendResult(
        backend="protobuf",
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
    return symbol.symbol_type == expected_type


def _short_type(value: str) -> str:
    return value.rsplit(".", 1)[-1]


def _symbol_sort_key(symbol: Symbol) -> tuple[str, str, str]:
    service = symbol.metadata.get("service")
    return (symbol.name, symbol.symbol_type, service if isinstance(service, str) else "")


def _strip_proto_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    return "\n".join(line.split("//", 1)[0] for line in text.splitlines())
