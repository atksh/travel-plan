from __future__ import annotations

from app.services.rule_validation import validate_rule_payload
import pytest


def test_soft_rule_requires_weight() -> None:
    with pytest.raises(Exception):
        validate_rule_payload(
            rule_kind="preference_match",
            mode="soft",
            operator="prefer",
            target_kind="tag",
            parameters={},
            weight=None,
        )


def test_hard_rule_rejects_weight() -> None:
    with pytest.raises(Exception):
        validate_rule_payload(
            rule_kind="selection_exclude",
            mode="hard",
            operator="exclude",
            target_kind="tag",
            parameters={},
            weight=1,
        )


def test_arrival_window_requires_after_and_before() -> None:
    with pytest.raises(Exception):
        validate_rule_payload(
            rule_kind="arrival_window",
            mode="hard",
            operator="require_between",
            target_kind="place",
            parameters={"arrive_after_min": 600},
            weight=None,
        )


def test_valid_selection_count_rule_passes() -> None:
    validate_rule_payload(
        rule_kind="selection_count",
        mode="soft",
        operator="include",
        target_kind="tag",
        parameters={"min_count": 1},
        weight=3,
    )
