"""A measured claim's status, computed — never typed in (BETA_PLAN §7).

The latest metric evidence for the claim's `metric_key` is compared with its
target. Pure functions, so the rule is easy to read and test.
"""
from __future__ import annotations

import math
from typing import Literal, Optional

from app.prosho.models.enums import ClaimTargetOp

ComputedStatus = Literal["met", "not_met", "awaiting_evidence"]
EQ_TOLERANCE = 1e-9


def target_met(op: ClaimTargetOp, target: float, target_hi: Optional[float], value: float) -> bool:
    if math.isnan(value):
        return False
    if op == ClaimTargetOp.gte:
        return value >= target
    if op == ClaimTargetOp.lte:
        return value <= target
    if op == ClaimTargetOp.abs_lte:
        return abs(value) <= target
    if op == ClaimTargetOp.between:
        return target <= value <= (target_hi if target_hi is not None else target)
    if op == ClaimTargetOp.eq:
        return math.isclose(value, target, rel_tol=EQ_TOLERANCE, abs_tol=EQ_TOLERANCE)
    raise ValueError(f"unknown op {op}")


def computed_status(op: Optional[ClaimTargetOp], target: Optional[float], target_hi: Optional[float],
                    latest_value: Optional[float]) -> ComputedStatus:
    if op is None or target is None or latest_value is None:
        return "awaiting_evidence"
    return "met" if target_met(op, target, target_hi, latest_value) else "not_met"
