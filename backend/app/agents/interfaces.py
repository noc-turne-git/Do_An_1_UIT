"""Async component contracts only; implementations are intentionally out of scope.

Each method must validate input/output with the shared Pydantic models and must
not mutate inputs or WorkflowState. ValidationError denotes invalid schema;
ApplicationError(code, message, retryable) denotes technical failure. Domain
outcomes (missing fields, infeasible, violations) are returned as schema data.
Cancellation propagates; timeouts/network failures are translated by adapters.
"""
from datetime import date
from uuid import UUID
from typing import Protocol

from app.models.contracts import (
    BudgetResult, DestinationResult, Itinerary, PlaceCandidate, PlanningInput,
    TimeConstraints, TripRequest, ValidationResult,
)


class RequestParser(Protocol):
    async def parse(self, prompt: str, *, current_date: date,
                    context: dict[str, object], previous_request: TripRequest | None = None) -> TripRequest: ...


class DestinationAgent(Protocol):
    async def select(self, request: TripRequest) -> DestinationResult: ...


class ConstraintPlanner(Protocol):
    async def build(self, request: TripRequest, destination: DestinationResult,
                    *, defaults: dict[str, object]) -> TimeConstraints: ...


class PlaceAgent(Protocol):
    async def find(self, request: TripRequest, destination: DestinationResult,
                   time_constraints: TimeConstraints, *, max_candidates: int,
                   exclude_place_ids: list[str]) -> list[PlaceCandidate]: ...


class BudgetModule(Protocol):
    async def estimate(self, request: TripRequest, places: list[PlaceCandidate],
                       *, must_visit_place_ids: list[str]) -> BudgetResult: ...


class PlanningInputBuilder(Protocol):
    async def build(self, trip_id: UUID, request: TripRequest,
                    destination: DestinationResult, time_constraints: TimeConstraints,
                    places: list[PlaceCandidate], costs: BudgetResult,
                    *, configuration: dict[str, object]) -> PlanningInput: ...


class PlanningEngine(Protocol):
    async def plan(self, planning_input: PlanningInput) -> Itinerary: ...


class Validator(Protocol):
    async def validate(self, itinerary: Itinerary, planning_input: PlanningInput,
                       *, low_price_confidence: float = 0.5) -> ValidationResult: ...


class Explainer(Protocol):
    async def explain(self, itinerary: Itinerary, validation: ValidationResult) -> str:
        """Only for accepted validated itineraries; text cannot alter source data.

        Future implementation must cross-check facts, retry boundedly and fall
        back to summary_message as described in section 9.3.
        """
        ...
