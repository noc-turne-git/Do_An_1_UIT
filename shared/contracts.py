"""Shared contracts from docs/Cáº¥u trÃºc schema.md; ambiguities: docs/Backend_ERD.md.

These models validate data shape, not the 14 business rules of the future Validator.
"""
from datetime import date
from uuid import UUID
from typing import Annotated, Generic, Literal, TypeVar

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictInt, StrictBool, field_validator, model_validator, model_serializer
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


SelectionIntent = Literal["EXPLICIT", "USER_UNKNOWN", "ANY_DESTINATION",
                          "DELEGATE_SELECTION", "UNSPECIFIED"]
SelectionAuthority = Literal["USER", "AGENT", "SYSTEM"] | None
DestinationSource = Literal["user", "AGENT_DELEGATED", "SYSTEM_DEFAULT"] | None
QuestionKind = Literal["trip_request", "destination_info", "destination_choice"]
PositiveInt = Annotated[StrictInt, Field(gt=0)]
NonEmpty = Annotated[str, Field(min_length=1, pattern=r"\S")]
TRIP_NEVER_DEFAULT = frozenset({'trip.start_date', 'trip.end_date', 'travelers.adults'})
# A field may deliberately remain null when the user has explicitly declined to
# constrain it.  Such a decision closes collection for this field; it is not
# the same as UNKNOWN, which means we still need an answer or a delegation.
FIELD_DECISIONS_THAT_CLOSE_COLLECTION = frozenset({
    'FLEXIBLE', 'AI_DECIDE', 'NO_PREFERENCE', 'DEFERRED',
})


class SelectionProvenance(Model):
    """Audit evidence for a user's stated intent or answer.

    This deliberately is not the source of a resolved destination.  That is
    represented by ``destination_source`` on ``SelectionPolicy``.
    """
    source: Literal["user"]
    evidence: NonEmpty
    episode_id: UUID | None = None
    question_id: UUID | None = None

    @model_validator(mode="after")
    def linked(self):
        if self.question_id is not None and self.episode_id is None:
            raise ValueError("question provenance requires episode_id")
        return self


class SelectionPolicy(Model):
    selection_intent: SelectionIntent = "UNSPECIFIED"
    selection_authority: SelectionAuthority = None
    destination_source: DestinationSource = None
    selection_provenance: SelectionProvenance | None = None

    @model_validator(mode="after")
    def authority_is_explicit(self):
        intent, authority, source = (self.selection_intent, self.selection_authority,
                                     self.destination_source)
        if intent == 'EXPLICIT':
            if authority != 'USER' or source != 'user':
                raise ValueError('explicit destination requires USER authority and user source')
        elif intent == 'USER_UNKNOWN':
            if authority != 'USER' or source not in {None, 'user'}:
                raise ValueError('USER_UNKNOWN retains USER authority without a system source')
        elif intent == 'ANY_DESTINATION':
            if (authority, source) not in {('USER', None), ('USER', 'user'),
                                           ('SYSTEM', 'SYSTEM_DEFAULT')}:
                raise ValueError('ANY_DESTINATION requires USER choice or SYSTEM_DEFAULT')
        elif intent == 'DELEGATE_SELECTION':
            if authority != 'AGENT' or source not in {None, 'AGENT_DELEGATED'}:
                raise ValueError('delegated selection requires AGENT authority')
        elif authority is not None or source is not None:
            raise ValueError('UNSPECIFIED must not assign decision authority or source')
        return self


class Destination(SelectionPolicy):
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
    field_decisions: dict[str, Literal["UNKNOWN", "FLEXIBLE", "AI_DECIDE", "NO_PREFERENCE", "DEFERRED", "SPECIFIED"]] = Field(default_factory=dict)
    parser_status: Literal["clarifying", "ready", "error"] | None = None

    @model_serializer(mode='wrap')
    def compatible_payload(self, handler):
        payload = handler(self)
        # Preserve historical workflow artifacts byte-for-byte when chat metadata is absent.
        if not self.field_decisions:
            payload.pop('field_decisions', None)
        if self.parser_status is None:
            payload.pop('parser_status', None)
        return payload

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
        elif self.destination.selection_intent == 'USER_UNKNOWN':
            required['destination.city'] = self.destination.city
        def unresolved(path, value):
            if value is None or (isinstance(value, str) and not value.strip()):
                return True
            # Empty collections are valid explicit preferences (for example,
            # "không có sở thích").  They are unresolved only when the parser
            # recorded UNKNOWN rather than an affirmative user decision.
            return (self.meta.field_decisions.get(path) == 'UNKNOWN'
                    and isinstance(value, (list, dict)) and not value)
        self.missing_fields = [path for path, value in required.items()
            if unresolved(path, value) and (
                # Destination has its own policy state machine.  An explicit
                # city and USER_UNKNOWN require an answer; ANY_DESTINATION
                # and DELEGATE_SELECTION are resolved by the destination flow.
                path.startswith('destination.') or
                # Elsewhere, only an absent decision or UNKNOWN remains an
                # actionable clarification.  A user-confirmed refusal,
                # flexibility, or delegation must never be asked again.
                self.meta.field_decisions.get(path) not in FIELD_DECISIONS_THAT_CLOSE_COLLECTION
            )]
        if self.travelers.adults == 0 and self.travelers.children == 0:
            self.missing_fields.append('travelers.adults')
        return self


class Region(Model):
    city: str
    province: str | None = None
    country: str | None = None


class CandidateRegion(Region):
    reason: str
    candidate_id: NonEmpty | None = None
    rank: PositiveInt | None = None


class ConstraintProposal(Model):
    proposal_id: NonEmpty
    fields: Annotated[list[NonEmpty], Field(min_length=1)]
    current_values: dict[str, object] | None = None
    proposed_values: dict[str, object]
    reason: NonEmpty

    @model_validator(mode="after")
    def proposal_fields(self):
        if set(self.fields) != set(self.proposed_values) or len(self.fields) != len(set(self.fields)):
            raise ValueError("proposal values must match unique fields")
        if self.current_values is not None and set(self.fields) != set(self.current_values):
            raise ValueError('current constraint values must match proposal fields')
        return self


class InformationRequest(Model):
    purpose: Literal["trip_request", "destination_info"]
    fields: Annotated[list[NonEmpty], Field(min_length=1)]
    reason: NonEmpty


class DestinationRecovery(Model):
    reason: NonEmpty
    fields: Annotated[list[NonEmpty], Field(min_length=1)]
    constraint_proposal: ConstraintProposal | None = None


class DestinationResult(Contract):
    request_type: Literal["EXPLICIT", "IMPLICIT", "AMBIGUOUS", "INSUFFICIENT"]
    selected_region: Region | None
    selection_status: Literal["selected", "needs_user_choice", "no_valid_candidate", "needs_more_info"]
    selection_reason: str
    candidate_regions: list[CandidateRegion]
    missing_fields: list[str]
    information_requests: list[InformationRequest] = Field(default_factory=list)
    recovery: DestinationRecovery | None = None
    selected_candidate_id: NonEmpty | None = None
    destination_source: DestinationSource = None
    selection_method: Literal['USER_EXPLICIT', 'USER_CHOICE', 'AGENT_DELEGATED', 'SYSTEM_DEFAULT'] | None = None

    @model_validator(mode="after")
    def selection_consistent(self):
        if (self.selection_status == "selected") != (self.selected_region is not None):
            raise ValueError("selected status requires selected_region; other statuses must leave it null")
        if self.selection_status == "needs_user_choice" and not self.candidate_regions:
            raise ValueError("needs_user_choice requires at least one candidate for confirmation")
        if self.selection_status == "no_valid_candidate" and self.candidate_regions:
            raise ValueError("no_valid_candidate cannot contain candidates")
        for key in ("candidate_id", "rank"):
            values = [getattr(c, key) for c in self.candidate_regions if getattr(c, key) is not None]
            if len(values) != len(set(values)):
                raise ValueError(f"duplicate candidate {key}")
        if self.information_requests and self.selection_status != "needs_more_info":
            raise ValueError("information_requests require needs_more_info")
        if self.recovery is not None and self.selection_status != "no_valid_candidate":
            raise ValueError("recovery requires no_valid_candidate")
        return self

    def require_canonical_recovery(self):
        """Legacy results remain readable, but cannot drive routing without purpose."""
        if self.selection_status == "needs_more_info" and not self.information_requests:
            raise ValueError("needs_more_info requires structured information_requests")
        # No recovery is a valid terminal result; it must never invent a question.
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


class QuestionOption(Model):
    option_id: NonEmpty
    city: str
    province: str | None = None
    country: str | None = None
    reason: str | None = None
    candidate_id: NonEmpty | None = None
    rank: PositiveInt | None = None


class PendingQuestion(Model):
    question: NonEmpty
    fields: list[str]
    kind: QuestionKind = "trip_request"
    options: list[QuestionOption] = Field(default_factory=list)
    question_id: UUID | None = None
    episode_id: UUID | None = None
    status: Literal["legacy", "open", "answered", "cancelled", "superseded"] = "legacy"
    intent_snapshot: SelectionIntent = "UNSPECIFIED"
    round: PositiveInt | None = None
    constraint_proposal: ConstraintProposal | None = None

    @model_validator(mode="after")
    def unique_option_ids(self):
        option_ids = [option.option_id for option in self.options]
        if len(option_ids) != len(set(option_ids)):
            raise ValueError("question option_id values must be unique")
        if self.status != "legacy":
            if self.question_id is None or self.episode_id is None or self.round is None:
                raise ValueError("canonical question requires identity, episode and round")
            if not self.fields or any(not f.strip() for f in self.fields) or len(set(self.fields)) != len(self.fields):
                raise ValueError("canonical question requires unique nonempty fields")
            if self.kind == "destination_choice":
                if not self.options or any(not o.candidate_id or not o.rank or not o.reason or not o.reason.strip() for o in self.options):
                    raise ValueError("choice requires candidate identities, ranks and reasons")
                for key in ("candidate_id", "rank"):
                    values = [getattr(o, key) for o in self.options]
                    if len(values) != len(set(values)):
                        raise ValueError(f"duplicate option {key}")
            elif self.options:
                raise ValueError("only destination_choice has candidate options")
            if self.constraint_proposal and (self.kind != "destination_info" or not set(self.constraint_proposal.fields) <= set(self.fields)):
                raise ValueError("constraint proposal must belong to destination_info fields")
        return self

    @property
    def counter_group(self):
        return "trip_request" if self.kind == "trip_request" else "destination"

    def require_actionable(self):
        # Revalidation also catches callers that mutated an existing model.
        question = type(self).model_validate(self.model_dump())
        if question.status != "open":
            raise ValueError("question is not open/actionable")
        return question


class AnswerHistory(Model):
    round: PositiveInt
    kind: QuestionKind = "trip_request"
    asked_fields: list[str]
    question: str
    answer_raw: str
    resolved_fields: list[str]
    declared_unknown_fields: list[str]
    answer_id: UUID | None = None
    episode_id: UUID | None = None
    question_id: UUID | None = None
    selected_option_id: NonEmpty | None = None
    confirmed_proposal_id: NonEmpty | None = None
    constraint_confirmed: StrictBool | None = None
    destination_update: Destination | None = None

    @model_validator(mode="after")
    def linked_identity(self):
        ids = (self.answer_id, self.episode_id, self.question_id)
        if any(v is not None for v in ids) and not all(v is not None for v in ids):
            raise ValueError("canonical answer requires answer, episode and question identity")
        if self.selected_option_id and self.kind != "destination_choice":
            raise ValueError("selection requires destination_choice")
        if (self.confirmed_proposal_id is None) != (self.constraint_confirmed is None):
            raise ValueError("constraint confirmation requires proposal identity and decision")
        if (self.selected_option_id or self.confirmed_proposal_id) and self.answer_id is None:
            raise ValueError("selection/confirmation requires canonical identity")
        if self.destination_update is not None:
            d = self.destination_update
            if self.kind != 'destination_choice' or self.answer_id is None or self.selected_option_id:
                raise ValueError('destination update requires a canonical non-option choice response')
            if not ((d.selection_intent == 'EXPLICIT' and d.selection_authority == 'USER' and d.city and d.city.strip())
                    or (d.selection_intent in {'ANY_DESTINATION', 'USER_UNKNOWN'}
                        and d.selection_authority == 'USER')
                    or (d.selection_intent == 'DELEGATE_SELECTION'
                        and d.selection_authority == 'AGENT')):
                raise ValueError('destination update requires a parser-confirmed intent')
        return self

    def validate_for(self, question: PendingQuestion):
        question.require_actionable()
        if self.answer_id is None or self.question_id != question.question_id or self.episode_id != question.episode_id:
            raise ValueError("stale or cross-episode answer")
        if (self.kind, self.round, self.question, self.asked_fields) != (question.kind, question.round, question.question, question.fields):
            raise ValueError("answer snapshot differs from question")
        if not set(self.resolved_fields + self.declared_unknown_fields) <= set(question.fields):
            raise ValueError("answer fields outside question")
        if set(self.resolved_fields) & set(self.declared_unknown_fields):
            raise ValueError("field cannot be resolved and unknown")
        if question.kind == 'destination_choice':
            if self.selected_option_id is not None:
                if self.selected_option_id not in {o.option_id for o in question.options}:
                    raise ValueError('unknown option')
                if self.destination_update is not None:
                    raise ValueError('option and new destination are mutually exclusive')
            elif self.destination_update is None and 'destination.city' not in self.declared_unknown_fields:
                raise ValueError('missing option or parser-confirmed destination response')
        if question.constraint_proposal:
            if self.confirmed_proposal_id != question.constraint_proposal.proposal_id or self.constraint_confirmed is None:
                raise ValueError("proposal requires explicit confirmation decision")
        elif self.confirmed_proposal_id is not None:
            raise ValueError("question has no constraint proposal")
        return self


class DestinationEpisode(SelectionPolicy):
    episode_id: UUID
    request_id: UUID
    status: Literal["active", "completed", "failed"] = "active"
    destination_round: Minutes = 0
    max_destination_rounds: Annotated[StrictInt, Field(ge=0, le=2)] = 2
    final_resolve_status: Literal["not_started", "claimed", "completed"] = "not_started"
    final_resolve_id: UUID | None = None
    final_resolve_result: DestinationResult | None = None

    @model_validator(mode="after")
    def consistent(self):
        if self.destination_round > self.max_destination_rounds:
            raise ValueError("episode destination budget exceeded")
        if (self.final_resolve_status == "not_started") != (self.final_resolve_id is None):
            raise ValueError("final resolve identity/state mismatch")
        if (self.final_resolve_status == "completed") != (self.final_resolve_result is not None):
            raise ValueError("completed final resolve requires persisted result")
        return self

    def default_candidate(self):
        """A permission gate, not an orchestration side effect."""
        self.consistent()
        self.authority_is_explicit()
        if self.status == 'failed' or self.selection_intent != "ANY_DESTINATION" or self.final_resolve_status != "completed":
            raise ValueError("default requires exhausted ANY_DESTINATION after final resolve")
        candidates = self.final_resolve_result.candidate_regions
        if self.final_resolve_result.selection_status not in {'selected', 'needs_user_choice'} or self.final_resolve_result.missing_fields:
            raise ValueError('final resolve remains unresolved')
        ranked = [c for c in candidates if c.rank == 1 and c.candidate_id and c.city.strip() and c.reason.strip()]
        if len(ranked) != 1:
            raise ValueError("no unique valid rank 1 candidate")
        return ranked[0]


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
    max_destination_rounds: Minutes = 2
    destination_episode: DestinationEpisode | None = None
    pending_fields: list[str]
    retry_count: Minutes

    @model_validator(mode="after")
    def clarification_consistent(self):
        if self.clarification_round > self.max_clarification_rounds:
            raise ValueError("clarification limit exceeded")
        if self.destination_round > self.max_destination_rounds:
            raise ValueError("destination limit exceeded")
        if self.destination_episode:
            episode = self.destination_episode
            if episode.request_id != self.request_id:
                raise ValueError("episode belongs to another workflow")
            if (self.destination_round, self.max_destination_rounds) != (episode.destination_round, episode.max_destination_rounds):
                raise ValueError("workflow destination budget must mirror episode")
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
