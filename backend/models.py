"""Typed Profile, Rule, and result models.

Everything the runtime touches is a Pydantic model. Bad input fails at the
boundary instead of quietly corrupting a match.

Note that almost every Profile field is optional. That is deliberate: the intake
form asks a small gating set, and /profile/confirm works out which follow-up
questions the still-live programs actually need. A missing attribute is not an
error, it is a question we haven't asked yet.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

HukouType = Literal["bj_urban", "bj_rural", "non_bj"]
#: 民政部门认定状态. dibao 最低生活保障, tekun 分散供养特困人员,
#: low_income 城市低收入家庭, none 以上均否.
WelfareStatus = Literal["dibao", "tekun", "low_income", "none"]
#: 就业状态. Was a free-form str until the employment programs landed. Two rules
#: now compare against it with `in`, and a rule that tests a free string is a
#: rule that silently never matches -- "灵活就业" and "flexible" are both things
#: a person could type and only one of them would have worked.
#: self_employed_founder is 创业组织的法定代表人或主要负责人, which 一次性创业
#: 补贴 needs and which "employed" does not imply.
EmploymentStatus = Literal[
    "employed",
    "flexible",
    "self_employed_founder",
    "unemployed",
    "student",
    "retired",
    "other",
]
#: How often the money arrives. `annual` was added 2026-08-07 for 育儿补贴,
#: which pays every year until the child turns 3 -- it had been squeezed into
#: one_time and rendered as 「一次性」, which told people a recurring benefit
#: was a single payment. one_time still means genuinely once (一次性创业补贴).
Cadence = Literal["monthly", "one_time", "annual"]
Confidence = Literal["high", "medium", "low"]
Status = Literal["qualified", "needs_verification", "excluded"]

Operator = Literal[
    "==", "!=", "<", "<=", ">", ">=", "in", "not_in", "manual_review"
]


# --------------------------------------------------------------------------
# Profile
# --------------------------------------------------------------------------


class Profile(BaseModel):
    """What we know about a household. Grows across the confirm/finalize round trips."""

    # Gating questions.
    hukou_type: HukouType | None = None
    household_size: int | None = Field(default=None, ge=1, le=20)
    household_monthly_income: float | None = Field(default=None, ge=0)

    # Follow-ups, asked only when a still-live program needs them.
    household_assets: float | None = Field(default=None, ge=0)
    owns_property: bool | None = None
    district: str | None = None
    monthly_rent: float | None = Field(default=None, ge=0)

    # 民政 status. Worth a whole question: it decides 第一档/第二档 versus an
    # income band, which for a 3-person household is ¥3,500 against ¥1,200.
    welfare_status: WelfareStatus | None = None

    # Other domains.
    employment_status: EmploymentStatus | None = None
    children_ages: list[int] | None = None


# --------------------------------------------------------------------------
# Rule pieces
# --------------------------------------------------------------------------


class Band(BaseModel):
    """One row of a range lookup. `min` inclusive, `max` inclusive, either may be null."""

    value: Any
    min: float | None = None
    max: float | None = None


class Override(BaseModel):
    """A categorical answer that pre-empts the range lookup.

    市场租房补贴's 第一档 and 第二档 are not income bands at all -- they are
    民政 statuses (低保家庭 / 特困人员 / 城市低收入家庭). Only 第三档 through
    第六档 are income ranges. Without this, a 低收入家庭 falls through to the
    band matching their raw income and is offered ¥1,200 instead of ¥3,000.
    """

    attr: str
    equals: Any
    value: Any


class KeyDefinition(BaseModel):
    """How to compute a program-specific lookup key from a profile.

    These live in the rule, not in derive.py, because they are program-specific.
    One program's 第六档 is not another's, and the district groupings differ.

    They are also not one-per-program: 市场租房补贴 buckets household size at
    ≤2/≥3 for the benefit amount and at ≤3/≥4 for the asset limit, in the same
    document. Keys are named individually for exactly that reason.

    `bands` are matched in order, first match wins, so adjacent bands can share
    a boundary (第三档 max 2700, 第四档 min 2700) and still mean 2700 元 ->
    第三档, as the policy intends.
    """

    kind: Literal["range_lookup", "set_lookup"]
    attr: str
    overrides: list[Override] = Field(default_factory=list)
    bands: list[Band] = Field(default_factory=list)
    groups: dict[str, list[str]] = Field(default_factory=dict)
    default: Any = None


class Table(BaseModel):
    """A multi-dimensional lookup. Each row carries its key values plus `value`."""

    kind: Literal["table"] = "table"
    keys: list[str]
    rows: list[dict[str, Any]]


class Fixed(BaseModel):
    kind: Literal["fixed"] = "fixed"
    value: float


AmountSpec = Annotated[Table | Fixed, Field(discriminator="kind")]


class Predicate(BaseModel):
    """One eligibility condition.

    `value` may be a scalar, a list (for in / not_in), or a Table when the
    threshold itself varies -- the asset limit on 市场租房补贴 depends on
    household size, so the cutoff is a table, not a number.

    op == "manual_review" means the source text was too vague to encode. The
    program is routed to needs_verification and `clause` is shown to the user
    verbatim. We surface the policy's own wording rather than a model's
    paraphrase of it.
    """

    attr: str | None = None
    op: Operator
    value: Any = None
    clause: str | None = None
    note: str | None = None


class Eligibility(BaseModel):
    all_of: list[Predicate] = Field(default_factory=list)


class Cap(BaseModel):
    """Ceiling applied after the amount is computed, e.g. subsidy <= actual rent."""

    kind: Literal["not_to_exceed"]
    profile_field: str


class Duration(BaseModel):
    kind: Literal["ongoing_conditional", "fixed_months", "one_time"]
    months: int | None = None
    review: str | None = None


class Benefit(BaseModel):
    cadence: Cadence
    amount: AmountSpec
    caps: list[Cap] = Field(default_factory=list)
    duration: Duration


class Rule(BaseModel):
    program_id: str
    name: str
    domain: Literal["housing", "childcare", "employment"]
    agency: str

    # From data/manifest.json, recorded by a human at upload. Never model output.
    document_refs: list[str] = Field(default_factory=list)
    source_url: str | None = None

    required_attributes: list[str] = Field(default_factory=list)
    key_definitions: dict[str, KeyDefinition] = Field(default_factory=dict)
    eligibility: Eligibility = Field(default_factory=Eligibility)
    benefit: Benefit

    exclusivity_group: str | None = None
    claim_steps: list[str] = Field(default_factory=list)
    required_documents: list[str] = Field(default_factory=list)

    #: Shown alongside the amount. For conditions that can only raise the
    #: payment (市场租房补贴's 提档 rules for 特殊困难家庭 and 核心区迁出),
    #: telling the user "you may be entitled to more" is better than either
    #: asking six more questions or quietly understating. Never use this for
    #: anything that could *lower* the figure -- that has to be asked.
    benefit_caveats: list[str] = Field(default_factory=list)

    confidence: Confidence = "low"
    notes: str = ""

    # False until a human has checked the extracted figures against the source
    # PDF. Unverified rules are usable in development and refused by
    # `build_rules.py --strict`.
    verified: bool = False


# --------------------------------------------------------------------------
# Results
# --------------------------------------------------------------------------


class MatchResult(BaseModel):
    program_id: str
    name: str
    domain: str
    agency: str = ""
    status: Status

    amount: float | None = None
    cadence: Cadence | None = None
    duration: Duration | None = None

    # Why the status is what it is.
    unresolved_attributes: list[str] = Field(default_factory=list)
    failed_conditions: list[str] = Field(default_factory=list)
    review_clauses: list[str] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)

    confidence: Confidence = "low"
    verified: bool = False
    source_url: str | None = None
    document_refs: list[str] = Field(default_factory=list)
    claim_steps: list[str] = Field(default_factory=list)
    required_documents: list[str] = Field(default_factory=list)
    exclusivity_group: str | None = None

    # Filled by Stage 3. Always optional -- if Bailian times out the card still
    # renders with every number intact.
    explanation: str | None = None

    # Set by the aggregator when a higher-value program in the same
    # exclusivity group won the slot.
    superseded_by: str | None = None


class Totals(BaseModel):
    """Each cadence is totalled separately. They are never added together --
    ¥1,200/月, ¥3,600/年 and ¥8,000 once are three different kinds of thing and
    a single combined figure would not mean anything."""

    monthly: float = 0.0
    one_time: float = 0.0
    annual: float = 0.0


class MatchResponse(BaseModel):
    totals: Totals
    qualified: list[MatchResult] = Field(default_factory=list)
    needs_verification: list[MatchResult] = Field(default_factory=list)
    alternatives: list[MatchResult] = Field(default_factory=list)
    excluded: list[MatchResult] = Field(default_factory=list)


class FollowUpQuestion(BaseModel):
    attr: str
    asked_for: list[str] = Field(default_factory=list)


class ConfirmResponse(BaseModel):
    profile: Profile
    derived: dict[str, Any] = Field(default_factory=dict)
    follow_ups: list[FollowUpQuestion] = Field(default_factory=list)
