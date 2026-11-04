"""Normalized result projections, written with their artifact in one transaction."""
from datetime import time
from uuid import UUID, uuid4

from sqlalchemy import select

from app.core.errors import ApplicationError
from app.db.models import (ItineraryRecord, ItineraryDayRecord, ItineraryActivityRecord,
    ItineraryDroppedPlaceRecord, RelaxationSuggestionRecord, ValidationResultRecord, ValidationIssueRecord)
from app.repositories.workflows import OwnedRepository


def bounds(cost):
    return (cost.min, cost.max) if cost is not None else (None, None)


class ResultRepository(OwnedRepository):
    def itinerary(self, request_id: UUID, artifact, value, attempt_no: int):
        request = self.request(request_id)
        if value.trip_id != request.trip_id:
            raise ApplicationError('planning_input_inconsistent', 'Itinerary trip differs')
        low, high = bounds(value.summary.total_cost)
        row = ItineraryRecord(itinerary_id=artifact.artifact_id, request_id=request_id,
            parent_artifact_id=artifact.parent_artifact_id, attempt_no=attempt_no,
            schema_version=value.schema_version, status=value.status, currency=value.currency,
            total_cost_min=low, total_cost_max=high, price_status=value.summary.price_status,
            total_travel_minutes=value.summary.total_travel_minutes,
            total_scheduled_places=value.summary.total_scheduled_places,
            objective_value=value.summary.objective_value, solver_status=value.diagnostics.solver_status,
            optimality_proven=value.diagnostics.optimality_proven,
            unsatisfied_constraints=value.diagnostics.unsatisfied_constraints,
            summary_message=value.summary.summary_message)
        self.session.add(row)
        self.session.flush()
        for day in value.days:
            low, high = bounds(day.day_total_cost)
            daily = ItineraryDayRecord(id=uuid4(), request_id=request_id, itinerary_id=row.itinerary_id,
                day=day.day, date=day.date, day_cost_min=low, day_cost_max=high, price_status=day.price_status)
            self.session.add(daily)
            self.session.flush()
            for seq, activity in enumerate(day.activities, 1):
                low, high = bounds(activity.estimated_total_cost)
                self.session.add(ItineraryActivityRecord(id=uuid4(), request_id=request_id,
                    itinerary_day_id=daily.id, seq=seq, place_id=activity.place_id,
                    arrival_time=time.fromisoformat(activity.arrival_time),
                    start_time=time.fromisoformat(activity.start_time),
                    departure_time=time.fromisoformat(activity.departure_time),
                    travel_minutes_from_previous=activity.travel_minutes_from_previous,
                    cost_min=low, cost_max=high, price_status=activity.price_status))
        for place in value.dropped_places:
            self.session.add(ItineraryDroppedPlaceRecord(id=uuid4(), request_id=request_id,
                itinerary_id=row.itinerary_id, place_id=place.place_id, reason=place.reason))
        for suggestion in value.relaxation_suggestions:
            # These NOT NULL values must be provided by the engine, never invented.
            self.session.add(RelaxationSuggestionRecord(id=uuid4(), request_id=request_id,
                itinerary_id=row.itinerary_id, constraint_type=suggestion.constraint_type,
                description=suggestion.description, payload=suggestion.payload))
        self.session.flush()
        return row

    def validation(self, request_id: UUID, artifact, itinerary_id: UUID, value):
        request = self.request(request_id)
        if value.trip_id != request.trip_id:
            raise ApplicationError('planning_input_inconsistent', 'Validation trip differs')
        self.get_itinerary(request_id, itinerary_id)
        row = ValidationResultRecord(validation_result_id=artifact.artifact_id,
            request_id=request_id, itinerary_id=itinerary_id, trip_id=value.trip_id,
            parent_artifact_id=artifact.parent_artifact_id, schema_version=value.schema_version,
            is_valid=value.is_valid, suggested_action=value.suggested_action,
            checked_rules=value.checked_rules, recomputed=value.recomputed.model_dump(mode='json'))
        self.session.add(row)
        self.session.flush()
        for kind, issues in [('violation', value.violations), ('warning', value.warnings)]:
            for issue in issues:
                limit = issue.expected if issue.expected is not None else issue.limit
                if limit is None:
                    limit = issue.deadline if issue.deadline is not None else issue.target
                self.session.add(ValidationIssueRecord(id=uuid4(), request_id=request_id,
                    validation_result_id=row.validation_result_id, kind=kind, severity=issue.severity,
                    rule=issue.rule, type=issue.type, day=issue.day, place_id=issue.place_id,
                    actual=None if issue.actual is None else str(issue.actual),
                    expected_or_limit=None if limit is None else str(limit), message=issue.message))
        self.session.flush()
        return row

    def get_itinerary(self, request_id: UUID, itinerary_id: UUID):
        self.request(request_id)
        row = self.session.scalar(select(ItineraryRecord).where(
            ItineraryRecord.request_id == request_id, ItineraryRecord.itinerary_id == itinerary_id))
        if row is None:
            raise ApplicationError('not_found', 'Itinerary not found')
        return row
