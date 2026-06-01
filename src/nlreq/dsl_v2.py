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


DSL_V2_VERSION = "0.1"
DSL_V2_GRAMMAR_PATH = Path(__file__).with_name("dsl_v2.lark")


class DslV2ParseError(ValueError):
    def __init__(self, message: str, *, line: int | None = None, column: int | None = None) -> None:
        self.line = line
        self.column = column
        location = f" at line {line}, column {column}" if line is not None and column is not None else ""
        super().__init__(f"dsl_v2_parse_error{location}: {message}")


class DslV2Parser:
    def __init__(self) -> None:
        self._parser = Lark(
            DSL_V2_GRAMMAR_PATH.read_text(),
            parser="lalr",
            propagate_positions=True,
            maybe_placeholders=False,
        )

    def parse_ir(self, text: str, *, requirement_id: str, title: str) -> RequirementIRV2:
        controlled = normalize_dsl_v2_text(text)
        try:
            tree = self._parser.parse(controlled)
        except UnexpectedInput as exc:
            raise DslV2ParseError(
                "unsupported or malformed DSL v2 fragment",
                line=exc.line,
                column=exc.column,
            ) from exc
        except LarkError as exc:
            raise DslV2ParseError(str(exc)) from exc
        parsed = _requirement_to_semantic_ir(tree, controlled)
        return RequirementIRV2(
            requirement_id=requirement_id,
            title=title,
            source=RequirementSource(controlled_text=controlled),
            semantic_ir=parsed,
        )


def normalize_dsl_v2_text(text: str) -> str:
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    return "\n".join(lines) + "\n"


def _requirement_to_semantic_ir(tree: Tree, text: str) -> SemanticNode:
    requirement = tree.children[0]
    if not isinstance(requirement, Tree) or requirement.data != "requirement":
        raise DslV2ParseError("expected requirement")
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
    return _node(
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
    )


def _scope(tree: Tree, text: str) -> SemanticNode:
    return _node(
        "scope.0",
        "forall",
        text=text,
        tree=tree,
        name=_token_text(tree.children[0]),
        target=_pascal_case(_token_text(tree.children[0])),
    )


def _premise_block(tree: Tree, text: str) -> SemanticNode:
    premises = [
        _premise(child, text, index)
        for index, child in enumerate(tree.children)
        if isinstance(child, Tree)
    ]
    return _node(
        "premise.root",
        "and",
        text=text,
        tree=tree,
        children=premises,
    )


def _premise(tree: Tree, text: str, index: int) -> SemanticNode:
    if tree.data == "authorized":
        return _node(
            f"premise.{index}",
            "predicate",
            text=text,
            tree=tree,
            name="authorized",
            args=[_identifier(tree.children[0])],
        )
    if tree.data == "confirmed":
        return _node(
            f"premise.{index}",
            "predicate",
            text=text,
            tree=tree,
            name="confirmed",
            args=[_identifier(tree.children[0])],
        )
    if tree.data in {"lte", "gte"}:
        return _node(
            f"premise.{index}",
            tree.data,
            text=text,
            tree=tree,
            args=[_identifier(tree.children[0]), _identifier(tree.children[1])],
        )
    raise DslV2ParseError(f"unsupported premise: {tree.data}")


def _obligation_block(tree: Tree, text: str) -> tuple[SemanticNode, list[SemanticNode]]:
    action = _node(
        "obligation.action",
        "action",
        text=text,
        tree=tree,
        name=_token_text(tree.children[0]),
    )
    obligations = [
        _obligation(child, text, index)
        for index, child in enumerate(tree.children[1:])
        if isinstance(child, Tree)
    ]
    return action, obligations


def _obligation(tree: Tree, text: str, index: int) -> SemanticNode:
    if tree.data == "emit_within":
        unit = _singular_unit(_token_text(tree.children[2]))
        return _node(
            f"obligation.{index}",
            "within",
            text=text,
            tree=tree,
            temporal_bound=TemporalBound(value=_number(tree.children[1]), unit=unit),
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
    if tree.data in {"keep_gte", "keep_lte"}:
        return _node(
            f"obligation.{index}",
            "gte" if tree.data == "keep_gte" else "lte",
            text=text,
            tree=tree,
            args=[_identifier(tree.children[0]), _identifier(tree.children[1])],
        )
    raise DslV2ParseError(f"unsupported obligation: {tree.data}")


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
            tool="nlreq.dsl_v2",
            tool_version=DSL_V2_VERSION,
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


def _identifier(token: Tree | Token) -> ValueRef:
    return ValueRef(kind="identifier", value=_token_text(token))


def _token_text(value: Tree | Token) -> str:
    if isinstance(value, Token):
        return str(value)
    if len(value.children) != 1:
        raise DslV2ParseError(f"expected token for {value.data}")
    return _token_text(value.children[0])


def _number(value: Tree | Token) -> int | float:
    raw = _token_text(value)
    return float(raw) if "." in raw else int(raw)


def _singular_unit(value: str) -> str:
    return value[:-1] if value.endswith("s") else value


def _pascal_case(value: str) -> str:
    return "".join(part.capitalize() for part in value.split("_"))
