"""Deterministic normalization only; no scheduling or external services."""
from datetime import timedelta

from pydantic import Field, ValidationError

from app.core.errors import ApplicationError
from app.models.contracts import (
    Clock, DestinationResult, MealWindow, Minutes, Model, TimeConstraints,
    TripRequest, clock_minutes,
)


class PlannerDefaults(Model):
    """Explicit caller policy. No undocumented pace/count/meal lookup table."""
    activity_start: Clock | None = None
    activity_end: Clock | None = None
    min_activities: Minutes | None = None
    target_activities: Minutes | None = None
    max_activities: Minutes | None = None
    rest_minutes: Minutes | None = None
    pace: str | None = None
    transport_modes: list[str] | None = None
    interests: list[str] | None = None
    meal_windows: list[MealWindow] = Field(default_factory=list)
    # Orchestrator sets this only after clarification is exhausted/accepted.
    allow_preference_defaults: bool = False


class PlannerIssue(Model):
    code: str
    fields: list[str]
    message: str
    day: int | None = None


class ConstraintPlanningError(ApplicationError):
    def __init__(self, issues: list[PlannerIssue]):
        self.issues = issues
        self.pending_fields = list(dict.fromkeys(
            field for issue in issues if issue.code == "missing_required_field" for field in issue.fields
        ))
        super().__init__("constraint_planning_failed", "; ".join(issue.message for issue in issues))

    def as_dict(self) -> dict[str, object]:
        return {"code": self.code, "pending_fields": self.pending_fields,
                "issues": [issue.model_dump() for issue in self.issues]}


class DeterministicConstraintPlanner:
    async def build(self, request: TripRequest, destination: DestinationResult,
                    *, defaults: dict[str, object]) -> TimeConstraints:
        """Adapter matching agents.interfaces.ConstraintPlanner; destination is not needed."""
        return self.plan(request, PlannerDefaults.model_validate(defaults))

    def plan(self, request: TripRequest, defaults: PlannerDefaults) -> TimeConstraints:
        issues: list[PlannerIssue] = []

        def issue(code, fields, message, day=None):
            issues.append(PlannerIssue(code=code, fields=fields, message=message, day=day))

        trip = request.trip
        for name in ("start_date", "end_date"):
            if getattr(trip, name) is None:
                issue("missing_required_field", [f"trip.{name}"], f"trip.{name} is required")
        if issues:
            raise ConstraintPlanningError(issues)
        duration = (trip.end_date - trip.start_date).days + 1
        by_day = {pref.day: (index, pref) for index, pref in enumerate(request.daily_preferences)}
        sources = request.meta.field_sources
        days = []

        def resolve(value, path, default, *, preference=False, day=None):
            source = sources.get(path)
            if value is not None:
                if source is None:
                    issue("missing_source", [path], f"Missing field_sources entry for {path}", day)
                return {"value": value, "is_hard": source == "user"}
            # A user-declared unknown isn't asked again, but still needs an explicit usable default.
            permitted = not preference or defaults.allow_preference_defaults or source == "user"
            if default is None or not permitted:
                code = "unknown_required_value" if source == "user" else "missing_required_field"
                issue(code, [path], f"No authorized default for {path}", day)
                return None
            return {"value": default, "is_hard": False}

        for number in range(1, duration + 1):
            index, daily = by_day.get(number, (None, None))

            def daily_value(name):
                path = f"daily_preferences.{index}.{name}" if daily else f"daily_preferences[day={number}].{name}"
                return resolve(getattr(daily, name) if daily else None, path,
                               getattr(defaults, name), day=number)

            start = daily_value("activity_start")
            # return_by is itself a usable upper boundary when activity_end is absent.
            end = (None if daily and daily.activity_end is None and daily.return_by is not None
                   else daily_value("activity_end"))
            if daily and daily.return_by is not None:
                deadline = resolve(daily.return_by, f"daily_preferences.{index}.return_by", None, day=number)
                # The output has one end boundary: a soft earlier preference must
                # never hide a later hard deadline (and vice versa).
                if (end is None or (deadline["is_hard"] and not end["is_hard"])
                        or (deadline["is_hard"] == end["is_hard"] and deadline["value"] < end["value"])):
                    end = deadline
            counts = {key: daily_value(name) for key, name in
                      (("min", "min_activities"), ("target", "target_activities"), ("max", "max_activities"))}
            if counts["target"]:
                counts["target"]["is_hard"] = False
            rest = daily_value("rest_minutes")
            if daily and daily.pace_override is not None:
                pace = resolve(daily.pace_override, f"daily_preferences.{index}.pace_override", None, day=number)
            else:
                pace = resolve(request.preferences.pace, "preferences.pace", defaults.pace, preference=True, day=number)
            transport = resolve(request.preferences.transport_modes, "preferences.transport_modes",
                                defaults.transport_modes, preference=True, day=number)
            interests = resolve(request.preferences.interests, "preferences.interests", defaults.interests,
                                preference=True, day=number)
            if not all([start, end, rest, pace, transport, interests, *counts.values()]):
                continue
            meals = []
            for meal in defaults.meal_windows:
                left, right = max(start["value"], meal.start), min(end["value"], meal.end)
                fits = left <= right and clock_minutes(right) - clock_minutes(left) >= meal.duration_minutes
                if meal.required and not fits:
                    hard_left = max(start["value"], meal.start) if start["is_hard"] else meal.start
                    hard_right = min(end["value"], meal.end) if end["is_hard"] else meal.end
                    if clock_minutes(hard_right) - clock_minutes(hard_left) < meal.duration_minutes:
                        issue("conflicting_constraints", ["meal_windows", "activity_window"],
                              "Required configured meal does not fit hard activity window", number)
                    else:
                        meals.append(meal.model_copy(update={"start": hard_left, "end": hard_right}))
                if fits:
                    meals.append(meal.model_copy(update={"start": left, "end": right}))
            if rest["is_hard"] and start["is_hard"] and end["is_hard"]:
                if rest["value"] > clock_minutes(end["value"]) - clock_minutes(start["value"]):
                    issue("conflicting_constraints", ["rest_minutes", "activity_window"],
                          "Hard rest exceeds hard activity window", number)
            days.append({"day": number, "date": trip.start_date + timedelta(days=number - 1),
                         "activity_window": {"start": start, "end": end}, "target_activity_count": counts,
                         "pace": pace, "transport_mode": transport, "meal_windows": meals,
                         "rest_minutes": rest,
                         "preferences": [{"value": interest, "is_hard": interests["is_hard"]}
                                         for interest in interests["value"]]})
        if issues:
            raise ConstraintPlanningError(issues)
        try:
            return TimeConstraints(days=days)
        except ValidationError as exc:
            raise ConstraintPlanningError([
                PlannerIssue(code="conflicting_constraints", fields=[".".join(map(str, error["loc"]))],
                             message=error["msg"]) for error in exc.errors()
            ]) from exc
