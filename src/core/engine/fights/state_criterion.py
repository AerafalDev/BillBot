from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cache


_STATE_PREDICATE = re.compile(r"HS([=!])(\d+)")


@dataclass(frozen=True)
class _StatePredicate:
    state_id: int
    must_be_present: bool


@dataclass(frozen=True)
class _LogicalExpression:
    operator: str
    left: _StateExpression
    right: _StateExpression


_StateExpression = _StatePredicate | _LogicalExpression


class _StateCriterionParser:
    def __init__(self, criterion: str) -> None:
        self.criterion = criterion
        self.position = 0

    def parse(self) -> _StateExpression:
        expression = self._parse_or()
        self._skip_whitespace()
        if self.position != len(self.criterion):
            raise ValueError("Unexpected data after state criterion")
        return expression

    def _parse_or(self) -> _StateExpression:
        expression = self._parse_and()
        while self._consume("|"):
            expression = _LogicalExpression("|", expression, self._parse_and())
        return expression

    def _parse_and(self) -> _StateExpression:
        expression = self._parse_atom()
        while self._consume("&"):
            expression = _LogicalExpression("&", expression, self._parse_atom())
        return expression

    def _parse_atom(self) -> _StateExpression:
        self._skip_whitespace()
        if self._consume("("):
            expression = self._parse_or()
            if not self._consume(")"):
                raise ValueError("Unclosed state criterion group")
            return expression

        match = _STATE_PREDICATE.match(self.criterion, self.position)
        if match is None:
            raise ValueError("Unsupported state criterion")

        self.position = match.end()
        return _StatePredicate(int(match.group(2)), match.group(1) == "=")

    def _consume(self, token: str) -> bool:
        self._skip_whitespace()
        if not self.criterion.startswith(token, self.position):
            return False
        self.position += len(token)
        return True

    def _skip_whitespace(self) -> None:
        while self.position < len(self.criterion) and self.criterion[self.position].isspace():
            self.position += 1


@cache
def _parse_state_criterion(criterion: str) -> _StateExpression | None:
    try:
        return _StateCriterionParser(criterion).parse()
    except ValueError:
        return None


def _is_expression_respected(expression: _StateExpression, state_ids: frozenset[int]) -> bool:
    if isinstance(expression, _StatePredicate):
        return (expression.state_id in state_ids) == expression.must_be_present

    if expression.operator == "&":
        return _is_expression_respected(expression.left, state_ids) and _is_expression_respected(
            expression.right, state_ids
        )
    return _is_expression_respected(expression.left, state_ids) or _is_expression_respected(
        expression.right, state_ids
    )


def is_spell_state_criterion_satisfied(
    criterion: str,
    state_ids: frozenset[int],
) -> bool:
    if not criterion:
        return True

    expression = _parse_state_criterion(criterion)
    return expression is not None and _is_expression_respected(expression, state_ids)
