import asyncio
import json
from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError

from shared.contracts import (TripRequest, DestinationResult, PlaceCandidate, CostedPlaceCandidate,
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
    ("trip_request",TripRequest,False), ("destination_result",DestinationResult,False),
    ("place_candidates",PlaceCandidate,True), ("costed_place_candidates",CostedPlaceCandidate,True),
    ("planning_input",PlanningInput,False), ("itinerary",Itinerary,False),
    ("time_constraints",TimeConstraints,False), ("validation_result",ValidationResult,False),
])
def test_fixture_roundtrip(name, model, many):
    data = payload(name)
    for item in data if many else [data]:
        parsed = model.model_validate(item)
        assert model.model_validate_json(parsed.model_dump_json()) == parsed


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


@pytest.mark.parametrize("value", [-1,1.1,"100",True,None])
def test_money_rejects_invalid(value):
    with pytest.raises(ValidationError):
        CostRange(min=value,max=200)


def test_money_bounds():
    assert CostRange(min=0,max=0).min == 0
    with pytest.raises(ValidationError):
        CostRange(min=2,max=1)


@pytest.mark.parametrize("path,value", [
    (("destination","selection_mode"),"EXPLICIT"), (("trip","duration_days"),"3"),
    (("trip","duration_days"),2), (("trip","end_date"),"2026-11-13"),
    (("trip","timezone"),"Bad/Timezone"), (("budget","max_overrun_percent"),1),
    (("trip","arrival","datetime"),"2026-11-14T08:00:00"),
])
def test_request_invalid(request_data,path,value):
    target=request_data
    for key in path[:-1]:
        target=target[key]
    target[path[-1]]=value
    with pytest.raises(ValidationError):
        TripRequest.model_validate(request_data)


def test_null_not_zero_and_no_repeat_question(request_data):
    request_data["budget"]["amount"]=None
    request_data["meta"]["field_sources"]["budget.amount"]="user"
    req=TripRequest.model_validate(request_data)
    assert req.budget.amount is None
    assert "budget.amount" not in req.missing_fields
    request_data["meta"]["field_sources"].pop("budget.amount")
    assert "budget.amount" in TripRequest.model_validate(request_data).missing_fields


@pytest.mark.parametrize("status,cost,confidence,valid", [
    ("UNKNOWN",None,None,True), ("UNKNOWN",{"min":0,"max":0,"currency":"VND"},None,False),
    ("VERIFIED_FREE",{"min":0,"max":0,"currency":"VND"},None,True),
    ("VERIFIED_FREE",{"min":0,"max":1,"currency":"VND"},None,False),
    ("ESTIMATED",None,.7,False), ("ESTIMATED",{"min":0,"max":0,"currency":"VND"},.7,False),
    ("ESTIMATED",{"min":1,"max":2,"currency":"VND"},None,False),
    ("estimated",{"min":1,"max":2,"currency":"VND"},.7,False),
])
def test_price_integrity(status,cost,confidence,valid):
    data=payload("costed_place_candidates")[0]
    data.update(price_status=status,estimated_total_cost=cost,price_confidence_score=confidence)
    if valid:
        assert CostedPlaceCandidate.model_validate(data).estimated_total_cost is None or status=="VERIFIED_FREE"
    else:
        with pytest.raises(ValidationError):
            CostedPlaceCandidate.model_validate(data)


@pytest.mark.parametrize("start,end,valid", [("09:00","09:00",True),("20:00","09:00",False),("24:00","25:00",False),("9:00","10:00",False)])
def test_time_window(start,end,valid):
    data=dict(start=dict(value=start,is_hard=False),end=dict(value=end,is_hard=True))
    if valid:
        ActivityWindow.model_validate(data)
    else:
        with pytest.raises(ValidationError):
            ActivityWindow.model_validate(data)


@pytest.mark.parametrize("hard", [True,False])
def test_is_hard(hard):
    assert Constraint[int](value=1,is_hard=hard).is_hard is hard


@pytest.mark.parametrize("hard", ["false",0,None])
def test_is_hard_strict(hard):
    with pytest.raises(ValidationError):
        Constraint[int](value=1,is_hard=hard)


def test_count_target_soft_and_bounds():
    for values in [(1,2,3,True),(3,2,1,False)]:
        low,target,high,hard=values
        with pytest.raises(ValidationError):
            ActivityCount(min=dict(value=low,is_hard=True),target=dict(value=target,is_hard=hard),max=dict(value=high,is_hard=True))


def test_duration_and_meal():
    with pytest.raises(ValidationError):
        VisitDuration(min_minutes=60,typical_minutes=30,max_minutes=90,source="crawled")
    with pytest.raises(ValidationError):
        MealWindow(type="dinner",start="18:00",end="18:30",duration_minutes=60,required=True)


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


@pytest.mark.parametrize("source,hard", [("user",True),("default",False),("inferred",False)])
def test_preference_sources(request_data,defaults,source,hard):
    request_data["meta"]["field_sources"]["preferences.pace"]=source
    assert plan(request_data,defaults).days[0].pace.is_hard is hard


def test_async_interface(request_data,defaults):
    destination=DestinationResult.model_validate(payload("destination_result"))
    result=asyncio.run(DeterministicConstraintPlanner().build(TripRequest.model_validate(request_data),destination,defaults=defaults.model_dump()))
    assert result == plan(request_data,defaults)


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


def test_preference_default_authorization(request_data,defaults):
    request_data["preferences"]["pace"]=None
    request_data["meta"]["field_sources"].pop("preferences.pace")
    configured=defaults.model_copy(update={"pace":"relaxed"})
    with pytest.raises(ConstraintPlanningError):
        plan(request_data,configured)
    configured.allow_preference_defaults=True
    assert not plan(request_data,configured).days[0].pace.is_hard


def test_unknown_source_does_not_repeat_pending(request_data,defaults):
    request_data["preferences"]["pace"]=None
    request_data["meta"]["field_sources"]["preferences.pace"]="user"
    with pytest.raises(ConstraintPlanningError) as error:
        plan(request_data,defaults)
    # Missing executable data still reported, Orchestrator intersects with TripRequest.missing_fields.
    assert "preferences.pace" not in TripRequest.model_validate(request_data).missing_fields
    assert error.value.issues[0].code=="unknown_required_value"
    assert "preferences.pace" not in error.value.pending_fields


def test_missing_source(request_data,defaults):
    request_data["meta"]["field_sources"].pop("preferences.transport_modes")
    with pytest.raises(ConstraintPlanningError) as error:
        plan(request_data,defaults)
    assert any(i.code=="missing_source" for i in error.value.issues)


def test_no_invented_defaults(request_data):
    with pytest.raises(ConstraintPlanningError) as error:
        plan(request_data,PlannerDefaults())
    assert error.value.pending_fields


def test_return_by_without_end(request_data,defaults):
    request_data["daily_preferences"][0]["activity_end"]=None
    result=plan(request_data,defaults)
    assert result.days[1].activity_window.end.value=="12:00"
    assert result.days[1].activity_window.end.is_hard


@pytest.mark.parametrize("kind", ["time","count","rest","meal"])
def test_conflicts(request_data,defaults,kind):
    daily=request_data["daily_preferences"][0]
    if kind=="time":
        daily["activity_start"]="13:00"
    elif kind=="count":
        daily["min_activities"]=3
    elif kind=="rest":
        daily["rest_minutes"]=181
    else:
        defaults.meal_windows[0].required=True
    with pytest.raises(ConstraintPlanningError) as error:
        plan(request_data,defaults)
    assert any(i.code=="conflicting_constraints" for i in error.value.issues)


@pytest.mark.parametrize("kind", ["duplicate","outside"])
def test_daily_day_validation(request_data,kind):
    if kind=="duplicate":
        request_data["daily_preferences"]*=2
    else:
        request_data["daily_preferences"][0]["day"]=4
    with pytest.raises(ValidationError):
        TripRequest.model_validate(request_data)


@pytest.mark.parametrize("kind", ["unit","locations","endpoint","must_avoid","missing_place"])
def test_planning_consistency(kind):
    data=payload("planning_input")
    if kind=="unit": data["travel_time_matrix"]["unit"]="m"
    if kind=="locations": data["travel_distance_matrix"]["locations"].reverse()
    if kind=="endpoint": data["time_constraints"]["days"][0]["start_location_id"]=None
    if kind=="must_avoid": data.update(must_visit_place_ids=["p001"],avoid_place_ids=["p001"])
    if kind=="missing_place": data["candidate_places"][0]["place_id"]="absent"
    with pytest.raises(ValidationError): PlanningInput.model_validate(data)


def test_workflow_clarification():
    from uuid import uuid4
    data=dict(request_id=uuid4(),trip_id=uuid4(),status="clarifying",current_step="request_parser",completed_steps=[],artifacts={},
        clarification_round=1,max_clarification_rounds=3,pending_fields=["trip.start_date"],retry_count=0)
    WorkflowState.model_validate(data)
    data["pending_questions"]=[]
    with pytest.raises(ValidationError): WorkflowState.model_validate(data)
    data.pop("pending_questions")
    data["clarification_round"]=4
    with pytest.raises(ValidationError): WorkflowState.model_validate(data)


def test_required_meal_can_exceed_soft_window(request_data,defaults):
    request_data["daily_preferences"]=[]
    defaults.activity_end="12:00"
    defaults.meal_windows[0].required=True
    assert plan(request_data,defaults).days[0].meal_windows[0].start=="17:30"


@pytest.mark.parametrize("kind", ["missing_rules","hard_warning","soft_violation","invalid_accept"])
def test_validation_result_consistency(kind):
    data=payload("validation_result")
    if kind=="missing_rules": data["checked_rules"].remove("budget")
    if kind=="hard_warning": data["warnings"]=[dict(type="x",rule="budget",severity="hard",message="x")]
    if kind=="soft_violation": data["violations"]=[dict(type="x",rule="budget",severity="soft",message="x")]
    if kind=="invalid_accept": data["is_valid"]=False
    with pytest.raises(ValidationError): ValidationResult.model_validate(data)


def test_inferred_requires_confidence(request_data):
    request_data["meta"]["field_confidences"]={}
    with pytest.raises(ValidationError): TripRequest.model_validate(request_data)


def test_multiple_daily_overrides(request_data,defaults):
    another=deepcopy(request_data["daily_preferences"][0])
    another.update(day=3,activity_start="10:00",activity_end="16:00",return_by=None,
                   min_activities=0,target_activities=0,max_activities=0,rest_minutes=0,pace_override="relaxed")
    request_data["daily_preferences"].append(another)
    for key,value in another.items():
        if key!="day" and value is not None:
            request_data["meta"]["field_sources"][f"daily_preferences.1.{key}"]="user"
    result=plan(request_data,defaults)
    assert result.days[1].activity_window.end.value=="12:00"
    assert result.days[2].activity_window.start.value=="10:00"
    assert result.days[2].target_activity_count.max.value==0
    assert result.days[2].pace.is_hard


def test_meal_exact_boundary_and_null_hours():
    meal=MealWindow(type="dinner",start="17:30",end="18:30",duration_minutes=60,required=False)
    assert meal.duration_minutes==60
    data=payload("place_candidates")[0]["opening_hours"]
    data["weekly_schedule"][0].update(open=None,close=None)
    assert OpeningHours.model_validate(data).weekly_schedule[0].open is None
    data["weekly_schedule"][0]["weekday"]=0
    with pytest.raises(ValidationError): OpeningHours.model_validate(data)


@pytest.mark.parametrize("end_source,deadline_source,end,deadline,expected,hard", [
    ("default","user","11:00","12:00","12:00",True),
    ("user","default","12:00","11:00","12:00",True),
    ("user","user","11:00","12:00","11:00",True),
    ("inferred","default","11:00","12:00","11:00",False),
])
def test_return_by_preserves_hard_boundary(request_data,defaults,end_source,deadline_source,end,deadline,expected,hard):
    daily=request_data["daily_preferences"][0]
    daily.update(activity_end=end,return_by=deadline)
    request_data["meta"]["field_sources"].update({"daily_preferences.0.activity_end":end_source,
                                               "daily_preferences.0.return_by":deadline_source})
    if end_source=="inferred":
        request_data["meta"]["field_confidences"]["daily_preferences.0.activity_end"]=.8
    result=plan(request_data,defaults)
    assert result.days[1].activity_window.end.value==expected
    assert result.days[1].activity_window.end.is_hard is hard
