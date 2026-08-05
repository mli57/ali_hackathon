"""Golden tests over the frozen demo profiles.

Runs the full deterministic path -- derive, match, benefit, aggregate -- with no
network and no model. Stage 3 is not involved: explanations are decoration and
a test that needed Bailian to pass would be a test that fails on stage wifi.

Run before every merge. It takes a second, and it is the difference between
someone fixing a predicate at 2am and someone quietly breaking the demo at 2am.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from backend.aggregator import aggregate
from backend.derive import derive
from backend.matchers import childcare, employment, housing
from backend.models import MatchResponse, Profile
from backend.rules import load_rules

FIXTURES = Path(__file__).parent / "fixtures" / "profiles.json"
CASES = json.loads(FIXTURES.read_text(encoding="utf-8"))["profiles"]


def run_match(profile: Profile) -> MatchResponse:
    rules = load_rules()
    attrs = derive(profile)

    async def _run():
        groups = await asyncio.gather(
            housing.match(attrs, rules),
            childcare.match(attrs, rules),
            employment.match(attrs, rules),
        )
        return [r for group in groups for r in group]

    return aggregate(asyncio.run(_run()))


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_golden(case: dict) -> None:
    response = run_match(Profile.model_validate(case["profile"]))
    expect = case["expect"]

    assert [r.program_id for r in response.qualified] == expect["qualified"]

    for bucket in ("needs_verification", "excluded"):
        if bucket in expect:
            assert [r.program_id for r in getattr(response, bucket)] == expect[bucket]

    for program_id, amount in expect.get("amounts", {}).items():
        result = next(r for r in response.qualified if r.program_id == program_id)
        assert result.amount == pytest.approx(amount)

    if "unresolved_includes" in expect:
        unresolved = {
            attr
            for r in response.needs_verification
            for attr in r.unresolved_attributes
        }
        assert set(expect["unresolved_includes"]) <= unresolved

    assert response.totals.monthly == pytest.approx(expect["totals"]["monthly"])
    assert response.totals.one_time == pytest.approx(expect["totals"]["one_time"])


def test_qualified_results_always_carry_an_amount() -> None:
    """A card that says 符合条件 with no number is a promise we can't keep."""
    for case in CASES:
        response = run_match(Profile.model_validate(case["profile"]))
        for result in response.qualified:
            assert result.amount is not None, f"{case['id']}: {result.program_id}"


def test_unknown_never_qualifies() -> None:
    """The safety property, asserted directly rather than per-fixture.

    An empty profile knows nothing. Nothing may come back qualified. Saying yes
    on no information is the one failure that costs a real person a wasted trip
    to a government office.
    """
    response = run_match(Profile())
    assert response.qualified == []
    assert response.totals.monthly == 0
    assert response.totals.one_time == 0


def test_monthly_and_one_time_are_never_summed() -> None:
    response = run_match(Profile.model_validate(CASES[0]["profile"]))
    assert isinstance(response.totals.monthly, float)
    assert isinstance(response.totals.one_time, float)
    # Two fields, not one. If anyone collapses these into a single `total`,
    # this test is the argument against it.
    assert not hasattr(response.totals, "combined")
