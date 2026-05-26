from __future__ import annotations

from pathlib import Path
from typing import Any

from lark import Lark, Token, Tree

from .models import (
    Approval,
    Claim,
    ExpectedResult,
    Predicate,
    RequirementIR,
    RequirementSource,
    SourceSpan,
    ValueRef,
)


GRAMMAR_PATH = Path(__file__).with_name("grammar.lark")


def normalize_controlled_text(text: str) -> str:
    """Canonicalize controlled text before parsing so source spans are stable."""
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    return "\n".join(lines) + "\n"


class RequirementParser:
    def __init__(self) -> None:
        self._parser = Lark(
            GRAMMAR_PATH.read_text(),
            parser="lalr",
            propagate_positions=True,
            maybe_placeholders=False,
        )

    def parse(self, text: str) -> dict[str, Any]:
        controlled = normalize_controlled_text(text)
        return _requirement_to_ast(self._parser.parse(controlled), controlled)

    def parse_ir(
        self,
        text: str,
        *,
        requirement_id: str,
        title: str,
        claim_kind: str,
        original_text: str | None = None,
        approved_by: str | None = None,
        approved_at: str | None = None,
    ) -> RequirementIR:
        controlled = normalize_controlled_text(text)
        parsed = _requirement_to_ast(self._parser.parse(controlled), controlled)
        approval = None
        if approved_by or approved_at:
            approval = Approval(
                status="approved",
                approved_by=approved_by,
                approved_at=approved_at,
            )
        return RequirementIR(
            requirement_id=requirement_id,
            title=title,
            source=RequirementSource(
                original_text=original_text,
                controlled_text=controlled,
                controlled_text_approval=approval,
            ),
            claim=Claim(
                kind=claim_kind,  # type: ignore[arg-type]
                action=parsed["action"],
                forall=[{"name": parsed["entity"], "type": _pascal_case(parsed["entity"])}],
                condition=parsed["conditions"],
                expected=parsed["expected"],
            ),
        )


def _requirement_to_ast(tree: Tree, text: str) -> dict[str, Any]:
    requirement = tree.children[0]
    if not isinstance(requirement, Tree) or requirement.data != "requirement":
        raise ValueError("expected requirement")

    children = [child for child in requirement.children if isinstance(child, Tree)]
    entity = _name(children[0])
    conditions = _condition_block(children[1], text)
    action = _name(children[2])
    expected = _expected(children[3], text)

    return {
        "kind": "universal_rule",
        "entity": entity,
        "conditions": conditions,
        "action": action,
        "expected": expected,
    }


def _condition_block(tree: Tree, text: str) -> list[Predicate]:
    if tree.data != "condition_block":
        raise ValueError("expected condition_block")
    return [_predicate(child, text) for child in tree.children if isinstance(child, Tree)]


def _predicate(tree: Tree, text: str) -> Predicate:
    if tree.data == "condition":
        return _predicate(tree.children[0], text)

    span = _span(tree, text)

    if tree.data == "auth_condition":
        return Predicate(
            op="not_authorized",
            args=[_value(tree.children[0])],
            source_span=span,
        )
    if tree.data == "approved":
        op = "not_approved" if "not approved" in span.text else "approved"
        return Predicate(op=op, args=[_value(tree.children[0])], source_span=span)
    if tree.data == "negated_equality":
        return Predicate(
            op="neq",
            args=[_value(tree.children[0]), _value(tree.children[1])],
            source_span=span,
        )
    if tree.data == "equality":
        return Predicate(
            op="eq",
            args=[_value(tree.children[0]), _value(tree.children[1])],
            source_span=span,
        )
    if tree.data == "membership":
        return Predicate(
            op="in",
            args=[_value(tree.children[0]), _value(tree.children[1])],
            source_span=span,
        )
    if tree.data == "comparison":
        return Predicate(
            op=_comparison_op(tree.children[1]),
            args=[_value(tree.children[0]), _value(tree.children[2])],
            source_span=span,
        )

    raise ValueError(f"unsupported predicate: {tree.data}")


def _expected(tree: Tree, text: str) -> ExpectedResult:
    child = tree.children[0] if tree.data == "expected_result" else tree
    span = _span(child, text)
    if child.data == "rejected_before":
        return ExpectedResult(kind="rejected_before", target=_name(child.children[0]), source_span=span)
    if child.data == "rejected":
        return ExpectedResult(kind="rejected", source_span=span)
    if child.data == "succeed":
        return ExpectedResult(kind="succeed", source_span=span)
    if child.data == "emit":
        return ExpectedResult(kind="emit", target=_name(child.children[0]), source_span=span)
    if child.data == "not_change":
        return ExpectedResult(kind="not_change", target=_name(child.children[0]), source_span=span)
    if child.data == "set_value":
        return ExpectedResult(
            kind="set",
            target=_name(child.children[0]),
            value=_value(child.children[1]),
            source_span=span,
        )
    if child.data == "increase":
        return ExpectedResult(
            kind="increase",
            target=_name(child.children[0]),
            value=_value(child.children[1]),
            source_span=span,
        )
    if child.data == "decrease":
        return ExpectedResult(
            kind="decrease",
            target=_name(child.children[0]),
            value=_value(child.children[1]),
            source_span=span,
        )
    raise ValueError(f"unsupported expected result: {child.data}")


def _span(tree: Tree, text: str) -> SourceSpan:
    return SourceSpan(
        document="controlled_requirement",
        start_char=tree.meta.start_pos,
        end_char=tree.meta.end_pos,
        text=text[tree.meta.start_pos : tree.meta.end_pos],
    )


def _comparison_op(tree: Tree) -> str:
    mapping = {"gt": "gt", "lt": "lt", "gte": "gte", "lte": "lte"}
    if tree.data in mapping:
        return mapping[tree.data]
    child = tree.children[0]
    return mapping[child.data if isinstance(child, Tree) else tree.data]


def _value(tree: Tree | Token) -> ValueRef:
    if isinstance(tree, Token):
        return ValueRef(kind="identifier", value=str(tree))
    if tree.data == "value":
        return _value(tree.children[0])
    if tree.data == "name":
        return ValueRef(kind="identifier", value=_name(tree))
    if tree.data == "number":
        raw = str(tree.children[0])
        return ValueRef(kind="number", value=float(raw) if "." in raw else int(raw))
    if tree.data == "string":
        raw = str(tree.children[0])
        return ValueRef(kind="string", value=raw[1:-1])
    raise ValueError(f"unsupported value: {tree.data}")


def _name(tree: Tree | Token) -> str:
    if isinstance(tree, Token):
        return str(tree)
    if tree.data == "name":
        return str(tree.children[0])
    if tree.data == "entity":
        return "_".join(_name(child) for child in tree.children)
    raise ValueError(f"unsupported name tree: {tree.data}")


def _pascal_case(identifier: str) -> str:
    return "".join(part.capitalize() for part in identifier.split("_"))
