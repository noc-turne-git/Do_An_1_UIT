"""Canonical configuration only: no request state, routing or default application."""
from typing import Annotated, Literal

from pydantic import ConfigDict, Field, StrictInt

from shared.contracts import Model, NonEmpty, QuestionKind


TRIP_NEVER_DEFAULT = frozenset({'trip.start_date', 'trip.end_date', 'travelers.adults'})
DESTINATION_NEVER_DEFAULT = frozenset({'destination.city'})  # explicit destination branch
NEVER_DEFAULT = TRIP_NEVER_DEFAULT | DESTINATION_NEVER_DEFAULT
PREFERENCE_FIELDS = frozenset({'preferences.interests', 'preferences.pace',
                               'preferences.transport_modes'})


class FrozenConfig(Model):
    model_config = ConfigDict(extra='forbid', frozen=True)


class TripRequestDefaults(FrozenConfig):
    """Closed table: never-default and destination fields cannot be configured here.

    Unknown budget remains null outside this default table. Preferences are
    configured separately with explicit owner approval.
    """
    children: Annotated[StrictInt, Field(ge=0, le=0)] = Field(default=0, alias='travelers.children')


class ApprovedPreferenceDefaults(FrozenConfig):
    approved_by: NonEmpty
    interests: Annotated[tuple[NonEmpty, ...], Field(min_length=1)]
    pace: NonEmpty
    transport_modes: Annotated[tuple[NonEmpty, ...], Field(min_length=1)]


class ClarificationPolicy(FrozenConfig):
    max_clarification_rounds: Annotated[StrictInt, Field(ge=0)] = 3
    max_destination_rounds: Annotated[StrictInt, Field(ge=2, le=2)] = 2
    trip_request_defaults: TripRequestDefaults = Field(default_factory=TripRequestDefaults)
    preference_defaults: ApprovedPreferenceDefaults | None = None

    @staticmethod
    def counter_for(kind: QuestionKind) -> Literal['clarification_round', 'destination_round']:
        if kind == 'trip_request':
            return 'clarification_round'
        if kind in {'destination_choice', 'destination_info'}:
            return 'destination_round'
        raise ValueError(f'Unknown question kind: {kind}')

    def limit_for(self, kind: QuestionKind) -> int:
        return (self.max_clarification_rounds if self.counter_for(kind) == 'clarification_round'
                else self.max_destination_rounds)

    @property
    def unconfigured_defaults(self) -> frozenset[str]:
        return PREFERENCE_FIELDS if self.preference_defaults is None else frozenset()

    @property
    def default_table(self) -> dict[str, object]:
        """A fresh export each time; callers cannot mutate shared policy data."""
        table = self.trip_request_defaults.model_dump(mode='json', by_alias=True)
        if self.preference_defaults is not None:
            table.update({f'preferences.{key}': value for key, value in
                self.preference_defaults.model_dump(mode='json', exclude={'approved_by'}).items()})
        return table
