from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.errors import RequestContractError


@dataclass(frozen=True)
class RuleDefinition:
    allowed_modes: set[str]
    allowed_operators: set[str]
    allowed_target_kinds: set[str]
    required_parameter_keys: set[str]


RULE_MATRIX: dict[str, RuleDefinition] = {
    "selection_count": RuleDefinition(
        allowed_modes={"hard", "soft"},
        allowed_operators={"include", "limit"},
        allowed_target_kinds={"place", "tag", "trait", "category", "source"},
        required_parameter_keys=set(),
    ),
    "selection_exclude": RuleDefinition(
        allowed_modes={"hard"},
        allowed_operators={"exclude"},
        allowed_target_kinds={"place", "tag", "trait", "category", "source"},
        required_parameter_keys=set(),
    ),
    "preference_match": RuleDefinition(
        allowed_modes={"soft"},
        allowed_operators={"prefer", "avoid"},
        allowed_target_kinds={"place", "tag", "trait", "category", "source", "price_band", "rating"},
        required_parameter_keys=set(),
    ),
    "order_dependency": RuleDefinition(
        allowed_modes={"hard", "soft"},
        allowed_operators={"require_before", "require_after", "lock", "prefer"},
        allowed_target_kinds={"place_pair", "place"},
        required_parameter_keys=set(),
    ),
    "arrival_window": RuleDefinition(
        allowed_modes={"hard", "soft"},
        allowed_operators={"require_between", "prefer"},
        allowed_target_kinds={"place"},
        required_parameter_keys={"arrive_after_min", "arrive_before_min"},
    ),
    "stay_duration": RuleDefinition(
        allowed_modes={"hard", "soft"},
        allowed_operators={"limit", "prefer"},
        allowed_target_kinds={"place"},
        required_parameter_keys=set(),
    ),
    "continuous_travel_limit": RuleDefinition(
        allowed_modes={"hard", "soft"},
        allowed_operators={"limit", "avoid"},
        allowed_target_kinds={"trip"},
        required_parameter_keys={"max_minutes"},
    ),
    "context_filter": RuleDefinition(
        allowed_modes={"hard", "soft"},
        allowed_operators={"exclude", "avoid", "include", "prefer"},
        allowed_target_kinds={"tag", "trait", "category"},
        required_parameter_keys={"context_key", "context_value"},
    ),
}


def _raise_validation(field: str, message: str, *, rule_kind: str) -> None:
    raise RequestContractError(
        "RULE_VALIDATION_FAILED",
        message,
        details={"rule_kind": rule_kind, "field": field},
    )


def validate_rule_payload(
    *,
    rule_kind: str,
    mode: str,
    operator: str,
    target_kind: str,
    parameters: dict[str, Any] | None,
    weight: float | None,
) -> None:
    definition = RULE_MATRIX.get(rule_kind)
    if definition is None:
        _raise_validation("rule_kind", f"Unsupported rule_kind={rule_kind}.", rule_kind=rule_kind)
    if mode not in definition.allowed_modes:
        _raise_validation("mode", f"mode={mode} is not allowed for {rule_kind}.", rule_kind=rule_kind)
    if operator not in definition.allowed_operators:
        _raise_validation(
            "operator",
            f"operator={operator} is not allowed for {rule_kind}.",
            rule_kind=rule_kind,
        )
    if target_kind not in definition.allowed_target_kinds:
        _raise_validation(
            "target.kind",
            f"target.kind={target_kind} is not allowed for {rule_kind}.",
            rule_kind=rule_kind,
        )
    parameters = parameters or {}
    for required_key in definition.required_parameter_keys:
        if required_key not in parameters:
            _raise_validation(
                f"parameters.{required_key}",
                f"parameters.{required_key} is required for {rule_kind}.",
                rule_kind=rule_kind,
            )
    if mode == "soft" and weight is None:
        _raise_validation("weight", "Soft rules require a weight.", rule_kind=rule_kind)
    if mode == "hard" and weight is not None:
        _raise_validation("weight", "Hard rules must not provide a weight.", rule_kind=rule_kind)
    if rule_kind == "selection_count":
        min_count = parameters.get("min_count")
        max_count = parameters.get("max_count")
        exact_count = parameters.get("exact_count")
        if exact_count is not None and not isinstance(exact_count, int):
            _raise_validation("parameters.exact_count", "exact_count must be an integer.", rule_kind=rule_kind)
        if min_count is not None and not isinstance(min_count, int):
            _raise_validation("parameters.min_count", "min_count must be an integer.", rule_kind=rule_kind)
        if max_count is not None and not isinstance(max_count, int):
            _raise_validation("parameters.max_count", "max_count must be an integer.", rule_kind=rule_kind)
    if rule_kind == "arrival_window":
        after = parameters.get("arrive_after_min")
        before = parameters.get("arrive_before_min")
        if not isinstance(after, int) or not isinstance(before, int):
            _raise_validation(
                "parameters",
                "arrival_window requires integer arrive_after_min and arrive_before_min.",
                rule_kind=rule_kind,
            )
        if before < after:
            _raise_validation(
                "parameters.arrive_before_min",
                "arrive_before_min must be greater than or equal to arrive_after_min.",
                rule_kind=rule_kind,
            )
    if rule_kind == "continuous_travel_limit":
        max_minutes = parameters.get("max_minutes")
        if not isinstance(max_minutes, int) or max_minutes <= 0:
            _raise_validation(
                "parameters.max_minutes",
                "max_minutes must be a positive integer.",
                rule_kind=rule_kind,
            )
    if rule_kind == "context_filter":
        if not isinstance(parameters.get("context_key"), str):
            _raise_validation("parameters.context_key", "context_key must be a string.", rule_kind=rule_kind)
        if "context_value" not in parameters:
            _raise_validation("parameters.context_value", "context_value is required.", rule_kind=rule_kind)
