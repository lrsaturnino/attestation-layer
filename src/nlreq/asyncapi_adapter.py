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


EMIT_ACTIONS = {"publish", "send"}


@dataclass(frozen=True)
class AsyncApiMessage:
    name: str
    source: str
    payload_ref: str | None
    metadata: dict[str, Any]


@dataclass(frozen=True)
class AsyncApiOperation:
    name: str
    index: int
    action: str | None
    channel: str | None
    emits: list[str]
    metadata: dict[str, Any]


class AsyncApiAdapter(Adapter):
    adapter_id = "asyncapi"
    target_kind = "asyncapi_document"

    def __init__(self, document_path: Path, *, document_name: str | None = None) -> None:
        self.document_path = Path(document_path)
        if not self.document_path.is_file():
            raise ValueError(f"AsyncAPI document does not exist: {self.document_path}")
        self.document_text = self.document_path.read_text()
        self.document_hash = sha256_text(self.document_text)
        self.document = _load_asyncapi_document(self.document_text)
        self.document_name = document_name or _document_name(self.document, self.document_path)
        self._messages = _collect_messages(self.document)
        self._operations = _collect_operations(self.document, self._messages)
        self._symbols = _build_symbol_index(
            self.document_name,
            self.document_hash,
            self.document,
            self._messages,
            self._operations,
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
                description="AsyncAPI symbol exists in the parsed document.",
            ),
            EvidenceCapability(
                evidence_level=EvidenceLevel.TYPE_CHECKED,
                description="AsyncAPI operation, channel, message, and emission declarations are parsed.",
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
                id="ASYNCAPI-SYMBOLS",
                backend="adapter",
                description=f"Validate AsyncAPI symbol bindings for {ir.requirement_id}.",
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
            raise TypeError(f"unsupported AsyncAPI adapter task result: {type(result).__name__}")
        return collected

    def run_task(self, task: VerificationTask) -> BackendResult:
        task_kind = task.payload.get("task")
        if task_kind == "symbol_shape":
            return self._run_symbol_shape_task(task)
        if task_kind == "event_emission":
            return self._run_event_emission_task(task)
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
                reason="multiple AsyncAPI symbols matched",
            )
        return SymbolResolution(ref=ref, status="resolved", symbols=candidates)

    def _claim_task_for_ir(self, ir: RequirementIR) -> VerificationTask | None:
        if not _is_event_emission_claim(ir):
            return None
        operation = ir.bindings.get(ir.claim.action)
        event = ir.bindings.get(ir.claim.expected.target or "")
        if operation is None or event is None or operation.adapter != self.adapter_id:
            return None
        payload = {
            "adapter": self.adapter_id,
            "document": self.document_name,
            "document_path": self.document_path.as_posix(),
            "document_hash": self.document_hash,
            "requirement_id": ir.requirement_id,
            "task": "event_emission",
            "operation": ir.claim.action,
            "operation_symbol": operation.symbol,
            "event": ir.claim.expected.target,
            "event_symbol": event.symbol,
        }
        return VerificationTask(
            id="ASYNCAPI-EVENT-EMISSION",
            backend="adapter",
            description=f"Validate AsyncAPI event emission declaration for {ir.requirement_id}.",
            input_hash=sha256_json(payload),
            payload=payload,
        )

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

    def _run_event_emission_task(self, task: VerificationTask) -> BackendResult:
        operation = self._symbol_named(task.payload.get("operation_symbol"), "action")
        event = self._symbol_named(task.payload.get("event_symbol"), "event")
        if operation is None:
            return _invalid_asyncapi_result(task, "operation_symbol does not resolve to an action")
        if event is None:
            return _invalid_asyncapi_result(task, "event_symbol does not resolve to an event")

        operation_action = operation.metadata.get("action")
        emitted_events = _string_list(operation.metadata.get("emits"))
        event_names = _event_names(event)
        event_declared = bool(set(emitted_events).intersection(event_names))
        emit_action = operation_action in EMIT_ACTIONS or not operation_action
        problems: list[str] = []
        if not event_declared:
            problems.append("operation does not declare the expected event message")
        if not emit_action:
            problems.append("operation action is not an emitting action")

        return BackendResult(
            backend=self.adapter_id,
            status="invalid" if problems else "valid",
            evidence_level=EvidenceLevel.TYPE_CHECKED,
            details={
                **_task_details(task),
                "operation_symbol": operation.name,
                "operation_action": operation_action,
                "event_symbol": event.name,
                "emitted_events": emitted_events,
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


def supported_asyncapi_claim(ir: RequirementIR) -> bool:
    return _is_event_emission_claim(ir)


def _load_asyncapi_document(text: str) -> dict[str, Any]:
    try:
        document = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"AsyncAPI document is not valid JSON: {exc}") from exc
    if not isinstance(document, dict):
        raise ValueError("AsyncAPI document must be a JSON object")
    if "asyncapi" not in document:
        raise ValueError("AsyncAPI document must include an asyncapi version")
    return document


def _document_name(document: dict[str, Any], path: Path) -> str:
    info = document.get("info")
    if isinstance(info, dict) and isinstance(info.get("title"), str) and info["title"]:
        return info["title"]
    return path.stem


def _collect_messages(document: dict[str, Any]) -> list[AsyncApiMessage]:
    messages: list[AsyncApiMessage] = []
    raw_components = document.get("components")
    components = raw_components if isinstance(raw_components, dict) else {}
    raw_messages = components.get("messages")
    if isinstance(raw_messages, dict):
        for name, raw in sorted(raw_messages.items()):
            if isinstance(raw, dict):
                messages.append(_message_from_raw(str(name), raw, f"#/components/messages/{name}"))

    raw_channels = document.get("channels")
    if isinstance(raw_channels, dict):
        for channel_name, channel in sorted(raw_channels.items()):
            if not isinstance(channel, dict):
                continue
            channel_messages = channel.get("messages")
            if isinstance(channel_messages, dict):
                for message_name, raw in sorted(channel_messages.items()):
                    resolved = _resolve_ref(raw, document)
                    if isinstance(resolved, dict):
                        messages.append(
                            _message_from_raw(
                                str(message_name),
                                resolved,
                                f"#/channels/{channel_name}/messages/{message_name}",
                            )
                        )
    return _dedupe_messages(messages)


def _collect_operations(
    document: dict[str, Any], messages: list[AsyncApiMessage]
) -> list[AsyncApiOperation]:
    operations: list[AsyncApiOperation] = []
    raw_operations = document.get("operations")
    if isinstance(raw_operations, dict):
        for name, raw in sorted(raw_operations.items()):
            if isinstance(raw, dict):
                operations.append(
                    AsyncApiOperation(
                        name=str(name),
                        index=len(operations),
                        action=_string_or_none(raw.get("action")),
                        channel=_operation_channel(raw),
                        emits=_operation_messages(raw, document, messages),
                        metadata={str(key): value for key, value in raw.items()},
                    )
                )

    raw_channels = document.get("channels")
    if isinstance(raw_channels, dict):
        for channel_name, channel in sorted(raw_channels.items()):
            if not isinstance(channel, dict):
                continue
            for operation_kind in ("publish", "subscribe"):
                raw = channel.get(operation_kind)
                if not isinstance(raw, dict):
                    continue
                name = _string_or_none(raw.get("operationId")) or _safe_name(
                    f"{operation_kind}_{channel_name}"
                )
                operations.append(
                    AsyncApiOperation(
                        name=name,
                        index=len(operations),
                        action="send" if operation_kind == "publish" else "receive",
                        channel=str(channel_name),
                        emits=_operation_messages(raw, document, messages),
                        metadata={str(key): value for key, value in raw.items()},
                    )
                )

    operations.extend(_extension_operations(document, len(operations)))
    return operations


def _extension_operations(document: dict[str, Any], start_index: int) -> list[AsyncApiOperation]:
    raw = document.get("x-nlreq-actions", [])
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

    operations: list[AsyncApiOperation] = []
    for offset, (name, item) in enumerate(entries):
        operations.append(
            AsyncApiOperation(
                name=name,
                index=start_index + offset,
                action=_string_or_none(item.get("action")) or "send",
                channel=_string_or_none(item.get("channel")),
                emits=sorted(set(_string_list(item.get("emits")))),
                metadata={str(key): value for key, value in item.items() if key != "name"},
            )
        )
    return operations


def _build_symbol_index(
    document_name: str,
    document_hash: str,
    document: dict[str, Any],
    messages: list[AsyncApiMessage],
    operations: list[AsyncApiOperation],
) -> list[Symbol]:
    symbols: list[Symbol] = [
        Symbol(
            name=document_name,
            symbol_type="asyncapi_document",
            metadata={"kind": "asyncapi_document", "document_hash": document_hash},
        )
    ]

    raw_channels = document.get("channels")
    if isinstance(raw_channels, dict):
        for name, raw in sorted(raw_channels.items()):
            address = raw.get("address") if isinstance(raw, dict) else None
            symbols.append(
                Symbol(
                    name=str(name),
                    symbol_type="channel",
                    metadata={
                        "kind": "channel",
                        "address": address if isinstance(address, str) else str(name),
                    },
                )
            )

    for principal in _principal_symbols(document):
        symbols.append(principal)

    for message in messages:
        symbols.append(
            Symbol(
                name=message.name,
                symbol_type="event",
                metadata={
                    "kind": "message",
                    "source": message.source,
                    "payload_ref": message.payload_ref,
                    **message.metadata,
                },
            )
        )

    for operation in operations:
        symbols.append(
            Symbol(
                name=operation.name,
                symbol_type="action",
                metadata={
                    "kind": "operation",
                    "operation_index": operation.index,
                    "action": operation.action,
                    "channel": operation.channel,
                    "emits": operation.emits,
                    **operation.metadata,
                },
            )
        )
    return sorted(symbols, key=_symbol_sort_key)


def _principal_symbols(document: dict[str, Any]) -> list[Symbol]:
    raw_components = document.get("components")
    components = raw_components if isinstance(raw_components, dict) else {}
    raw_schemes = components.get("securitySchemes")
    symbols: list[Symbol] = []
    if isinstance(raw_schemes, dict):
        for name, raw in sorted(raw_schemes.items()):
            metadata = {"kind": "security_scheme"}
            if isinstance(raw, dict):
                metadata.update({str(key): value for key, value in raw.items()})
            symbols.append(Symbol(name=str(name), symbol_type="principal", metadata=metadata))
    return symbols


def _message_from_raw(name: str, raw: dict[str, Any], source: str) -> AsyncApiMessage:
    message_name = _string_or_none(raw.get("name")) or name
    payload = raw.get("payload")
    payload_ref = _ref_value(payload)
    return AsyncApiMessage(
        name=message_name,
        source=source,
        payload_ref=payload_ref,
        metadata={str(key): value for key, value in raw.items() if key != "name"},
    )


def _dedupe_messages(messages: list[AsyncApiMessage]) -> list[AsyncApiMessage]:
    by_key: dict[str, AsyncApiMessage] = {}
    for message in messages:
        existing = by_key.get(message.name)
        if existing is None or message.source.startswith("#/components/messages/"):
            by_key[message.name] = message
    return [by_key[key] for key in sorted(by_key)]


def _operation_messages(
    raw: dict[str, Any],
    document: dict[str, Any],
    messages: list[AsyncApiMessage],
) -> list[str]:
    explicit = _string_list(raw.get("x-nlreq-emits")) + _string_list(raw.get("emits"))
    raw_messages = raw.get("messages", raw.get("message"))
    extracted = _message_names_from_value(raw_messages, document, messages)
    return sorted(set(explicit + extracted))


def _message_names_from_value(
    value: object,
    document: dict[str, Any],
    messages: list[AsyncApiMessage],
) -> list[str]:
    if isinstance(value, str):
        return [_message_name_from_ref(value, messages)]
    if isinstance(value, list):
        names: list[str] = []
        for item in value:
            names.extend(_message_names_from_value(item, document, messages))
        return names
    if isinstance(value, dict):
        ref = _ref_value(value)
        if ref:
            return [_message_name_from_ref(ref, messages)]
        if isinstance(value.get("oneOf"), list):
            return _message_names_from_value(value["oneOf"], document, messages)
        if isinstance(value.get("name"), str):
            return [value["name"]]
        names: list[str] = []
        for key, item in sorted(value.items()):
            if key.startswith("x-"):
                continue
            if isinstance(item, dict):
                ref = _ref_value(item)
                if ref:
                    names.append(_message_name_from_ref(ref, messages))
                elif isinstance(item.get("name"), str):
                    names.append(item["name"])
                else:
                    resolved = _resolve_ref(item, document)
                    if isinstance(resolved, dict) and isinstance(resolved.get("name"), str):
                        names.append(resolved["name"])
                    else:
                        names.append(str(key))
            elif isinstance(item, str):
                names.append(item)
        return names
    return []


def _operation_channel(raw: dict[str, Any]) -> str | None:
    channel = raw.get("channel")
    if isinstance(channel, str):
        return channel
    ref = _ref_value(channel)
    if ref:
        return ref.rsplit("/", 1)[-1]
    return None


def _resolve_ref(value: object, document: dict[str, Any]) -> object:
    ref = _ref_value(value)
    if not ref or not ref.startswith("#/"):
        return value
    current: object = document
    for part in ref[2:].split("/"):
        if not isinstance(current, dict):
            return value
        current = current.get(part)
    return current if current is not None else value


def _ref_value(value: object) -> str | None:
    if isinstance(value, str):
        return value if value.startswith("#/") else None
    if isinstance(value, dict) and isinstance(value.get("$ref"), str):
        return value["$ref"]
    return None


def _message_name_from_ref(ref: str, messages: list[AsyncApiMessage]) -> str:
    fallback = ref.rsplit("/", 1)[-1]
    for message in messages:
        if message.source == ref or message.source.endswith("/" + fallback):
            return message.name
    return fallback


def _event_names(event: Symbol) -> set[str]:
    names = {event.name}
    source = event.metadata.get("source")
    if isinstance(source, str):
        names.add(source.rsplit("/", 1)[-1])
    payload_ref = event.metadata.get("payload_ref")
    if isinstance(payload_ref, str):
        names.add(payload_ref.rsplit("/", 1)[-1])
    return names


def _index_symbols(symbols: list[Symbol]) -> dict[str, list[Symbol]]:
    indexed: dict[str, list[Symbol]] = {}
    for symbol in symbols:
        indexed.setdefault(symbol.name, []).append(symbol)
    return {key: sorted(value, key=_symbol_sort_key) for key, value in indexed.items()}


def _task_details(task: VerificationTask, **extra: Any) -> dict[str, Any]:
    return {
        "task_id": task.id,
        "task_input_hash": task.input_hash,
        "document": task.payload.get("document"),
        "document_path": task.payload.get("document_path"),
        "document_hash": task.payload.get("document_hash"),
        **extra,
    }


def _invalid_asyncapi_result(task: VerificationTask, reason: str) -> BackendResult:
    return BackendResult(
        backend="asyncapi",
        status="invalid",
        evidence_level=EvidenceLevel.TYPE_CHECKED,
        details=_task_details(task, reason=reason),
    )


def _is_event_emission_claim(ir: RequirementIR) -> bool:
    return ir.claim.expected.kind == "emit" and ir.claim.expected.target is not None


def _matches_expected_type(symbol: Symbol, expected_type: str | None) -> bool:
    if expected_type is None:
        return True
    return symbol.symbol_type == expected_type


def _string_or_none(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _string_list(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    return []


def _safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]+", "_", value).strip("_") or "operation"


def _symbol_sort_key(symbol: Symbol) -> tuple[str, str, int]:
    raw_index = symbol.metadata.get("operation_index", 0)
    index = raw_index if isinstance(raw_index, int) else 0
    return (symbol.name, symbol.symbol_type, index)
