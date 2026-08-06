"""Boundary tests over tests/edge_cases.json.

Same deterministic path as test_golden.py, different intent. The golden fixtures
say what the policy means; these say where the current rule file draws each line
-- income ceiling, both asset limits, the two different household-size splits,
the district fallback. If an edit moves a boundary by one yuan, this notices.

Two cases carry a `surprise` note. Their expectations record behaviour that is
questionable, pinned so that changing it has to be deliberate. Read the note
before assuming a failure here is your fault.
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

CASES_PATH = Path(__file__).parent / "edge_cases.json"
CASES = json.loads(CASES_PATH.read_text(encoding="utf-8"))["profiles"]


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
def test_boundary(case: dict) -> None:
    response = run_match(Profile.model_validate(case["profile"]))
    expect = case["expect"]

    assert [r.program_id for r in response.qualified] == expect["qualified"]

    for bucket in ("needs_verification", "excluded"):
        if bucket in expect:
            assert [r.program_id for r in getattr(response, bucket)] == expect[bucket]

    for program_id, amount in expect.get("amounts", {}).items():
        result = next(r for r in response.qualified if r.program_id == program_id)
        assert result.amount == pytest.approx(amount)

    assert response.totals.monthly == pytest.approx(expect["totals"]["monthly"])
    assert response.totals.one_time == pytest.approx(expect["totals"]["one_time"])


def test_asset_bucket_is_not_the_benefit_bucket() -> None:
    """The one thing about this program people get wrong, asserted directly.

    ¥600,000 in assets: out with 3 people, in with 4. Both households sit in the
    same 3人及以上 benefit column, so the amount is identical -- the split that
    decides the asset limit is a different split from the one that decides the
    money.
    """
    by_id = {c["id"]: c for c in CASES}
    three = run_match(Profile.model_validate(by_id["assets_between_limits_size3_excluded"]["profile"]))
    four = run_match(Profile.model_validate(by_id["assets_between_limits_size4_qualifies"]["profile"]))

    # Scoped to this program on purpose. Both households also land in other
    # buckets for the other five programs, and none of that is what this test
    # is about -- asserting the whole excluded list here would make every future
    # program addition look like an asset-bucket regression.
    assert "bj_housing_market_rent_subsidy" in [r.program_id for r in three.excluded]
    assert [r.program_id for r in four.qualified] == ["bj_housing_market_rent_subsidy"]
    assert four.qualified[0].amount == pytest.approx(1200)
