"""Turn per-program results into what the results page shows.

Three jobs: resolve exclusivity conflicts, total the selected programs, rank.
"""

from __future__ import annotations

from collections import defaultdict

from backend.models import MatchResponse, MatchResult, Totals

_CONFIDENCE_RANK = {"high": 0, "medium": 1, "low": 2}


def _sort_key(result: MatchResult) -> tuple[int, float]:
    """Confidence first, then amount.

    A high-confidence ¥800 program outranks a low-confidence ¥1,200 one. We are
    more use to someone as a reliable answer than an optimistic one.
    """
    return (_CONFIDENCE_RANK.get(result.confidence, 3), -(result.amount or 0.0))


def _resolve_exclusivity(
    qualified: list[MatchResult],
) -> tuple[list[MatchResult], list[MatchResult]]:
    """Within each exclusivity group keep the highest-value program.

    The loser is never dropped -- it moves to `alternatives` and says what beat
    it. The user may have a reason to prefer it, and hiding the choice would be
    making the decision for them.

    Comparison is within a cadence: ¥/month against ¥/month. A monthly and a
    one-time program in the same group can't be ranked by size and are both
    kept, because picking between them isn't arithmetic.
    """
    groups: dict[str | None, list[MatchResult]] = defaultdict(list)
    for result in qualified:
        groups[result.exclusivity_group].append(result)

    selected: list[MatchResult] = []
    alternatives: list[MatchResult] = []

    for group, members in groups.items():
        if group is None or len(members) == 1:
            selected.extend(members)
            continue

        by_cadence: dict[str | None, list[MatchResult]] = defaultdict(list)
        for member in members:
            by_cadence[member.cadence].append(member)

        for cadence_members in by_cadence.values():
            ranked = sorted(cadence_members, key=lambda r: -(r.amount or 0.0))
            winner, losers = ranked[0], ranked[1:]
            selected.append(winner)
            for loser in losers:
                loser.superseded_by = winner.program_id
                alternatives.append(loser)

    return selected, alternatives


def aggregate(results: list[MatchResult]) -> MatchResponse:
    qualified = [r for r in results if r.status == "qualified"]
    needs_verification = [r for r in results if r.status == "needs_verification"]
    excluded = [r for r in results if r.status == "excluded"]

    selected, alternatives = _resolve_exclusivity(qualified)

    totals = Totals()
    for result in selected:
        if result.amount is None:
            continue
        if result.cadence == "monthly":
            totals.monthly += result.amount
        elif result.cadence == "one_time":
            totals.one_time += result.amount
        elif result.cadence == "annual":
            totals.annual += result.amount

    # Monthly and one-time are reported separately and never summed. ¥1,200/月
    # and ¥10,000 一次性 are different kinds of thing and a single combined
    # figure would not mean anything.
    totals.monthly = round(totals.monthly, 2)
    totals.one_time = round(totals.one_time, 2)
    totals.annual = round(totals.annual, 2)

    return MatchResponse(
        totals=totals,
        qualified=sorted(selected, key=_sort_key),
        needs_verification=sorted(needs_verification, key=_sort_key),
        alternatives=sorted(alternatives, key=_sort_key),
        excluded=sorted(excluded, key=_sort_key),
    )
