"""Offline, deterministic adapters. No solver, business validator or external API."""
import json
from dataclasses import dataclass
from pathlib import Path

from app.agents import interfaces as api
from app.core.errors import ApplicationError
from app.models.contracts import (
    BudgetResult, DestinationResult, Itinerary, PlaceCandidate, PlanningInput,
    TripRequest, ValidationResult,
)
from app.services.constraint_planner import DeterministicConstraintPlanner

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


def fixture(name):
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


class MockRequestParser:
    async def parse(self, prompt, *, current_date, context, previous_request=None):
        # Already structured input; deliberately does not interpret natural language.
        return TripRequest.model_validate(context["trip_request"])


class MockDestinationAgent:
    async def select(self, request):
        result = fixture("destination_result")
        if request.destination.selection_mode == "ambiguous":
            cities = request.destination.candidate_cities
            if len(cities) >= 2:
                result.update(request_type="AMBIGUOUS", selected_region=None,
                              selection_status="needs_user_choice",
                              candidate_regions=[dict(city=c, reason="Mock choice") for c in cities])
        elif request.destination.selection_mode == "explicit" and request.destination.city != result["selected_region"]["city"]:
            raise ApplicationError("mock_fixture_unsupported", "Mock catalog supports only the fixture destination")
        return DestinationResult.model_validate(result)


class MockPlaceAgent:
    async def find(self, request, destination, time_constraints, *, max_candidates, exclude_place_ids):
        return [PlaceCandidate.model_validate(p) for p in fixture("place_candidates")
                if p["place_id"] not in exclude_place_ids][:max_candidates]


class MockBudgetModule:
    async def estimate(self, request, places, *, must_visit_place_ids):
        ids = {p.place_id for p in places}
        if request.budget.currency != "VND":
            raise ApplicationError("mock_fixture_unsupported", "Mock costs are VND only")
        return BudgetResult(places=[p for p in fixture("costed_place_candidates") if p["place_id"] in ids],
                            missing_costs=[], budget_reason="Fixed mock costs; no price lookup")


class MockPlanningInputBuilder:
    async def build(self, trip_id, request, destination, time_constraints, places, costs, *, configuration):
        data = fixture("planning_input")
        if {p.place_id for p in places} != {p.place_id for p in costs.places}:
            raise ApplicationError("planning_input_inconsistent", "Place and cost IDs differ")
        # Mock joining only; endpoints and matrices are explicit fixture data.
        times = time_constraints.model_dump(mode="json")
        for day in times["days"]:
            day["start_location_id"] = day["start_location_id"] or "hotel"
            day["end_location_id"] = day["end_location_id"] or "hotel"
        by_id = {p.place_id: p for p in costs.places}
        data.update(trip_id=trip_id, budget=request.budget.model_dump(), time_constraints=times)
        data["candidate_places"] = [dict(
            place_id=p.place_id, types=p.types, score_places=p.suitability.score_places,
            visit_duration_typical=p.visit_duration.typical_minutes,
            estimated_total_cost=by_id[p.place_id].estimated_total_cost,
            price_status=by_id[p.place_id].price_status,
            price_confidence_score=by_id[p.place_id].price_confidence_score,
            latitude=p.location.latitude, longitude=p.location.longitude,
            cluster_id=p.cluster_id, opening_hours=p.opening_hours) for p in places]
        def resolve(names):
            ids = {p.place_id for p in places}
            names_to_ids = {p.name: p.place_id for p in places}
            return [name if name in ids else names_to_ids.get(name, name) for name in names]
        data["must_visit_place_ids"] = resolve(request.destination.must_visit)
        data["avoid_place_ids"] = resolve(request.destination.avoid_places)
        if set(configuration) - {"weights", "optimization", "solver_config"}:
            raise ApplicationError("planning_input_inconsistent", "Mock configuration may only set weights, optimization and solver_config")
        if configuration:
            data.update(configuration)
        return PlanningInput.model_validate(data)


class MockPlanningEngine:
    async def plan(self, planning_input):
        data = fixture("itinerary")
        # Do not present a fixture for a different trip as a computed solution.
        expected = fixture("planning_input")
        if (planning_input.time_constraints.model_dump(mode="json") != expected["time_constraints"]
                or [p.place_id for p in planning_input.candidate_places] != [p["place_id"] for p in expected["candidate_places"]]):
            raise ApplicationError("mock_fixture_unsupported", "Engine fixture requires the sample dates, constraints and places")
        data["trip_id"] = planning_input.trip_id
        data["diagnostics"]["warnings"].append("MOCK: handwritten fixture; no optimization performed")
        return Itinerary.model_validate(data)


class MockValidator:
    async def validate(self, itinerary, planning_input, *, low_price_confidence=0.5):
        data = fixture("validation_result")
        data["trip_id"] = planning_input.trip_id
        data["recomputed"]["budget_limit"] = planning_input.budget.amount
        # checked_rules is fixture data, NOT evidence of executing business rules.
        return ValidationResult.model_validate(data)


class MockExplainer:
    async def explain(self, itinerary, validation):
        return itinerary.summary.summary_message


@dataclass
class Components:
    request_parser: api.RequestParser
    destination_agent: api.DestinationAgent
    constraint_planner: api.ConstraintPlanner
    place_agent: api.PlaceAgent
    budget_module: api.BudgetModule
    planning_input_builder: api.PlanningInputBuilder
    planning_engine: api.PlanningEngine
    validator: api.Validator
    explainer: api.Explainer


def mock_components():
    return Components(MockRequestParser(), MockDestinationAgent(), DeterministicConstraintPlanner(),
                      MockPlaceAgent(), MockBudgetModule(), MockPlanningInputBuilder(),
                      MockPlanningEngine(), MockValidator(), MockExplainer())
