"""Compatibility entry points for the shared source-aware trip renderer."""
from ai.orchestration.destination_response import render_trip_details
from shared.contracts import TripRequest


def trip_details(request: TripRequest) -> dict:
    return request.model_dump(mode='json', exclude={'meta', 'missing_fields'})


def summarize_trip(request: TripRequest) -> str:
    return 'Dưới đây là những thông tin chuyến đi của bạn:\n\n' + render_trip_details(request)
