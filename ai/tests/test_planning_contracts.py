import asyncio
import json
from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError

from shared.contracts import (AnswerHistory, PendingQuestion, TripRequest, DestinationResult, PlaceCandidate, CostedPlaceCandidate,
    TimeConstraints, PlanningInput, Itinerary, ValidationResult, WorkflowState)
from shared.contracts import (ActivityCount, ActivityWindow, Constraint, CostRange,
    MealWindow, OpeningHours, VisitDuration)
from ai.planning.constraint_planner import (
    ConstraintPlanningError, DeterministicConstraintPlanner, PlannerDefaults,
)

FIXTURES = Path(__file__).resolve().parents[2] / "shared" / "samples"


def payload(name):
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


@pytest.fixture
def request_data():
    return payload("trip_request")


@pytest.fixture
def defaults():
    return PlannerDefaults.model_validate(payload("planner_defaults"))


def plan(data, defaults):
    return DeterministicConstraintPlanner().plan(TripRequest.model_validate(data), defaults)


@pytest.mark.parametrize("name,model,many", [
    ("trip_request",TripRequest,False), ("planning_input",PlanningInput,False),
    ("itinerary",Itinerary,False), ("validation_result",ValidationResult,False),
])
def test_fixture_roundtrip(name, model, many):
    data = payload(name)
    for item in data if many else [data]:
        parsed = model.model_validate(item)
        assert model.model_validate_json(parsed.model_dump_json()) == parsed


@pytest.mark.smoke
def test_fixture_links_and_totals():
    places = {p["place_id"]:p for p in payload("place_candidates")}
    costs = {p["place_id"]:p for p in payload("costed_place_candidates")}
    inp, itinerary, validation = payload("planning_input"), payload("itinerary"), payload("validation_result")
    assert set(places) == set(costs) == {p["place_id"] for p in inp["candidate_places"]}
    for day in itinerary["days"]:
        for activity in day["activities"]:
            assert activity["types"] == places[activity["place_id"]]["types"]
            assert activity["estimated_total_cost"] == {k: costs[activity["place_id"]]["estimated_total_cost"][k] for k in ("min","max")}
        for bound in ("min", "max"):
            assert day["day_total_cost"][bound] == sum(a["estimated_total_cost"][bound] for a in day["activities"])
    for bound in ("min", "max"):
        assert itinerary["summary"]["total_cost"][bound] == sum(d["day_total_cost"][bound] for d in itinerary["days"])
    assert validation["recomputed"]["cost_in_scope"] == itinerary["summary"]["total_cost"]


@pytest.mark.parametrize("value", [-1,"100",None])
def test_money_rejects_invalid(value):
    with pytest.raises(ValidationError):
        CostRange(min=value,max=200)


@pytest.mark.parametrize("path,value", [
    (("destination","selection_mode"),"EXPLICIT"),
    (("trip","duration_days"),2),
    (("trip","timezone"),"Bad/Timezone"),
])
def test_request_invalid(request_data,path,value):
    target=request_data
    for key in path[:-1]:
        target=target[key]
    target[path[-1]]=value
    with pytest.raises(ValidationError):
        TripRequest.model_validate(request_data)


@pytest.mark.parametrize("status,cost,confidence,valid", [
    ("UNKNOWN",None,None,True), ("UNKNOWN",{"min":0,"max":0,"currency":"VND"},None,False),
    ("VERIFIED_FREE",{"min":0,"max":0,"currency":"VND"},None,True),
    ("ESTIMATED",{"min":1,"max":2,"currency":"VND"},None,False),
])
def test_price_integrity(status,cost,confidence,valid):
    data=payload("costed_place_candidates")[0]
    data.update(price_status=status,estimated_total_cost=cost,price_confidence_score=confidence)
    if valid:
        assert CostedPlaceCandidate.model_validate(data).estimated_total_cost is None or status=="VERIFIED_FREE"
    else:
        with pytest.raises(ValidationError):
            CostedPlaceCandidate.model_validate(data)


@pytest.mark.parametrize("start,end,valid", [("09:00","09:00",True),("20:00","09:00",False),("24:00","25:00",False)])
def test_time_window(start,end,valid):
    data=dict(start=dict(value=start,is_hard=False),end=dict(value=end,is_hard=True))
    if valid:
        ActivityWindow.model_validate(data)
    else:
        with pytest.raises(ValidationError):
            ActivityWindow.model_validate(data)


def test_multiday_sources_and_no_mutation(request_data,defaults):
    before=deepcopy(request_data)
    result=plan(request_data,defaults)
    assert request_data == before
    assert len(result.days)==3
    first,second,third=result.days
    assert first.activity_window.start.value=="09:00"
    assert not first.activity_window.start.is_hard
    assert second.activity_window.end.value=="12:00"
    assert second.activity_window.end.is_hard
    assert second.rest_minutes.value==0 and second.rest_minutes.is_hard
    assert not second.target_activity_count.target.is_hard
    assert not first.pace.is_hard # inferred
    assert first.transport_mode.is_hard # user
    assert first.meal_windows and not second.meal_windows and third.meal_windows


@pytest.mark.parametrize("field", ["start_date","end_date"])
def test_missing_dates(request_data,defaults,field):
    request_data["trip"][field]=None
    with pytest.raises(ConstraintPlanningError) as error:
        plan(request_data,defaults)
    assert f"trip.{field}" in error.value.pending_fields
    assert error.value.as_dict()["issues"]


def test_date_derived_duration_and_single_day(request_data,defaults):
    request_data["trip"].update(duration_days=None)
    assert len(plan(request_data,defaults).days)==3
    request_data["trip"].update(end_date="2026-11-14",duration_days=1)
    request_data["daily_preferences"]=[]
    assert len(plan(request_data,defaults).days)==1


def test_no_invented_defaults(request_data):
    with pytest.raises(ConstraintPlanningError) as error:
        plan(request_data,PlannerDefaults())
    assert error.value.pending_fields


@pytest.mark.parametrize("kind", ["unit","locations","must_avoid"])
def test_planning_consistency(kind):
    data=payload("planning_input")
    if kind=="unit": data["travel_time_matrix"]["unit"]="m"
    if kind=="locations": data["travel_distance_matrix"]["locations"].reverse()
    if kind=="endpoint": data["time_constraints"]["days"][0]["start_location_id"]=None
    if kind=="must_avoid": data.update(must_visit_place_ids=["p001"],avoid_place_ids=["p001"])
    if kind=="missing_place": data["candidate_places"][0]["place_id"]="absent"
    with pytest.raises(ValidationError): PlanningInput.model_validate(data)


@pytest.mark.parametrize("kind", ["missing_rules","invalid_accept"])
def test_validation_result_consistency(kind):
    data=payload("validation_result")
    if kind=="missing_rules": data["checked_rules"].remove("budget")
    if kind=="hard_warning": data["warnings"]=[dict(type="x",rule="budget",severity="hard",message="x")]
    if kind=="soft_violation": data["violations"]=[dict(type="x",rule="budget",severity="soft",message="x")]
    if kind=="invalid_accept": data["is_valid"]=False
    with pytest.raises(ValidationError): ValidationResult.model_validate(data)


def test_meal_exact_boundary_and_null_hours():
    meal=MealWindow(type="dinner",start="17:30",end="18:30",duration_minutes=60,required=False)
    assert meal.duration_minutes==60
    data=payload("place_candidates")[0]["opening_hours"]
    data["weekly_schedule"][0].update(open=None,close=None)
    assert OpeningHours.model_validate(data).weekly_schedule[0].open is None
    data["weekly_schedule"][0]["weekday"]=0
    with pytest.raises(ValidationError): OpeningHours.model_validate(data)
