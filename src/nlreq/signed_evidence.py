from __future__ import annotations

import hmac
from hashlib import sha256
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .jsonutil import canonical_json, sha256_json


SIGNED_EVIDENCE_SCHEMA_VERSION = "0.1"
SIGNED_EVIDENCE_TOOL_VERSION = "0.1"


class ProducerKey(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key_id: str
    producer_id: str
    algorithm: Literal["HMAC-SHA256"] = "HMAC-SHA256"
    public_hint: str | None = None
    trusted_for_high_assurance: bool = False


class ProducerKeyRegistry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = SIGNED_EVIDENCE_SCHEMA_VERSION
    keys: list[ProducerKey] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unique_keys(self) -> ProducerKeyRegistry:
        key_ids = [key.key_id for key in self.keys]
        if len(key_ids) != len(set(key_ids)):
            raise ValueError("key ids must be unique")
        return self


class SignedEvidenceEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = SIGNED_EVIDENCE_SCHEMA_VERSION
    envelope_id: str
    producer_id: str
    key_id: str
    algorithm: Literal["HMAC-SHA256"]
    payload_hash: str
    payload: dict[str, Any]
    signature: str
    tool: str = "nlreq.signed_evidence"
    tool_version: str = SIGNED_EVIDENCE_TOOL_VERSION


class SignatureVerificationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = SIGNED_EVIDENCE_SCHEMA_VERSION
    envelope_id: str
    result: Literal["valid", "invalid", "untrusted_key", "unknown_key"]
    reasons: list[str] = Field(default_factory=list)


def sign_evidence_payload(
    *,
    payload: dict[str, Any],
    producer_id: str,
    key_id: str,
    secret: str,
    envelope_id: str,
) -> SignedEvidenceEnvelope:
    payload_hash = sha256_json(payload)
    signature = _signature(payload_hash, producer_id=producer_id, key_id=key_id, secret=secret)
    return SignedEvidenceEnvelope(
        envelope_id=envelope_id,
        producer_id=producer_id,
        key_id=key_id,
        algorithm="HMAC-SHA256",
        payload_hash=payload_hash,
        payload=payload,
        signature=signature,
    )


def verify_signed_evidence(
    *,
    envelope: SignedEvidenceEnvelope,
    registry: ProducerKeyRegistry,
    secrets_by_key_id: dict[str, str],
    require_high_assurance_trust: bool = False,
) -> SignatureVerificationReport:
    key = next((item for item in registry.keys if item.key_id == envelope.key_id), None)
    if key is None:
        return SignatureVerificationReport(
            envelope_id=envelope.envelope_id,
            result="unknown_key",
            reasons=["key is not registered"],
        )
    if require_high_assurance_trust and not key.trusted_for_high_assurance:
        return SignatureVerificationReport(
            envelope_id=envelope.envelope_id,
            result="untrusted_key",
            reasons=["key is not trusted for high-assurance evidence"],
        )
    if key.producer_id != envelope.producer_id:
        return SignatureVerificationReport(
            envelope_id=envelope.envelope_id,
            result="invalid",
            reasons=["envelope producer does not match key registry"],
        )
    secret = secrets_by_key_id.get(envelope.key_id)
    if secret is None:
        return SignatureVerificationReport(
            envelope_id=envelope.envelope_id,
            result="unknown_key",
            reasons=["verification secret is unavailable"],
        )
    payload_hash = sha256_json(envelope.payload)
    expected = _signature(
        payload_hash,
        producer_id=envelope.producer_id,
        key_id=envelope.key_id,
        secret=secret,
    )
    reasons: list[str] = []
    if payload_hash != envelope.payload_hash:
        reasons.append("payload hash does not match envelope")
    if not hmac.compare_digest(expected, envelope.signature):
        reasons.append("signature mismatch")
    return SignatureVerificationReport(
        envelope_id=envelope.envelope_id,
        result="invalid" if reasons else "valid",
        reasons=reasons,
    )


def _signature(payload_hash: str, *, producer_id: str, key_id: str, secret: str) -> str:
    message = canonical_json(
        {"payload_hash": payload_hash, "producer_id": producer_id, "key_id": key_id}
    )
    digest = hmac.new(secret.encode("utf-8"), message.encode("utf-8"), sha256).hexdigest()
    return "hmac-sha256:" + digest
