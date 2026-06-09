"""PC-2 — the frozen Pillar C contracts must match their committed JSON Schemas.

These are the B↔C / A↔C contracts the parallel pillars build against. A field change here is only
allowed as a deliberate schema bump: regenerate the committed schema and version-stamp the contract.
An accidental change fails this test (and CI's drift check) rather than silently breaking Pillar B.
"""

import json
from pathlib import Path

from nlreq.c_contracts import (
    C_SIDE_CONTRACT_INTERFACE_VERSION,
    FROZEN_C_CONTRACTS,
    FROZEN_SYSTEM_SPEC_ENTRY_OPERATOR_FIELDS,
)
from nlreq.models import NormalizedTrace
from nlreq.system_spec import SystemSpecEntry


SCHEMA_DIR = Path(__file__).resolve().parents[1] / "schemas"


def _committed(filename: str) -> str:
    return (SCHEMA_DIR / filename).read_text()


def _generated(model) -> str:
    return json.dumps(model.model_json_schema(), indent=2, sort_keys=True) + "\n"


def test_frozen_c_contract_schemas_match_committed_files() -> None:
    assert FROZEN_C_CONTRACTS, "the frozen C contract set must not be empty"
    for contract in FROZEN_C_CONTRACTS:
        committed_path = SCHEMA_DIR / contract.schema_file
        assert committed_path.exists(), f"{contract.contract_id}: missing committed schema {contract.schema_file}"
        assert _committed(contract.schema_file) == _generated(contract.model), (
            f"schema drift for frozen C contract {contract.contract_id}: "
            f"{contract.schema_file} does not match the model — regenerate and version-bump"
        )


def test_each_frozen_contract_is_version_stamped() -> None:
    assert C_SIDE_CONTRACT_INTERFACE_VERSION == "1.0"
    for contract in FROZEN_C_CONTRACTS:
        assert contract.version, f"{contract.contract_id} must pin a frozen version"


def test_system_spec_entry_operator_fields_are_frozen() -> None:
    """init_op/next_op/invariants are the operator metadata the S∧R composition reads; freeze them
    both on the model and in the committed registry schema."""
    fields = SystemSpecEntry.model_fields
    for field in FROZEN_SYSTEM_SPEC_ENTRY_OPERATOR_FIELDS:
        assert field in fields, f"SystemSpecEntry lost frozen operator field {field}"

    registry_schema = json.loads(_committed("system-spec-registry.schema.json"))
    entry_schema = registry_schema["$defs"]["SystemSpecEntry"]["properties"]
    for field in FROZEN_SYSTEM_SPEC_ENTRY_OPERATOR_FIELDS:
        assert field in entry_schema, f"committed registry schema lost SystemSpecEntry.{field}"


def test_normalized_trace_carries_producer_provenance_and_documents_normalization() -> None:
    assert "producer" in NormalizedTrace.model_fields
    doc = NormalizedTrace.__doc__ or ""
    # The lossy EVM-vs-Go normalization rules are pinned inline on the contract.
    assert "EVM" in doc and "Go" in doc
    assert "lossy" in doc.lower()
