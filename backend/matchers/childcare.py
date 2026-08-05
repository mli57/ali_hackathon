"""Childcare domain matcher. Programs land in v0.2.0; the wiring is here so the
runtime shape is identical across domains from day one."""

from __future__ import annotations

from typing import Any

from backend.matchers.base import match_domain
from backend.models import MatchResult, Rule

DOMAIN = "childcare"


async def match(profile_attrs: dict[str, Any], rules: list[Rule]) -> list[MatchResult]:
    return await match_domain(DOMAIN, rules, profile_attrs)
