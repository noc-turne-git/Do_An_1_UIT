"""Shared contracts from docs/Cáº¥u trÃºc schema.md; ambiguities: docs/Backend_ERD.md.

These models validate data shape, not the 14 business rules of the future Validator.
"""
from datetime import date
from uuid import UUID
from typing import Annotated, Generic, Literal, TypeVar

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictInt, StrictBool, field_validator, model_validator
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

Money = Annotated[StrictInt, Field(ge=0, le=9223372036854775807)]
Minutes = Annotated[StrictInt, Field(ge=0, le=2147483647)]
Confidence = Annotated[float, Field(ge=0, le=1)]
Clock = Annotated[str, Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")]
Step = Literal["request_parser", "destination_agent", "constraint_planner", "place_agent", "budget_module", "planning_input_builder", "planning_engine", "validator", "explainer"]
PriceStatus = Literal["ESTIMATED", "UNKNOWN", "VERIFIED_FREE"]
SolverStatus = Literal["feasible", "infeasible", "partial", "error"]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Contract(Model):
    schema_version: str = Field(default="1.0", pattern=r"^1\.\d+$")


class Destination(Model):
    selection_mode: Literal["explicit", "implicit", "ambiguous"] | None
    city: str | None
    province: str | None
    country: str | None
    candidate_cities: list[str]
    preferred_areas: list[str]
    must_visit: list[str]
    avoid_places: list[str]


class TripBoundary(Model):
    datetime: AwareDatetime | None
    location: str | None


class Trip(Model):
    start_date: date | None
    end_date: date | None
    duration_days: Annotated[StrictInt, Field(ge=1)] | None
    timezone: str | None
    arrival: TripBoundary
    departure: TripBoundary

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value):
        if value is not None:
            try:
                ZoneInfo(value)
            except (ZoneInfoNotFoundError, ValueError) as exc:
                raise ValueError("Unknown IANA timezone") from exc
        return value

    @model_validator(mode="after")
    def dates_in_order(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date must be >= start_date")
        if self.start_date and self.end_date and self.duration_days is not None:
            if self.duration_days != (self.end_date - self.start_date).days + 1:
                raise ValueError("duration_days must match inclusive date range")
        if self.arrival.datetime and self.departure.datetime and self.arrival.datetime > self.departure.datetime:
            raise ValueError("departure must not precede arrival")
        return self


class Travelers(Model):
    adults: Minutes | None
    children: Minutes | None
    children_ages: list[Minutes]


class Budget(Model):
    amount: Money | None
    currency: str
    scope: str | None
    includes: list[str]
    excludes: list[str]
    flexibility: str
    max_overrun_percent: Annotated[float, Field(ge=0)]
    preferences: dict[str, str] | None = None

    @model_validator(mode="after")
    def strict_budget(self):
        if self.flexibility == "strict" and self.max_overrun_percent != 0:
            raise ValueError("strict budget requires max_overrun_percent = 0")
        return self


class Preferences(Model):
    interests: list[str] | None
    pace: str | None
    transport_modes: list[str] | None


class DailyPreference(Model):
    day: Annotated[StrictInt, Field(ge=1)]
    activity_start: Clock | None
    activity_end: Clock | None
    return_by: Clock | None
    start_location: str | None
    end_location: str | None
    min_activities: Minutes | None
    target_activities: Minutes | None
    max_activities: Minutes | None
    rest_minutes: Minutes | None
    pace_override: str | None


class AdditionalConstraint(Model):
    description: str
    type: str
    is_hard: StrictBool


class RequestMeta(Model):
    raw_prompt: str
    field_sources: dict[str, Literal["user", "default", "inferred"]]
    field_confidences: dict[str, Confidence]

    @model_validator(mode="after")
    def inferred_confidences(self):
        for path, source in self.field_sources.items():
            if source == "inferred" and path not in self.field_confidences:
                raise ValueError(f"inferred field requires confidence: {path}")
        return self


class TripRequest(Contract):
    destination: Destination
    trip: Trip
    travelers: Travelers
    budget: Budget
    preferences: Preferences
    daily_preferences: list[DailyPreference]
    must_do: list[str]
    additional_constraints: list[AdditionalConstraint]
    meta: RequestMeta
    missing_fields: list[str]

    @model_validator(mode="after")
    def daily_days(self):
        days = [p.day for p in self.daily_preferences]
        if len(days) != len(set(days)):
            raise ValueError("daily_preferences days must be unique")
        duration = self.trip.duration_days
        if self.trip.start_date and self.trip.end_date:
            duration = (self.trip.end_date - self.trip.start_date).days + 1
        if duration is not None and any(day > duration for day in days):
            raise ValueError("daily_preferences day outside trip")
        # Derived data, never trust a stale parser-provided list.
        required = {
            "destination.selection_mode": self.destination.selection_mode,
            "trip.start_date": self.trip.start_date,
            "trip.end_date": self.trip.end_date,
            "travelers.adults": self.travelers.adults,
            "travelers.children": self.travelers.children,
            "preferences.interests": self.preferences.interests,
            "preferences.pace": self.preferences.pace,
            "preferences.transport_modes": self.preferences.transport_modes,
            "budget.amount": self.budget.amount,
            "budget.scope": self.budget.scope,
        }
        if self.destination.selection_mode == "explicit":
            required["destination.city"] = self.destination.city
        self.missing_fields = [path for path, value in required.items()
                               if value is None and self.meta.field_sources.get(path) != "user"]
        return self


class Region(Model):
    city: str
    province: str | None = None
    country: str | None = None


class CandidateRegion(Region):
    reason: str


class DestinationResult(Contract):
    request_type: Literal["EXPLICIT", "IMPLICIT", "AMBIGUOUS", "INSUFFICIENT"]
    selected_region: Region | None
    selection_status: Literal["selected", "needs_user_choice", "no_valid_candidate", "needs_more_info"]
    selection_reason: str
    candidate_regions: list[CandidateRegion]
    missing_fields: list[str]

    @model_validator(mode="after")
    def selection_consistent(self):
        if (self.selection_status == "selected") != (self.selected_region is not None):
            raise ValueError("selected status requires selected_region; other statuses must leave it null")
        if self.selection_status == "needs_user_choice" and len(self.candidate_regions) < 2:
            raise ValueError("needs_user_choice requires at least two candidates")
        if self.selection_status == "no_valid_candidate" and self.candidate_regions:
            raise ValueError("no_valid_candidate cannot contain candidates")
        return self


T = TypeVar("T")


class Constraint(Model, Generic[T]):
    value: T
    is_hard: StrictBool


class ActivityWindow(Model):
    start: Constraint[Clock]
    end: Constraint[Clock]

    @model_validator(mode="after")
    def ordered(self):
        if self.start.value > self.end.value:
            raise ValueError("activity window start must be <= end")
        return self


class ActivityCount(Model):
    min: Constraint[Minutes]
    target: Constraint[Minutes]
    max: Constraint[Minutes]

    @model_validator(mode="after")
    def soft_target(self):
        if self.target.is_hard:
            raise ValueError("target is always soft")
        if not self.min.value <= self.target.value <= self.max.value:
            raise ValueError("activity count must satisfy min <= target <= max")
        return self


class MealWindow(Model):
    type: str
    start: Clock
    end: Clock
    duration_minutes: Minutes
    required: StrictBool

    @model_validator(mode="after")
    def ordered(self):
        if self.start > self.end or self.duration_minutes > clock_minutes(self.end) - clock_minutes(self.start):
            raise ValueError("meal duration must fit ordered meal window")
        return self


class TimeDay(Model):
    day: Annotated[StrictInt, Field(ge=1)]
    date: date
    activity_window: ActivityWindow
    target_activity_count: ActivityCount
    pace: Constraint[str]
    transport_mode: Constraint[list[str]]
    meal_windows: list[MealWindow]
    rest_minutes: Constraint[Minutes]
    preferences: list[Constraint[str]]
    start_location_id: str | None = None
    end_location_id: str | None = None


class TimeConstraints(Contract):
    days: list[TimeDay]

    @model_validator(mode="after")
    def consecutive(self):
        from datetime import timedelta
        if not self.days:
            raise ValueError("at least one day required")
        for index, day in enumerate(self.days):
            if day.day != index + 1 or day.date != self.days[0].date + timedelta(days=index):
                raise ValueError("days and dates must be consecutive starting at day 1")
        return self


class Location(Model):
    latitude: Annotated[float, Field(ge=-90, le=90)]
    longitude: Annotated[float, Field(ge=-180, le=180)]
    address: str | None


class WeeklyHours(Model):
    weekday: Annotated[StrictInt, Field(ge=1, le=7)]
    open: Clock | None
    close: Clock | None
    is_closed: StrictBool


class SpecialHours(Model):
    date: date
    open: Clock | None
    close: Clock | None
    is_closed: StrictBool
    note: str | None = None


class OpeningHours(Model):
    timezone: str
    weekly_schedule: list[WeeklyHours]
    special_hours: list[SpecialHours]

    _valid_timezone = field_validator("timezone")(Trip.valid_timezone.__func__)


class Photo(Model):
    photo_reference: str
    url: str | None
    width: Minutes
    height: Minutes
    attributions: list[str]


class VisitDuration(Model):
    min_minutes: Minutes
    typical_minutes: Minutes
    max_minutes: Minutes
    source: str
    source_url: str | None = None
    crawled_at: date | None = None
    confidence: Confidence | None = None
    reason: str | None = None

    @model_validator(mode="after")
    def ordered(self):
        if not self.min_minutes <= self.typical_minutes <= self.max_minutes:
            raise ValueError("visit duration must satisfy min <= typical <= max")
        if self.source == "estimated" and self.confidence is None:
            raise ValueError("estimated duration requires confidence")
        return self


class Suitability(Model):
    score_places: Annotated[StrictInt, Field(ge=0, le=100)]
    matched_interests: list[str]
    reason: str


class PlaceConstraints(Model):
    reservation_required: StrictBool
    accessibility_notes: list[str]


class DataQuality(Model):
    source: str
    opening_hours_verified: StrictBool
    last_verified_at: AwareDatetime | None


class PlaceSource(Model):
    type: Literal["user_requested", "agent_suggested"]
    original_name: str | None = None


class PlaceCandidate(Contract):
    place_id: str
    google_place_id: str | None
    name: str
    category: str
    types: list[str]
    google_maps_url: str | None
    rating: Annotated[float, Field(ge=0, le=5)] | None
    user_rating_count: Minutes | None
    business_status: str | None
    photos: list[Photo]
    location: Location
    opening_hours: OpeningHours
    visit_duration: VisitDuration
    suitability: Suitability
    constraints: PlaceConstraints
    cluster_id: int | None
    data_quality: DataQuality
    source: PlaceSource


class PlaceCandidates(Contract):
    """Storage envelope only; PlaceAgent still returns list[PlaceCandidate]."""
    places: list[PlaceCandidate]


class CostRange(Model):
    min: Money
    max: Money

    @model_validator(mode="after")
    def ordered(self):
        if self.min > self.max:
            raise ValueError("min must be <= max")
        return self


class CurrencyCostRange(CostRange):
    currency: str


class CostedPlaceCandidate(Contract):
    place_id: str
    google_place_id: str | None
    name: str
    category: str
    types: list[str]
    address: str | None
    score_places: Annotated[StrictInt, Field(ge=0, le=100)]
    price_status: PriceStatus
    price_confidence_score: Confidence | None
    estimated_total_cost: CurrencyCostRange | None
    # Original admission-price text, preserved without parsing.
    admission_price_raw: str | None = None
    score_budget: float | None = None

    @model_validator(mode="after")
    def price_integrity(self):
        validate_price(self.price_status, self.estimated_total_cost, self.price_confidence_score)
        return self


class BudgetResult(Contract):
    """Named envelope of section 6; interfaces also retain Agent B's full output."""
    places: list[CostedPlaceCandidate]
    missing_costs: list[str]
    budget_reason: str


class PlanningPlace(Model):
    place_id: str
    types: list[str]
    score_places: Annotated[StrictInt, Field(ge=0, le=100)]
    visit_duration_typical: Minutes
    estimated_total_cost: CurrencyCostRange
    price_status: PriceStatus
    price_confidence_score: Confidence | None
    latitude: Annotated[float, Field(ge=-90, le=90)]
    longitude: Annotated[float, Field(ge=-180, le=180)]
    cluster_id: int | None
    opening_hours: OpeningHours

    @model_validator(mode="after")
    def price_integrity(self):
        if self.price_status == "UNKNOWN":
            raise ValueError("UNKNOWN prices cannot enter PlanningInput")
        validate_price(self.price_status, self.estimated_total_cost, self.price_confidence_score)
        return self


class TravelMatrix(Model):
    locations: list[str]
    mode: str
    unit: Literal["minutes", "m"]
    values: list[list[Minutes]]

    @model_validator(mode="after")
    def square(self):
        n = len(self.locations)
        if len(set(self.locations)) != n or len(self.values) != n or any(len(row) != n for row in self.values):
            raise ValueError("Matrix must be square with unique locations")
        return self


class Weights(Model):
    alpha: float
    beta: float
    gamma: float
    delta: float
    normalized: StrictBool


class Optimization(Model):
    objective: Literal["maximize_total_utility"]
    allow_optional_places_to_be_skipped: StrictBool
    cost_basis_hard_limit: Literal["max"]
    cost_basis_objective: Literal["midpoint"]


class SolverConfig(Model):
    time_limit_seconds: Annotated[StrictInt, Field(gt=0)]
    random_seed: int
    max_retries: Minutes


class PlanningInput(Contract):
    trip_id: UUID
    budget: Budget
    candidate_places: list[PlanningPlace]
    must_visit_place_ids: list[str]
    avoid_place_ids: list[str]
    time_constraints: TimeConstraints
    travel_time_matrix: TravelMatrix
    travel_distance_matrix: TravelMatrix
    weights: Weights
    optimization: Optimization
    solver_config: SolverConfig

    @model_validator(mode="after")
    def consistent(self):
        times, distances = self.travel_time_matrix, self.travel_distance_matrix
        if times.unit != "minutes" or distances.unit != "m":
            raise ValueError("matrix units must be minutes and m respectively")
        if times.locations != distances.locations or times.mode != distances.mode:
            raise ValueError("matrix locations/order and modes must agree")
        ids = [place.place_id for place in self.candidate_places]
        if len(set(ids)) != len(ids) or not set(ids) <= set(times.locations):
            raise ValueError("candidate IDs must be unique and present in matrices")
        if not set(self.must_visit_place_ids) <= set(ids):
            raise ValueError("must visit IDs must be candidates")
        if set(self.must_visit_place_ids) & set(self.avoid_place_ids):
            raise ValueError("must visit and avoid IDs conflict")
        for day in self.time_constraints.days:
            if day.start_location_id not in times.locations or day.end_location_id not in times.locations:
                raise ValueError("day endpoints must be resolved and present in matrices")
        return self


class Activity(Model):
    place_id: str
    types: list[str]
    arrival_time: Clock
    start_time: Clock
    departure_time: Clock
    travel_minutes_from_previous: Minutes | None
    estimated_total_cost: CostRange | None
    price_status: PriceStatus

    @model_validator(mode="after")
    def time_order(self):
        if not self.arrival_time <= self.start_time <= self.departure_time:
            raise ValueError("activity must satisfy arrival <= start <= departure within one day")
        return self


    @model_validator(mode="after")
    def cost_status(self):
        validate_cost_status(self.price_status, self.estimated_total_cost)
        return self


class ItineraryDay(Model):
    day: int
    date: date
    activities: list[Activity]
    day_total_cost: CostRange | None
    price_status: PriceStatus


    @model_validator(mode="after")
    def cost_status(self):
        validate_cost_status(self.price_status, self.day_total_cost)
        return self


class Summary(Model):
    total_scheduled_places: Minutes
    total_cost: CostRange | None
    price_status: PriceStatus
    total_travel_minutes: Minutes
    objective_value: float | None
    summary_message: str


    @model_validator(mode="after")
    def cost_status(self):
        validate_cost_status(self.price_status, self.total_cost)
        return self


class DroppedPlace(Model):
    place_id: str
    reason: str


class Diagnostics(Model):
    solver_status: SolverStatus
    optimality_proven: StrictBool
    unsatisfied_constraints: list[str]
    warnings: list[str]


class Itinerary(Contract):
    trip_id: UUID
    status: SolverStatus
    currency: str
    days: list[ItineraryDay]
    summary: Summary
    dropped_places: list[DroppedPlace]
    relaxation_suggestions: list["RelaxationProposal"]
    diagnostics: Diagnostics


    @model_validator(mode="after")
    def solver_status_consistent(self):
        if self.status != self.diagnostics.solver_status:
            raise ValueError("status and solver_status differ")
        return self


class RelaxationProposal(Model):
    constraint_type: str
    description: str
    payload: dict[str, object]


class Finding(Model):
    type: str
    rule: str
    severity: Literal["hard", "soft", "info"]
    message: str
    day: int | None = None
    place_id: str | None = None
    actual: int | str | None = None
    expected: int | str | None = None
    target: int | None = None
    limit: int | None = None
    deadline: Clock | None = None
    cost_basis: str | None = None


class Recomputed(Model):
    cost_in_scope: CostRange
    budget_limit: Money | None
    total_travel_minutes: Minutes
    total_scheduled_places: Minutes


class ValidationResult(Contract):
    trip_id: UUID
    is_valid: StrictBool
    violations: list[Finding]
    warnings: list[Finding]
    checked_rules: list[str]
    recomputed: Recomputed
    suggested_action: Literal["accept", "replan", "ask_user", "fail"]

    @model_validator(mode="after")
    def findings_consistent(self):
        if any(f.severity != "hard" for f in self.violations):
            raise ValueError("violations must be hard")
        if any(f.severity == "hard" for f in self.warnings):
            raise ValueError("warnings must be soft or info")
        required = {"input_integrity", "price_integrity", "travel_time", "overlap", "opening_hours",
                    "visit_duration", "day_start_window", "day_end_window", "meal_window", "activity_count",
                    "rest_time", "must_visit", "budget", "summary_consistency"}
        if self.is_valid and (self.violations or not required <= set(self.checked_rules)):
            raise ValueError("is_valid requires no violations and all 14 rules in section 8.4")
        if self.suggested_action == "accept" and not self.is_valid:
            raise ValueError("accept requires is_valid")
        return self


class PendingQuestion(Model):
    question: str
    fields: list[str]


class AnswerHistory(Model):
    round: int
    asked_fields: list[str]
    question: str
    answer_raw: str
    resolved_fields: list[str]
    declared_unknown_fields: list[str]


class Attempt(Model):
    attempt: int
    step: Step
    random_seed: int
    time_limit_seconds: Annotated[StrictInt, Field(gt=0)]
    result: Literal["accepted", "hard_violation", "infeasible", "error"]
    violations: list[str]
    itinerary_id: UUID | None
    validation_result_id: UUID | None


class WorkflowError(Model):
    step: Step
    code: Literal["llm_output_invalid", "external_api_error", "planning_input_inconsistent", "solver_error", "validator_internal_error"]
    message: str
    retryable: StrictBool


class ArtifactReferences(Model):
    trip_request_id: UUID | None = None
    destination_result_id: UUID | None = None
    time_constraints_id: UUID | None = None
    candidates_id: UUID | None = None
    costed_candidates_id: UUID | None = None
    planning_input_id: UUID | None = None
    itinerary_id: UUID | None = None
    validation_result_id: UUID | None = None


class WorkflowState(Contract):
    """Small runtime references/counters; histories and payloads are persisted separately."""
    request_id: UUID
    trip_id: UUID
    status: Literal["parsing", "clarifying", "planning", "validating", "awaiting_relaxation", "completed", "failed"]
    current_step: Step
    completed_steps: list[Step]
    artifacts: ArtifactReferences
    clarification_round: Minutes
    max_clarification_rounds: Minutes = 3
    destination_round: Minutes = 0
    pending_fields: list[str]
    retry_count: Minutes

    @model_validator(mode="after")
    def clarification_consistent(self):
        if self.clarification_round > self.max_clarification_rounds:
            raise ValueError("clarification limit exceeded")
        return self


def clock_minutes(value: str) -> int:
    hours, minutes = map(int, value.split(":"))
    return hours * 60 + minutes


def validate_price(status, cost, confidence):
    if status == "UNKNOWN":
        if cost is not None:
            raise ValueError("UNKNOWN price must remain null")
    elif cost is None:
        raise ValueError("known price requires cost range")
    elif status == "VERIFIED_FREE":
        if cost.min != 0 or cost.max != 0:
            raise ValueError("VERIFIED_FREE requires zero cost")
    elif cost.min <= 0:
        raise ValueError("zero cost requires VERIFIED_FREE")
    if status == "ESTIMATED" and confidence is None:
        raise ValueError("ESTIMATED price requires confidence")


def validate_cost_status(status, cost):
    if status == "UNKNOWN":
        if cost is not None:
            raise ValueError("UNKNOWN cost must be null")
    elif cost is None:
        raise ValueError("known cost requires range")
    elif status == "VERIFIED_FREE":
        if cost.min != 0 or cost.max != 0:
            raise ValueError("VERIFIED_FREE requires zero cost")
    elif cost.min <= 0:
        raise ValueError("ESTIMATED cost must be positive")
