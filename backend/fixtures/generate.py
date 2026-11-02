"""Rebuild deterministic illustrative fixtures: python fixtures/generate.py."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.models.contracts import (TripRequest, DestinationResult, PlaceCandidate,
    CostedPlaceCandidate, PlanningInput, Itinerary, ValidationResult)
from app.services.constraint_planner import DeterministicConstraintPlanner, PlannerDefaults

ROOT = Path(__file__).parent


def save(name, value):
    if isinstance(value, list):
        data = [item.model_dump(mode="json") for item in value]
    elif isinstance(value, dict):
        data = value
    else:
        data = value.model_dump(mode="json")
    (ROOT / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    data = json.loads((ROOT / "trip_request.json").read_text(encoding="utf-8"))
    data["meta"]["field_sources"].update({"preferences.interests": "user", "preferences.transport_modes": "user"})
    template = dict(day=2, activity_start="09:00", activity_end="12:00", return_by="12:00",
        start_location=None, end_location=None, min_activities=1, target_activities=1,
        max_activities=2, rest_minutes=0, pace_override=None)
    data["daily_preferences"] = [template]
    for key, value in template.items():
        if key != "day" and value is not None:
            data["meta"]["field_sources"][f"daily_preferences.0.{key}"] = "user"
    request = TripRequest.model_validate(data)
    save("trip_request", request)
    destination = DestinationResult(request_type="EXPLICIT", selected_region=dict(city="Đà Lạt", province="Lâm Đồng", country="Việt Nam"),
        selection_status="selected", selection_reason="Điểm đến người dùng yêu cầu.", candidate_regions=[], missing_fields=[])
    save("destination_result", destination)
    defaults = PlannerDefaults(activity_start="09:00", activity_end="20:00", min_activities=0,
        target_activities=2, max_activities=4, rest_minutes=60,
        meal_windows=[dict(type="dinner", start="17:30", end="19:30", duration_minutes=60, required=False)])
    save("planner_defaults", defaults)
    times = DeterministicConstraintPlanner().plan(request, defaults)
    save("time_constraints", times)
    places, costs = [], []
    for index, (score, low, high) in enumerate([(92,40000,60000),(85,120000,200000),(78,30000,50000)], 1):
        food = index == 2
        place = PlaceCandidate(place_id=f"p{index:03}", google_place_id=None, name=f"Place {chr(64+index)}",
            category="food" if food else "nature", types=["restaurant", "food"] if food else ["park", "tourist_attraction"],
            google_maps_url=None, rating=None, user_rating_count=None, business_status=None, photos=[],
            location=dict(latitude=11.96-index*.01, longitude=108.44+index*.01, address=None),
            opening_hours=dict(timezone="Asia/Ho_Chi_Minh", weekly_schedule=[dict(weekday=d, open="07:30", close="21:00" if food else "17:00", is_closed=False) for d in (6,7,1)],
                special_hours=[dict(date="2026-12-25", open=None, close=None, is_closed=True, note="Đóng cửa")]),
            visit_duration=dict(min_minutes=30 if food else 60, typical_minutes=60 if food else 90, max_minutes=120,
                source="estimated", confidence=.7, reason="Dữ liệu minh họa, không tra cứu API."),
            suitability=dict(score_places=score, matched_interests=["food" if food else "nature"], reason="Khớp sở thích"),
            constraints=dict(reservation_required=False, accessibility_notes=[]), cluster_id=None,
            data_quality=dict(source="mock", opening_hours_verified=False, last_verified_at=None), source=dict(type="agent_suggested"))
        places.append(place)
        costs.append(CostedPlaceCandidate(place_id=place.place_id, google_place_id=None, name=place.name, category=place.category,
            types=place.types, address=None, score_places=score, price_status="ESTIMATED", price_confidence_score=.7,
            estimated_total_cost=dict(min=low,max=high,currency="VND")))
    save("place_candidates", places)
    save("costed_place_candidates", costs)
    # Fixture endpoints are resolved explicitly, not by the constraint planner.
    planning_times = times.model_copy(deep=True)
    for day in planning_times.days:
        day.start_location_id = day.end_location_id = "hotel"
    ids = [p.place_id for p in places] + ["hotel"]
    planning = PlanningInput(trip_id="trip_001", budget=request.budget,
        candidate_places=[dict(place_id=p.place_id, types=p.types, score_places=p.suitability.score_places,
            visit_duration_typical=p.visit_duration.typical_minutes, estimated_total_cost=c.estimated_total_cost,
            price_status=c.price_status, price_confidence_score=c.price_confidence_score,
            latitude=p.location.latitude, longitude=p.location.longitude, cluster_id=p.cluster_id, opening_hours=p.opening_hours)
            for p,c in zip(places,costs)], must_visit_place_ids=[], avoid_place_ids=[], time_constraints=planning_times,
        travel_time_matrix=dict(locations=ids, mode="motorbike", unit="minutes", values=[[0 if i==j else 10 for j in ids] for i in ids]),
        travel_distance_matrix=dict(locations=ids, mode="motorbike", unit="m", values=[[0 if i==j else 2000 for j in ids] for i in ids]),
        weights=dict(alpha=1,beta=.3,gamma=.2,delta=.5,normalized=True),
        optimization=dict(objective="maximize_total_utility",allow_optional_places_to_be_skipped=True,cost_basis_hard_limit="max",cost_basis_objective="midpoint"),
        solver_config=dict(time_limit_seconds=30,random_seed=42,max_retries=3))
    save("planning_input", planning)
    days=[]
    for number,(p,c,day) in enumerate(zip(places,costs,times.days),1):
        amount = c.estimated_total_cost.model_dump(exclude={"currency"})
        days.append(dict(day=number,date=day.date, activities=[dict(place_id=p.place_id,types=p.types,
            arrival_time="09:10",start_time="09:10",departure_time="10:10" if number==2 else "10:40",
            travel_minutes_from_previous=10,estimated_total_cost=amount)],day_total_cost=amount))
    itinerary=Itinerary(trip_id="trip_001",status="feasible",currency="VND",days=days,
        summary=dict(total_scheduled_places=3,total_cost=dict(min=190000,max=310000),total_travel_minutes=0,
            objective_value=None,summary_message="Fixture viết tay: 3 địa điểm trong 3 ngày; không chạy solver."),
        dropped_places=[],relaxation_suggestions=[],diagnostics=dict(solver_status="feasible",optimality_proven=False,unsatisfied_constraints=[],warnings=[]))
    save("itinerary",itinerary)
    rules=["input_integrity","price_integrity","travel_time","overlap","opening_hours","visit_duration","day_start_window","day_end_window","meal_window","activity_count","rest_time","must_visit","budget","summary_consistency"]
    save("validation_result", ValidationResult(trip_id="trip_001",is_valid=True,violations=[],warnings=[],checked_rules=rules,
        recomputed=dict(cost_in_scope=dict(min=190000,max=310000),budget_limit=3000000,total_travel_minutes=0,total_scheduled_places=3),suggested_action="accept"))


if __name__ == "__main__":
    main()
