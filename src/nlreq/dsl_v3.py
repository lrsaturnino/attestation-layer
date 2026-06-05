from __future__ import annotations

from pathlib import Path
from typing import Any

from lark import Lark, Token, Tree
from lark.exceptions import LarkError, UnexpectedInput

from .models import (
    RequirementIRV2,
    RequirementSource,
    SemanticNode,
    SemanticProvenance,
    SourceSpan,
    TemporalBound,
    ValueRef,
)


DSL_V3_VERSION = "0.3"
DSL_V3_GRAMMAR_PATH = Path(__file__).with_name("dsl_v3.lark")


class DslV3ParseError(ValueError):
    def __init__(self, message: str, *, line: int | None = None, column: int | None = None) -> None:
        self.line = line
        self.column = column
        location = f" at line {line}, column {column}" if line is not None and column is not None else ""
        super().__init__(f"dsl_v3_parse_error{location}: {message}")


class DslV3Parser:
    def __init__(self) -> None:
        self._parser = Lark(
            DSL_V3_GRAMMAR_PATH.read_text(),
            parser="lalr",
            propagate_positions=True,
            maybe_placeholders=False,
        )

    def parse_ir(self, text: str, *, requirement_id: str, title: str) -> RequirementIRV2:
        controlled = canonicalize_dsl_v3_text(text)
        try:
            tree = self._parser.parse(controlled)
        except UnexpectedInput as exc:
            raise DslV3ParseError(
                "unsupported or malformed DSL v3 fragment",
                line=exc.line,
                column=exc.column,
            ) from exc
        except LarkError as exc:
            raise DslV3ParseError(str(exc)) from exc
        semantic_ir, requirement_class = _requirement_to_semantic_ir(tree, controlled)
        return RequirementIRV2(
            requirement_id=requirement_id,
            title=title,
            source=RequirementSource(controlled_text=controlled),
            semantic_ir=semantic_ir,
        )


def canonicalize_dsl_v3_text(text: str) -> str:
    lines = [" ".join(line.strip().split()) for line in text.strip().splitlines() if line.strip()]
    return "\n".join(lines) + "\n"


def _requirement_to_semantic_ir(tree: Tree, text: str) -> tuple[SemanticNode, str]:
    requirement = tree.children[0]
    if not isinstance(requirement, Tree) or requirement.data != "requirement":
        raise DslV3ParseError("expected requirement")
    requirement_class = _token_text(requirement.children[0])
    children = [child for child in requirement.children if isinstance(child, Tree)]
    scope = _scope(children[0], text)
    premise = _premise_block(children[1], text)
    action, obligations = _obligation_block(children[2], text)
    must = obligations[0] if len(obligations) == 1 else _node(
        "obligation.must",
        "and",
        text=text,
        tree=children[2],
        children=obligations,
    )
    root = _node(
        "rule.root",
        "rule",
        text=text,
        tree=requirement,
        children=[],
        scope=[scope],
        premise=premise,
        obligation=_node(
            "obligation.root",
            "action_obligation",
            text=text,
            tree=children[2],
            action=action,
            must=must,
        ),
        metadata={"dsl_version": DSL_V3_VERSION, "requirement_class": requirement_class},
    )
    return root, requirement_class


def _scope(tree: Tree, text: str) -> SemanticNode:
    name = _token_text(tree.children[0])
    return _node(
        "scope.0",
        "forall",
        text=text,
        tree=tree,
        name=name,
        target=_pascal_case(name),
    )


def _premise_block(tree: Tree, text: str) -> SemanticNode:
    premises = [
        _premise(child, text, index)
        for index, child in enumerate(tree.children)
        if isinstance(child, Tree)
    ]
    return _node("premise.root", "and", text=text, tree=tree, children=premises)


def _premise(tree: Tree, text: str, index: int) -> SemanticNode:
    if tree.data in {"authorized", "not_authorized", "approved", "not_approved", "confirmed"}:
        return _node(
            f"premise.{index}",
            "predicate",
            text=text,
            tree=tree,
            name=tree.data,
            args=[_identifier(tree.children[0])],
        )
    if tree.data == "state_is":
        return _node(
            f"premise.{index}",
            "eq",
            text=text,
            tree=tree,
            args=[_identifier(tree.children[0]), _value(tree.children[1])],
            metadata={"predicate": "state_is"},
        )
    if tree.data == "comparison":
        return _node(
            f"premise.{index}",
            _comparison_kind(tree.children[1]),
            text=text,
            tree=tree,
            args=[_value(tree.children[0]), _value(tree.children[2])],
        )
    if tree.data == "membership_set":
        # `x is in {A, B, ...}` — a concrete, enumerable set. The grammar keeps only the NAME
        # children (the `{`, `,`, `}` are anonymous terminals), so children[0] is the element and
        # children[1:] are the members. The `set_literal` marker lets the SMT encoder distinguish
        # this from the opaque named-set membership below (`x is in S`, a single identifier whose
        # contents are unknown), which stays a model-level/needs-review check.
        return _node(
            f"premise.{index}",
            "membership",
            text=text,
            tree=tree,
            args=[_identifier(child) for child in tree.children],
            metadata={"membership": "set_literal"},
        )
    if tree.data == "membership":
        return _node(
            f"premise.{index}",
            "membership",
            text=text,
            tree=tree,
            args=[_identifier(tree.children[0]), _identifier(tree.children[1])],
        )
    raise DslV3ParseError(f"unsupported premise: {tree.data}")


def _obligation_block(tree: Tree, text: str) -> tuple[SemanticNode, list[SemanticNode]]:
    obligation_trees = [child for child in tree.children if isinstance(child, Tree)]
    action_name = _primary_action_name(obligation_trees[0]) if obligation_trees else "requirement_action"
    action = _node("obligation.action", "action", text=text, tree=tree, name=action_name)
    obligations = [
        _obligation(child, text, index) for index, child in enumerate(obligation_trees)
    ]
    return action, obligations


def _obligation(tree: Tree, text: str, index: int) -> SemanticNode:
    if tree.data == "succeed":
        return _node(
            f"obligation.{index}",
            "predicate",
            text=text,
            tree=tree,
            name="succeeds",
            args=[_identifier(tree.children[0])],
        )
    if tree.data == "reject_before":
        return _node(
            f"obligation.{index}",
            "before",
            text=text,
            tree=tree,
            children=[
                _node(
                    f"obligation.{index}.reject",
                    "predicate",
                    text=text,
                    tree=tree,
                    name="rejects",
                    args=[_identifier(tree.children[0])],
                ),
                _node(
                    f"obligation.{index}.before",
                    "state_ref",
                    text=text,
                    tree=tree,
                    name=_token_text(tree.children[1]),
                ),
            ],
        )
    if tree.data == "state_be":
        return _node(
            f"obligation.{index}",
            "post_state",
            text=text,
            tree=tree,
            name=_token_text(tree.children[0]),
            value=_value(tree.children[1]),
        )
    if tree.data == "emit_within":
        return _node(
            f"obligation.{index}",
            "within",
            text=text,
            tree=tree,
            temporal_bound=TemporalBound(
                value=_number(tree.children[1]),
                unit=_singular_unit(_token_text(tree.children[2])),
            ),
            children=[
                _node(
                    f"obligation.{index}.event",
                    "event",
                    text=text,
                    tree=tree,
                    name=_token_text(tree.children[0]),
                )
            ],
        )
    if tree.data == "keep_comparison":
        return _node(
            f"obligation.{index}",
            _comparison_kind(tree.children[1]),
            text=text,
            tree=tree,
            args=[_identifier(tree.children[0]), _value(tree.children[2])],
        )
    if tree.data == "cross_module_causal":
        source_module = _token_text(tree.children[0])
        target_module = _token_text(tree.children[1])
        action_name = _token_text(tree.children[2])
        return _node(
            f"obligation.{index}",
            "within",
            text=text,
            tree=tree,
            temporal_bound=TemporalBound(
                value=_number(tree.children[3]),
                unit=_singular_unit(_token_text(tree.children[4])),
            ),
            children=[
                _node(
                    f"obligation.{index}.transition",
                    "transition",
                    text=text,
                    tree=tree,
                    name=action_name,
                    metadata={"source_module": source_module, "target_module": target_module},
                )
            ],
            metadata={"obligation_kind": "cross_module_causal"},
        )
    raise DslV3ParseError(f"unsupported obligation: {tree.data}")


def _primary_action_name(tree: Tree) -> str:
    if tree.data in {"succeed", "reject_before"}:
        return _token_text(tree.children[0])
    if tree.data == "cross_module_causal":
        return _token_text(tree.children[2])
    if tree.data == "emit_within":
        return f"emit_{_token_text(tree.children[0])}"
    if tree.data == "state_be":
        return f"set_{_token_text(tree.children[0])}"
    if tree.data == "keep_comparison":
        return f"keep_{_token_text(tree.children[0])}"
    return "requirement_action"


def _node(
    node_id: str,
    kind: str,
    *,
    text: str,
    tree: Tree,
    **kwargs: Any,
) -> SemanticNode:
    return SemanticNode(
        node_id=node_id,
        kind=kind,  # type: ignore[arg-type]
        source_spans=[_span(tree, text)],
        provenance=SemanticProvenance(
            source_document="controlled_requirement",
            derived_from=[node_id],
            method="deterministic_parse",
            tool="nlreq.dsl_v3",
            tool_version=DSL_V3_VERSION,
        ),
        confidence="deterministic_parse",
        **kwargs,
    )


def _span(tree: Tree, text: str) -> SourceSpan:
    return SourceSpan(
        document="controlled_requirement",
        start_char=tree.meta.start_pos,
        end_char=tree.meta.end_pos,
        text=text[tree.meta.start_pos : tree.meta.end_pos],
    )


def _identifier(value: Tree | Token) -> ValueRef:
    return ValueRef(kind="identifier", value=_token_text(value))


def _value(value: Tree | Token) -> ValueRef:
    if isinstance(value, Token):
        if value.type == "NUMBER":
            return ValueRef(kind="number", value=_number(value))
        if value.type == "ESCAPED_STRING":
            return ValueRef(kind="string", value=str(value)[1:-1])
        return ValueRef(kind="identifier", value=str(value))
    if value.data == "value":
        return _value(value.children[0])
    if value.data == "name_value":
        return _identifier(value.children[0])
    if value.data == "number":
        return ValueRef(kind="number", value=_number(value.children[0]))
    if value.data == "string":
        return ValueRef(kind="string", value=_token_text(value.children[0])[1:-1])
    raise DslV3ParseError(f"unsupported value: {value.data}")


def _comparison_kind(value: Tree | Token) -> str:
    if isinstance(value, Tree) and value.data == "comp":
        value = value.children[0]
    if isinstance(value, Tree):
        return str(value.data)
    mapping = {"==": "eq", "!=": "neq", "<": "lt", "<=": "lte", ">": "gt", ">=": "gte"}
    return mapping[str(value)]


def _token_text(value: Tree | Token) -> str:
    if isinstance(value, Token):
        return str(value)
    if len(value.children) != 1:
        raise DslV3ParseError(f"expected token for {value.data}")
    return _token_text(value.children[0])


def _number(value: Tree | Token) -> int | float:
    raw = _token_text(value)
    return float(raw) if "." in raw else int(raw)


def _singular_unit(value: str) -> str:
    return value[:-1] if value.endswith("s") else value


def _pascal_case(value: str) -> str:
    return "".join(part.capitalize() for part in value.split("_"))
