"""Schemas: SOP files, LLM outputs, API payloads and graph state."""
from typing import Literal, TypedDict

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.weather import SNAPSHOT_FIELDS

Severity = Literal["low", "medium", "high"]
SEVERITY_RANK = {"high": 3, "medium": 2, "low": 1}
TimeWindow = Literal["now", "morning", "afternoon", "evening", "night", "tomorrow"]


class Condition(BaseModel):
    """Numeric test on one weather field. All operators given must hold."""
    model_config = ConfigDict(extra="forbid")

    gt: float | None = None
    gte: float | None = None
    lt: float | None = None
    lte: float | None = None

    @model_validator(mode="after")
    def at_least_one(self):
        if all(v is None for v in (self.gt, self.gte, self.lt, self.lte)):
            raise ValueError("a condition needs at least one of gt/gte/lt/lte")
        return self

    def holds(self, value) -> bool:
        if value is None:  # missing data never triggers or clears a rule
            return False
        return ((self.gt is None or value > self.gt)
                and (self.gte is None or value >= self.gte)
                and (self.lt is None or value < self.lt)
                and (self.lte is None or value <= self.lte))


class SOP(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^SOP-[A-Z]+-\d+$")
    category: str
    severity: Severity
    situational: bool = False
    applies_when: str
    conditions: dict[str, Condition] = {}
    advice: str
    cite_as: str

    @field_validator("conditions")
    @classmethod
    def known_fields(cls, v):
        unknown = sorted(set(v) - set(SNAPSHOT_FIELDS))
        if unknown:
            raise ValueError(f"unknown weather field(s) {unknown}; available: {SNAPSHOT_FIELDS}")
        return v

    @property
    def advice_text(self) -> str:
        """The advice on a single line (the YAML block is wrapped over several)."""
        return " ".join(self.advice.split())

    def conditions_hold(self, values: dict) -> bool:
        return all(cond.holds(values.get(field)) for field, cond in self.conditions.items())


class Intent(BaseModel):
    on_topic: bool = Field(description=(
        "True if the user asks whether weather makes an outdoor activity, trip, outing or "
        "taking someone/a pet outside safe or advisable, or follows up on such a question. "
        "False for anything else."))
    location: str | None = Field(None, description=(
        "Bare city or town name from THIS message (no landmark, area, state or country), else null."))
    activity: str | None = Field(None, description="The outdoor activity in THIS message, e.g. 'cycling to work', else null.")
    audience: str | None = Field(None, description="Who it is for if not the user (e.g. 'child', 'elderly parent', 'dog'), else null.")
    time_window: TimeWindow | None = Field(None, description=(
        "When, if stated in THIS message: now, morning (6-11), afternoon (12-16, includes noon), "
        "evening (17-20), night (21-23), tomorrow. 'today' with no time of day means now. Null if not stated."))


class MatchResult(BaseModel):
    sop_ids: list[str] = Field(description="IDs from the candidate list whose 'applies when' covers the question. Empty if none.")


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=1000)


class ChatResponse(BaseModel):
    reply: str
    path: str
    sop_ids: list[str]
    location: str | None = None
    weather: dict | None = None


class GraphState(TypedDict, total=False):
    message: str
    history: list[dict]   # [{"role": "user"|"assistant", "content": str}]
    facts: dict           # established in earlier turns of this session
    intent: dict
    location: dict
    weather: dict         # {"values": {...}, "label": str}
    sop_ids: list[str]    # ranked by the conflict rule
    situational: bool
    lead: str             # fixed paragraph written by the override node
    error: str | None     # failure kind
    reply: str
    path: str
