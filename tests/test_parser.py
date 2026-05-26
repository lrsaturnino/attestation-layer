from pathlib import Path

from nlreq.parser import RequirementParser, normalize_controlled_text


FIXTURES = Path(__file__).parent / "fixtures" / "requirements"


def test_parse_authorization_precondition() -> None:
    text = (FIXTURES / "authorization_precondition.nlreq").read_text()
    ast = RequirementParser().parse(text)

    assert ast["kind"] == "universal_rule"
    assert ast["entity"] == "operation_request"
    assert ast["action"] == "operation"
    assert [condition.op for condition in ast["conditions"]] == ["not_authorized"]
    assert ast["expected"].kind == "rejected_before"
    assert ast["expected"].target == "state_change"
    assert ast["conditions"][0].source_span.text == "actor is not authorized"


def test_parse_ir_is_deterministic() -> None:
    text = (FIXTURES / "state_postcondition.nlreq").read_text()
    parser = RequirementParser()

    first = parser.parse_ir(
        text,
        requirement_id="REQ-STATE-001",
        title="State postcondition",
        claim_kind="state_postcondition",
    )
    second = parser.parse_ir(
        text,
        requirement_id="REQ-STATE-001",
        title="State postcondition",
        claim_kind="state_postcondition",
    )

    assert first.model_dump(mode="json", exclude_none=True) == second.model_dump(
        mode="json", exclude_none=True
    )


def test_normalization_stabilizes_source_spans() -> None:
    raw = "\n  For every operation request:\n    if actor is approved\n    then operation must succeed.\n\n"

    assert normalize_controlled_text(raw) == (
        "For every operation request:\n"
        "if actor is approved\n"
        "then operation must succeed.\n"
    )
