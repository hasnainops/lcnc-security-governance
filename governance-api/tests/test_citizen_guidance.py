import os
import sys
from pathlib import Path


os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://test:test@localhost:5432/test",
)

GOVERNANCE_API_ROOT = (
    Path(__file__).resolve().parents[1]
)

sys.path.insert(
    0,
    str(GOVERNANCE_API_ROOT),
)

from app import citizen_guidance as guidance


def test_perfect_score_is_gold():
    controls = [
        {"status": "pass"}
        for _ in range(7)
    ]

    score = guidance.calculate_score(
        controls
    )

    assert score == 100
    assert (
        guidance.badge_for_score(score)
        == "gold"
    )


def test_mixed_score_is_bronze():
    controls = (
        [{"status": "pass"}] * 4
        + [{"status": "fail"}] * 2
        + [{"status": "not_assessed"}]
    )

    score = guidance.calculate_score(
        controls
    )

    assert score == 64
    assert (
        guidance.badge_for_score(score)
        == "bronze"
    )


def test_low_score_needs_attention():
    controls = (
        [{"status": "pass"}]
        + [{"status": "fail"}] * 6
    )

    score = guidance.calculate_score(
        controls
    )

    assert score == 14
    assert (
        guidance.badge_for_score(score)
        == "needs_attention"
    )
