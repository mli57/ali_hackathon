"""Stage 3: Bailian writes the sentence, after Python has made the decision.

The call receives the program, the rule that matched, the household, and the
verdict and amount that were already computed. It is asked only to phrase and
cite. It cannot change the outcome because the outcome is an input.

Nothing here is allowed to block a result. Hard timeout, every exception
swallowed, `None` on any failure. If Bailian is slow or unreachable on stage,
every card still renders with its amount, its verdict and its claim steps -- it
loses one paragraph.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

import httpx

from backend.models import MatchResult

# Endpoint for a Bailian (DashScope) application. Verify against the app you
# created -- if you're calling the knowledge base a different way, only
# _call_bailian below needs to change.
BAILIAN_ENDPOINT = os.getenv(
    "BAILIAN_ENDPOINT",
    "https://dashscope.aliyuncs.com/api/v1/apps/{app_id}/completion",
)
TIMEOUT_SECONDS = float(os.getenv("BAILIAN_TIMEOUT", "2.0"))

PROMPT = """你是一名政策解读助手。以下资格判定结果已由系统确定，你不得更改。

程序：{name}
判定结果：{status_cn}
补贴金额：{amount_cn}
依据条件：{conditions}
申请人情况：{profile}

请用两句话向申请人说明为什么会得到这个结果，并注明政策依据来源。
要求：
- 不要重新计算或改动上述金额与判定结果
- 不要引入上述条件以外的任何资格要求
- 不要假设任何未提供的申请人信息
- 只使用知识库中的政策原文作为依据
"""

_STATUS_CN = {
    "qualified": "符合条件",
    "needs_verification": "需进一步核验",
    "excluded": "不符合条件",
}


def _is_configured() -> bool:
    return bool(os.getenv("BAILIAN_API_KEY") and os.getenv("BAILIAN_APP_ID"))


def _build_prompt(result: MatchResult, attrs: dict[str, Any]) -> str:
    if result.amount is None:
        amount_cn = "待定"
    elif result.cadence == "monthly":
        amount_cn = f"{result.amount:.0f} 元/月"
    else:
        amount_cn = f"{result.amount:.0f} 元（一次性）"

    conditions = "；".join(
        result.failed_conditions or result.review_clauses or ["符合全部资格条件"]
    )
    shown = {
        key: value
        for key, value in attrs.items()
        if key in {
            "hukou_type", "household_size", "per_capita_monthly_income",
            "owns_property", "district", "monthly_rent",
        }
    }
    return PROMPT.format(
        name=result.name,
        status_cn=_STATUS_CN.get(result.status, result.status),
        amount_cn=amount_cn,
        conditions=conditions,
        profile=shown,
    )


async def _call_bailian(client: httpx.AsyncClient, prompt: str) -> str | None:
    app_id = os.environ["BAILIAN_APP_ID"]
    response = await client.post(
        BAILIAN_ENDPOINT.format(app_id=app_id),
        headers={"Authorization": f"Bearer {os.environ['BAILIAN_API_KEY']}"},
        json={"input": {"prompt": prompt}, "parameters": {}, "debug": {}},
    )
    response.raise_for_status()
    text = response.json().get("output", {}).get("text")
    return text.strip() if isinstance(text, str) and text.strip() else None


async def explain_one(
    client: httpx.AsyncClient, result: MatchResult, attrs: dict[str, Any]
) -> str | None:
    try:
        return await _call_bailian(client, _build_prompt(result, attrs))
    except Exception:
        # Deliberately broad. Nothing that happens in here justifies failing a
        # request that already has its answer.
        return None


async def attach_explanations(
    results: list[MatchResult], attrs: dict[str, Any]
) -> list[MatchResult]:
    """Fill in `explanation` where possible. Always returns, always in order."""
    if not results or not _is_configured():
        return results

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            texts = await asyncio.wait_for(
                asyncio.gather(
                    *(explain_one(client, r, attrs) for r in results),
                    return_exceptions=True,
                ),
                timeout=TIMEOUT_SECONDS + 0.5,
            )
    except Exception:
        return results

    for result, text in zip(results, texts):
        if isinstance(text, str):
            result.explanation = text

    return results
