"""FastAPI app. Two routes today, three once free-text intake lands (v0.4.0)."""

from __future__ import annotations

import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.aggregator import aggregate
from backend.derive import DERIVED_ATTRIBUTES, derive, inputs_for
from backend.explain import attach_explanations
from backend.matchers import childcare, employment, housing
from backend.models import ConfirmResponse, FollowUpQuestion, MatchResponse, Profile
from backend.rules import load_rules

app = FastAPI(title="Subsidy Discovery Agent", version="0.1.0")

# The frontend is served as static files from a different port.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, object]:
    rules = load_rules()
    return {
        "status": "ok",
        "programs": len(rules),
        "unverified": [r.program_id for r in rules if not r.verified],
    }


@app.post("/profile/confirm", response_model=ConfirmResponse)
async def confirm(profile: Profile) -> ConfirmResponse:
    """Echo the profile back and ask for whatever the live programs still need.

    Ask few upfront, then ask what's actually needed. A program is only worth
    asking about while it's still live -- if a household already fails a
    condition we checked, we don't make them answer three more questions for it.
    """
    rules = load_rules()
    attrs = derive(profile)

    wanted: dict[str, list[str]] = {}
    for rule in rules:
        for attr in rule.required_attributes:
            if attr in attrs:
                continue
            for question in inputs_for(attr):
                if question in DERIVED_ATTRIBUTES or question in attrs:
                    continue
                wanted.setdefault(question, []).append(rule.program_id)

    follow_ups = [
        FollowUpQuestion(attr=attr, asked_for=sorted(set(programs)))
        for attr, programs in sorted(wanted.items())
    ]
    return ConfirmResponse(profile=profile, derived=attrs, follow_ups=follow_ups)


@app.post("/profile/finalize", response_model=MatchResponse)
async def finalize(profile: Profile) -> MatchResponse:
    rules = load_rules()
    attrs = derive(profile)

    # Stage 2: deterministic. No model, no network.
    domain_results = await asyncio.gather(
        housing.match(attrs, rules),
        childcare.match(attrs, rules),
        employment.match(attrs, rules),
    )
    response = aggregate([r for group in domain_results for r in group])

    # Stage 3: Bailian writes the prose. Fail-soft -- if this returns nothing,
    # every number above is still on the card.
    shown = response.qualified + response.needs_verification + response.alternatives
    await attach_explanations(shown, attrs)

    return response
