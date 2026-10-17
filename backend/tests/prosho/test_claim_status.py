import math

import pytest

from app.prosho.models.enums import ClaimTargetOp as Op
from app.prosho.services.claim_status import computed_status, target_met


@pytest.mark.parametrize("op,target,hi,value,expected", [
    (Op.gte, 90, None, 90, True), (Op.gte, 90, None, 89.99, False),
    (Op.lte, 0.5, None, 0.5, True), (Op.lte, 0.5, None, 0.51, False),
    (Op.abs_lte, 25, None, -12, True), (Op.abs_lte, 25, None, 25, True), (Op.abs_lte, 25, None, -25.1, False),
    (Op.between, 1, 2, 1, True), (Op.between, 1, 2, 2, True), (Op.between, 1, 2, 2.01, False), (Op.between, 1, 2, 0.99, False),
    (Op.eq, 3, None, 3.0, True), (Op.eq, 0.3, None, 0.1 + 0.2, True), (Op.eq, 3, None, 3.1, False),
    (Op.gte, 1, None, math.nan, False),
])
def test_operators(op, target, hi, value, expected):
    assert target_met(op, target, hi, value) is expected


def test_missing_evidence_or_target():
    assert computed_status(Op.gte, 1, None, None) == "awaiting_evidence"
    assert computed_status(None, None, None, 5) == "awaiting_evidence"
    assert computed_status(Op.gte, 1, None, 5) == "met"
    assert computed_status(Op.gte, 10, None, 5) == "not_met"
