"""Pure date arithmetic for parser output; never issues questions or changes budgets.

The caller supplies the purpose of any eventual clarification question. This
module only reports missing, ambiguous and conflicting date information.
"""
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Literal, Mapping

from shared.contracts import TripRequest


DATE_PATHS = frozenset({'trip.start_date', 'trip.end_date', 'trip.duration_days'})
Reason = Literal['missing', 'ambiguous', 'conflicting']


@dataclass(frozen=True)
class DateIssue:
    reason: Reason
    fields: tuple[str, ...]
    detail: str


@dataclass(frozen=True)
class DateNormalization:
    start_date: date | None
    end_date: date | None
    duration_days: int | None
    issues: tuple[DateIssue, ...]
    derived_fields: frozenset[str]

    @property
    def unresolved(self) -> bool:
        return bool(self.issues)

    @property
    def conflicting(self) -> bool:
        return any(issue.reason == 'conflicting' for issue in self.issues)

    def trip_fields(self) -> dict[str, object]:
        return dict(start_date=self.start_date.isoformat() if self.start_date else None,
                    end_date=self.end_date.isoformat() if self.end_date else None,
                    duration_days=self.duration_days)


def _date(value, current_date: date | None) -> date | None:
    if isinstance(value, date) and not isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = date.fromisoformat(value)
        except ValueError:
            pieces = value.strip().split('/')
            if len(pieces) not in {2, 3} or not all(part.isdigit() for part in pieces):
                return None
            try:
                day, month = int(pieces[0]), int(pieces[1])
                if len(pieces) == 3:
                    if len(pieces[2]) != 4:
                        return None
                    parsed = date(int(pieces[2]), month, day)
                elif current_date is not None:
                    year = current_date.year
                    # 29/02 may require more than one rollover.
                    for _ in range(8):
                        try:
                            parsed = date(year, month, day)
                        except ValueError:
                            year += 1
                            continue
                        if parsed >= current_date:
                            break
                        year += 1
                    else:
                        return None
                else:
                    return None
            except ValueError:
                return None
    else:
        return None
    return parsed


def normalize_trip_dates(previous: TripRequest, updates: Mapping[str, object], *,
                         current_date: date | None = None) -> DateNormalization:
    """Normalize the current turn's date edits against an immutable previous request.

    A newly specified end date wins over a stale duration. A newly specified
    duration wins over a stale derived end date. Three conflicting values in
    the same turn remain unresolved. Null/ambiguous date edits are not silently
    re-derived from old values.
    """
    unknown = set(updates) - DATE_PATHS
    if unknown:
        raise ValueError(f'Unknown date update path: {sorted(unknown)}')
    old = previous.trip
    start, end, duration = old.start_date, old.end_date, old.duration_days
    provided = {path for path, value in updates.items() if value is not None}
    blocked = {path for path, value in updates.items() if value is None}
    issues: list[DateIssue] = []
    derived: set[str] = set()

    for path, value in updates.items():
        if value is None:
            if path == 'trip.start_date': start = None
            elif path == 'trip.end_date': end = None
            else: duration = None
            continue
        if path == 'trip.duration_days':
            if type(value) is not int or value < 1:
                issues.append(DateIssue('conflicting', (path,), 'Duration must be a positive integer'))
            else:
                duration = value
            continue
        parsed = _date(value, current_date)
        if parsed is None:
            issues.append(DateIssue('ambiguous', (path,), 'Date is ambiguous, invalid or in the past'))
            blocked.add(path)
        elif current_date is not None and parsed < current_date and not (
                # An established itinerary can be corrected after its travel
                # dates have passed.  Keep that explicit user correction so
                # its range can be re-normalized; ordering/conflict checks
                # below still reject an invalid range.
                old.start_date is not None or old.end_date is not None):
            other = start if path == 'trip.end_date' else end
            if other is not None and ((path == 'trip.end_date' and parsed < other)
                                      or (path == 'trip.start_date' and parsed > other)):
                issues.append(DateIssue('conflicting', (path, 'trip.start_date' if path == 'trip.end_date' else 'trip.end_date'),
                                        'Updated date conflicts with the preserved date'))
            else:
                issues.append(DateIssue('ambiguous', (path,), 'Date is in the past'))
                blocked.add(path)
                parsed = None
        if path == 'trip.start_date': start = parsed
        else: end = parsed

    start_new, end_new, duration_new = (path in provided and path not in blocked
        for path in ('trip.start_date', 'trip.end_date', 'trip.duration_days'))

    def derive_start():
        nonlocal start
        try:
            start = end - timedelta(days=duration - 1)
            derived.add('trip.start_date')
        except (OverflowError, ValueError):
            issues.append(DateIssue('conflicting', ('trip.end_date', 'trip.duration_days'),
                                    'Date range exceeds supported calendar'))

    def derive_end():
        nonlocal end
        try:
            end = start + timedelta(days=duration - 1)
            derived.add('trip.end_date')
        except (OverflowError, ValueError):
            issues.append(DateIssue('conflicting', ('trip.start_date', 'trip.duration_days'),
                                    'Date range exceeds supported calendar'))

    def derive_duration():
        nonlocal duration
        duration = (end - start).days + 1
        derived.add('trip.duration_days')

    if not issues and not blocked:
        if start_new and end_new and duration_new:
            if end < start or duration != (end - start).days + 1:
                issues.append(DateIssue('conflicting', tuple(sorted(DATE_PATHS)),
                                        'Start, end and duration disagree'))
        elif end_new and duration_new and end is not None and duration is not None:
            derive_start()
        elif start_new and duration_new and start is not None and duration is not None:
            if end is not None and previous.meta.field_sources.get('trip.end_date') == 'user':
                if end < start or duration != (end - start).days + 1:
                    issues.append(DateIssue('conflicting', tuple(sorted(DATE_PATHS)),
                                            'New start/duration conflict with preserved user end date'))
            else:
                derive_end()
        elif end_new and start is not None:
            # Preserve the user's explicit end date, including corrections.
            if end >= start:
                derive_duration()
            else:
                issues.append(DateIssue('conflicting', ('trip.start_date', 'trip.end_date'),
                                        'End date precedes the preserved start date'))
        elif start_new and end is not None:
            if end >= start:
                derive_duration()
            elif previous.meta.field_sources.get('trip.end_date') != 'user' and duration is not None:
                derive_end()
            else:
                issues.append(DateIssue('conflicting', ('trip.start_date', 'trip.end_date'),
                                        'New start date follows the preserved end date'))
        elif duration_new and start is not None:
            if end is not None and previous.meta.field_sources.get('trip.end_date') == 'user':
                if previous.meta.field_sources.get('trip.start_date') == 'user':
                    if duration != (end - start).days + 1:
                        issues.append(DateIssue('conflicting', tuple(sorted(DATE_PATHS)),
                                                'New duration conflicts with preserved user dates'))
                else:
                    derive_start()
            else:
                derive_end()
        elif duration_new and end is not None:
            derive_start()
        elif start is not None and end is not None:
            if duration is None or duration != (end - start).days + 1:
                derive_duration()
        elif start is not None and duration is not None and end is None:
            derive_end()
        elif end is not None and duration is not None and start is None:
            derive_start()

    if start is not None and end is not None and end < start and not any(i.reason == 'conflicting' for i in issues):
        issues.append(DateIssue('conflicting', ('trip.start_date', 'trip.end_date'),
                                'End date precedes start date'))
    if start is None and 'trip.start_date' not in blocked and not any('trip.start_date' in i.fields for i in issues):
        issues.append(DateIssue('missing', ('trip.start_date',), 'Start date not supplied'))
    if end is None and 'trip.end_date' not in blocked and not any('trip.end_date' in i.fields for i in issues):
        issues.append(DateIssue('missing', ('trip.end_date',), 'End date or duration not supplied'))
    for path in blocked:
        if not any(path in i.fields for i in issues):
            issues.append(DateIssue('missing', (path,), 'Date information not supplied'))
    return DateNormalization(start, end, duration, tuple(issues), frozenset(derived))
