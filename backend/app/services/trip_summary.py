"""Render collected requirements without another provider call."""
from shared.contracts import TripRequest


def trip_details(request: TripRequest) -> dict:
    return request.model_dump(mode='json', exclude={'meta', 'missing_fields'})


def summarize_trip(request: TripRequest) -> str:
    def value(path, item):
        if item is not None:
            return str(item)
        return {'AI_DECIDE': 'Để AI đề xuất', 'FLEXIBLE': 'Linh hoạt',
                'NO_PREFERENCE': 'Không có ưu tiên'}.get(
                    request.meta.field_decisions.get(path), 'Chưa xác định')

    def items(path, values):
        return ', '.join(values) if values else value(path, None)

    def date_value(path, day):
        return day.strftime('%d/%m/%Y') if day else value(path, None)

    destination = request.destination
    budget = request.budget
    preferences = request.preferences
    lines = ['Mình đã có đủ thông tin. Đây là tóm tắt chuyến đi của bạn:',
        f"• Điểm đến: {value('destination.city', destination.city or destination.province or destination.country)}.",
        f"• Thời gian: {date_value('trip.start_date', request.trip.start_date)} – {date_value('trip.end_date', request.trip.end_date)}"
        + (f' ({request.trip.duration_days} ngày).' if request.trip.duration_days else '.'),
        f'• Thành viên: {request.travelers.adults} người lớn, {request.travelers.children} trẻ em.',
        f"• Ngân sách: {format(budget.amount, ',').replace(',', '.' ) + ' ' + budget.currency if budget.amount is not None else value('budget.amount', None)}; phạm vi: {value('budget.scope', budget.scope)}.",
        f"• Sở thích: {items('preferences.interests', preferences.interests)}.",
        f"• Nhịp độ: {value('preferences.pace', preferences.pace)}.",
        f"• Di chuyển: {items('preferences.transport_modes', preferences.transport_modes)}."]
    for label, values in [('Ngân sách bao gồm', budget.includes), ('Không bao gồm', budget.excludes),
                          ('Điểm muốn ghé', destination.must_visit), ('Điểm cần tránh', destination.avoid_places),
                          ('Hoạt động muốn làm', request.must_do),
                          ('Yêu cầu thêm', [c.description for c in request.additional_constraints])]:
        if values:
            lines.append(f"• {label}: {', '.join(values)}.")
    for day in request.daily_preferences:
        details = []
        if day.activity_start:
            details.append(f'bắt đầu {day.activity_start}')
        if day.activity_end:
            details.append(f'kết thúc {day.activity_end}')
        if day.return_by:
            details.append(f'về trước {day.return_by}')
        if day.min_activities is not None:
            details.append(f'tối thiểu {day.min_activities} điểm')
        if day.max_activities is not None:
            details.append(f'tối đa {day.max_activities} điểm')
        if details:
            lines.append(f"• Ngày {day.day}: {', '.join(details)}.")
    lines.append('Bạn kiểm tra lại giúp mình nhé. Nếu muốn điều chỉnh, bạn có thể nhắn thêm.')
    return '\n'.join(lines)
