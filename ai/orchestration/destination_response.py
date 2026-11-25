"""Natural destination confirmation backed by source-aware, canonical facts."""
from typing import Literal

from pydantic import Field
from shared.contracts import Model, NonEmpty, TripRequest

DetailGroup = Literal['destination', 'time', 'travelers', 'budget', 'interests', 'pace', 'transport']
DISPLAY_VALUES = {
    'interests': {'nature': 'thiên nhiên', 'food': 'ẩm thực', 'photography': 'chụp ảnh',
                  'culture': 'văn hóa', 'history': 'lịch sử', 'relaxation': 'nghỉ dưỡng',
                  'adventure': 'khám phá', 'shopping': 'mua sắm'},
    'pace': {'relaxed': 'Thư thả', 'balanced': 'Cân bằng', 'fast': 'Nhiều hoạt động',
             'intensive': 'Nhiều hoạt động'},
    'transport': {'motorbike': 'xe máy', 'car': 'ô tô', 'taxi': 'taxi', 'bus': 'xe buýt',
                  'walking': 'đi bộ', 'walk': 'đi bộ', 'bicycle': 'xe đạp',
                  'public_transport': 'phương tiện công cộng'},
}


class DestinationWording(Model):
    opening: NonEmpty
    summary_intro: NonEmpty
    detail_order: list[DetailGroup] = Field(default_factory=list)


def trip_facts(request: TripRequest) -> dict[str, str]:
    """Do not turn technical defaults or unanswered fields into user wishes."""
    def known(path, value):
        if value is None or request.meta.field_decisions.get(path) == 'DECLINED':
            return False
        source = request.meta.field_sources.get(path)
        return source == 'user' or (source == 'inferred' and path in {
            'trip.duration_days', 'trip.end_date', 'trip.start_date'})

    facts = {}
    d, trip, people, budget, preferences = (
        request.destination, request.trip, request.travelers, request.budget, request.preferences)
    if d.city and d.destination_source in {'USER', 'AGENT_DELEGATED'}:
        facts['destination'] = d.city
    dates = []
    for path, value, label in [('trip.start_date', trip.start_date, 'Từ'),
                               ('trip.end_date', trip.end_date, 'đến')]:
        if known(path, value):
            dates.append(f'{label} {value:%d/%m/%Y}')
    if known('trip.duration_days', trip.duration_days):
        dates.append(f'({trip.duration_days} ngày)' if dates else f'{trip.duration_days} ngày')
    if dates:
        facts['time'] = ' '.join(dates)
    travelers = [f'{value} {label}' for path, value, label in (
        ('travelers.adults', people.adults, 'người lớn'),
        ('travelers.children', people.children, 'trẻ em')) if known(path, value)]
    if travelers:
        facts['travelers'] = ', '.join(travelers)
    if known('budget.amount', budget.amount):
        text = f"{budget.amount:,}".replace(',', '.')
        if known('budget.currency', budget.currency):
            text += ' ' + budget.currency
        if known('budget.scope', budget.scope):
            text += ' — ' + {'total': 'cả nhóm', 'per_person': 'mỗi người',
                            'group': 'cả nhóm', 'whole_trip': 'toàn chuyến đi'}.get(budget.scope, budget.scope)
        facts['budget'] = text
    for key, path, value in [('interests', 'preferences.interests', preferences.interests),
                             ('pace', 'preferences.pace', preferences.pace),
                             ('transport', 'preferences.transport_modes', preferences.transport_modes)]:
        if known(path, value):
            names = DISPLAY_VALUES[key]
            facts[key] = (', '.join(names.get(item, item) for item in value) if value else
                          'Không có ưu tiên') if isinstance(value, list) else names.get(value, value)
    return facts


def render_trip_details(request, detail_order=()):
    labels = dict(destination='📍 **Điểm đến:**', time='📅 **Thời gian:**',
        travelers='👥 **Số người:**', budget='💰 **Ngân sách:**', interests='🌿 **Sở thích:**',
        pace='🚶 **Nhịp độ:**', transport='🚗 **Di chuyển:**')
    facts = trip_facts(request)
    order = list(dict.fromkeys([*detail_order, *labels]))
    return '\n\n'.join(f'{labels[key]} {facts[key]}' for key in order if key in facts)


def render_confirmation(request, result, wording=None):
    city = result.selected_region.city
    if wording is None:
        opening = (f'Mình sẽ lên kế hoạch cho chuyến đi **{city}** mà bạn đã chọn nhé!'
                   if result.destination_source == 'USER' else
                   f'Mình đã chọn **{city}** cho chuyến đi của bạn. {result.selection_reason.strip()}')
        wording = DestinationWording(opening=opening,
            summary_intro='Dưới đây là những thông tin chuyến đi của bạn:')
    return wording.opening + '\n\n' + wording.summary_intro + '\n\n' + render_trip_details(
        request, wording.detail_order)
