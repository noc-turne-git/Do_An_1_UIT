from uuid import uuid4

from sqlalchemy.dialects.postgresql import insert

from app.db.models import PlaceRecord, RequestPlaceCandidateRecord
from app.repositories.workflows import OwnedRepository


class PlaceRepository(OwnedRepository):
    def save_candidates(self, request_id, places):
        self.request(request_id, lock=True)
        for p in places:
            facts = dict(place_id=p.place_id, google_place_id=p.google_place_id, name=p.name,
                category=p.category, types=p.types, google_maps_url=p.google_maps_url,
                rating=p.rating, user_rating_count=p.user_rating_count, business_status=p.business_status,
                latitude=p.location.latitude, longitude=p.location.longitude, address=p.location.address,
                timezone=p.opening_hours.timezone, reservation_required=p.constraints.reservation_required,
                accessibility_notes=p.constraints.accessibility_notes, source=p.data_quality.source,
                opening_hours_verified=p.data_quality.opening_hours_verified,
                last_verified_at=p.data_quality.last_verified_at,
                opening_hours=p.opening_hours.model_dump(mode='json'),
                photos=[photo.model_dump(mode='json') for photo in p.photos],
                visit_duration=p.visit_duration.model_dump(mode='json'))
            stmt = insert(PlaceRecord).values(**facts)
            self.session.execute(stmt.on_conflict_do_update(index_elements=['place_id'],
                set_={k: getattr(stmt.excluded, k) for k in facts if k != 'place_id'}))
            values = dict(id=uuid4(), request_id=request_id, place_id=p.place_id,
                schema_version=p.schema_version, score_places=p.suitability.score_places,
                matched_interests=p.suitability.matched_interests, reason=p.suitability.reason,
                cluster_id=p.cluster_id, source_type=p.source.type, original_name=p.source.original_name)
            stmt = insert(RequestPlaceCandidateRecord).values(**values)
            self.session.execute(stmt.on_conflict_do_update(index_elements=['request_id', 'place_id'],
                set_={k: getattr(stmt.excluded, k) for k in values if k not in ('id', 'request_id', 'place_id')}))
        self.session.flush()

    def save_costs(self, request_id, costs):
        from sqlalchemy import select
        from app.core.errors import ApplicationError
        self.request(request_id, lock=True)
        for cost in costs.places:
            row = self.session.scalar(select(RequestPlaceCandidateRecord).where(
                RequestPlaceCandidateRecord.request_id == request_id,
                RequestPlaceCandidateRecord.place_id == cost.place_id))
            if row is None:
                raise ApplicationError('planning_input_inconsistent', 'Cost has no candidate')
            row.price_min = cost.estimated_total_cost.min if cost.estimated_total_cost else None
            row.price_max = cost.estimated_total_cost.max if cost.estimated_total_cost else None
            row.price_status = cost.price_status
            row.price_confidence_score = cost.price_confidence_score
            row.admission_price_raw = cost.admission_price_raw
        self.session.flush()
