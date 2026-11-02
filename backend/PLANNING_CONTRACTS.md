# Models và Constraint Planner

Nguồn chính: `docs/Cấu trúc schema.md`, đối chiếu các quyết định tương thích trong `docs/Backend_ERD.md`. Mở rộng `app/models/contracts.py` hiện có, dùng nguyên Protocol trong `app/agents/interfaces.py`. Không có schema thay thế, agent thật, Planning Engine, Validator hay endpoint lập lịch trình.

## Chạy

Từ thư mục `backend`:

```powershell
.\.venv\Scripts\python.exe -m pytest -q -rs
.\.venv\Scripts\python.exe fixtures/generate.py
```

Lệnh thứ hai tái tạo fixture minh họa, không gọi mạng. Cài môi trường mới theo README bằng `pip install -e '.[test]'` trước khi chạy.

Kết quả chạy thực tế sau triển khai: **87 passed, 2 skipped, 1 warning**. Hai test PostgreSQL được skip vì chưa cấu hình DATABASE_URL/TEST_DATABASE_URL. Warning hiện hữu của Starlette TestClient về httpx; không có lỗi test. Chưa xác minh PostgreSQL server trong lần chạy này.

## Gọi từ Orchestrator tương lai

```python
import json
from pathlib import Path
from app.models import TripRequest, DestinationResult
from app.services.constraint_planner import (
    DeterministicConstraintPlanner, PlannerDefaults, ConstraintPlanningError,
)

request = TripRequest.model_validate_json(Path('fixtures/trip_request.json').read_text(encoding='utf-8'))
defaults = PlannerDefaults.model_validate_json(Path('fixtures/planner_defaults.json').read_text(encoding='utf-8'))
try:
    constraints = DeterministicConstraintPlanner().plan(request, defaults)
except ConstraintPlanningError as error:
    structured_error = error.as_dict()
```

Cũng có `await planner.build(request, destination, defaults=defaults.model_dump())`, đúng chữ ký Protocol hiện có. Destination không tham gia tính khung thời gian. `plan()` đồng bộ, thuần Python, tái lập và không sửa input.

`ConstraintPlanningError` kế thừa `ApplicationError`, có `code`, `issues`, `pending_fields`, `as_dict()`. Codes từng issue: `missing_required_field`, `unknown_required_value`, `missing_source`, `conflicting_constraints`. Người dùng đã khai chưa biết (`null`, source=user) không bị thêm lại vào pending_fields. Thiếu dữ liệu chạy vẫn báo `unknown_required_value` nếu không có default hợp lệ.

## Quy tắc đã triển khai

- Pydantic v2; extra=forbid; version mặc định 1.0, chỉ nhận major 1; enum đã được liệt kê giữ nguyên case. Các enum chưa có tập giá trị đầy đủ vẫn là `str` theo skeleton.
- Tiền và phút là integer nghiêm ngặt, không âm, không nhận bool/string/float làm tiền. Khoảng min ≤ max. Không nhận NaN/infinity. Không đổi null thành 0.
- Ngày ISO; khoảng ngày bao gồm hai đầu; duration_days nếu có phải khớp khoảng ngày. Arrival/departure phải có timezone và departure không trước arrival. Timezone kiểm bằng IANA; HH:MM được kiểm định dạng.
- Daily preference không trùng day hoặc vượt chuyến đi. TimeConstraints có ngày liên tiếp, bắt đầu day=1. Khung hoạt động start ≤ end; số hoạt động min ≤ target ≤ max; target luôn soft. Thời lượng ăn phải nằm được trong khung bữa ăn; min ≤ typical ≤ max cho visit duration.
- Nguồn inferred trong metadata cần confidence. Visit duration estimated cũng cần confidence. ESTIMATED price cần cost và confidence, UNKNOWN giữ cost=null, VERIFIED_FREE có min=max=0; giá 0 không xác minh bị từ chối.
- PlanningInput giữ hai ma trận đúng unit, thứ tự locations và mode giống nhau; ma trận vuông; candidate IDs duy nhất và có trong ma trận; endpoints được resolve trước khi nhận PlanningInput; must_visit phải tồn tại và không giao avoid. UNKNOWN không được lọt vào PlanningInput.
- DestinationResult kiểm sự nhất quán selected/selected_region, số ứng viên khi needs_user_choice, danh sách rỗng khi no_valid_candidate.
- Activity kiểm arrival ≤ start ≤ departure. ValidationResult kiểm severity; is_valid=true chỉ khi không có violations và đủ 14 rule names theo bảng 8.4. Đây là kiểm hợp đồng, không thực thi 14 quy tắc trên lịch trình.
- WorkflowState giữ đầy đủ artifacts, pending_fields/questions, answers_history, attempts, retry_count, errors. Không quá 3 lượt clarification; câu hỏi chỉ nhắm pending_fields và bao phủ hết khi status=clarifying.
- Planner cần start_date/end_date và tính số ngày bao gồm hai đầu. Daily override ưu tiên hơn preferences toàn chuyến; trường thiếu dùng cấu hình tường minh. return_by là cận trên, lấy sớm hơn activity_end; có thể dùng riêng khi activity_end chưa có.
- Source đọc từ `TripRequest.meta.field_sources`. Dữ liệu user là hard, inferred/default là soft; target luôn soft kể cả user. Có giá trị nhưng thiếu source thì báo lỗi, không tự đoán. Defaults do planner áp luôn soft, input không bị sửa và không thêm field ngoài TimeConstraints để lưu nguồn. Orchestrator có thể truy nguồn từ request + cấu hình đầu vào.
- Các trường preferences thiếu chỉ dùng default khi caller bật `allow_preference_defaults` (đã hết lượt hỏi/đã chấp thuận), hoặc người dùng đã khai chưa biết. Planner không tự tăng clarification_round hay gọi LLM hỏi lại. Ngày bắt đầu/kết thúc không có default trong PlannerDefaults.
- Meal windows lấy từ cấu hình; không có bảng giờ ăn cố định hay suy luận từ interest=food, không tự tạo bữa bắt buộc hoặc chi phí ăn. Chính sách cấu hình hiện tại: optional meal lấy phần giao đủ duration với khung ngày; không đủ thì bỏ. Required meal giữ khả năng vượt biên soft; chỉ báo xung đột khi không đủ duration trong biên hard. Rest cứng vượt độ dài khung ngày cứng cũng báo xung đột. Không đánh giá khả thi tuyến đường/số địa điểm vì chưa có dữ liệu địa điểm ở bước này.
- start_location_id/end_location_id vẫn null sau planner; tên địa điểm không được giả làm ID. Builder tương lai resolve theo quy định tài liệu. additional_constraints và must_do dạng văn bản không được planner diễn giải bằng heuristic.

## Fixtures

JSON riêng cho cả 7 loại được yêu cầu, thêm `time_constraints.json` và `planner_defaults.json`. Cùng chuyến Đà Lạt 14–16/11/2026, 3 ngày, p001/p002/p003, VND, có weekly_schedule và special_hours. `generate.py` viết tay dữ liệu minh họa qua models, không triển khai Builder/Engine/Validator. PlanningInput fixture resolve endpoint bằng `hotel` và dùng ma trận mock 4×4. Tổng giá fixture: 190.000–310.000 VND. Mỗi ngày một hoạt động nên tổng di chuyển giữa các hoạt động bằng 0 theo mục 8.5; chặng đầu mock 10 phút vẫn được giữ riêng trên activity. ValidationResult là mock contract, không phải kết quả chạy Validator thật.

## Những điểm còn mâu thuẫn hoặc chưa rõ

1. Không có bảng pace → giờ/số hoạt động/rest, không có quy tắc chính thức sinh meal_windows, không có daily transport/meal override trong TripRequest. Vì vậy các số mặc định phải được caller truyền; fixture defaults chỉ là minh họa, không phải policy production. Chính sách giao khung bữa ăn nêu trên cần chốt khi bổ sung thiết kế.
2. Tài liệu chưa định nghĩa đường dẫn source cho phần tử array. Quy ước triển khai là `daily_preferences.0.activity_start` (index 0-based trong array), khác với day=1-based. Khi thiếu cả daily record, lỗi chỉ rõ day và đường dẫn `daily_preferences[day=N].field`; không tạo giả một phần tử request.
3. Mục 3 nói giá trị user là hard, nhưng ví dụ pace/transport có is_hard=false. Planner theo quy tắc văn bản và source; chưa có trường riêng để người dùng nói một sở thích user chỉ là soft. Cần bổ sung thiết kế nếu muốn phân biệt ý định đó.
4. Chưa có shape xác định cho admission_price_raw và relaxation_suggestions; giữ dict opaque như skeleton. Danh sách đầy đủ của pace/transport/category/scope/flexibility/constraint.type chưa có; không tự dựng enum đóng.
5. selection_status bảng đầu không có needs_more_info, bảng sau có; giữ enum hiện hữu. destination_round tối đa 2 mâu thuẫn clarification_round chung tối đa 3; chưa triển khai Orchestrator nên không chọn logic mới.
6. Ví dụ checked_rules dùng day_window nhưng bảng 8.4 dùng day_start_window. Model chọn bảng 8.4 khi kiểm đủ 14 rules. Không tự normalize tên.
7. Mục 7 có chi phí/chặng về; mục 8.5 bỏ chi phí di chuyển và chỉ cộng thời gian giữa hoạt động. Fixture theo 8.5, không giải quyết thay Engine/Validator. Trọng số mẫu normalized=true nhưng không tổng bằng 1; không ép tổng khi chưa rõ nghĩa normalized.
8. Giờ mở cửa qua nửa đêm chưa được hỗ trợ bởi Validator theo 8.5; models vẫn giữ dữ liệu nguồn, không tự sửa thành giờ khác. Không ép weekday duy nhất vì một ngày có thể có nhiều khoảng mở cửa.
9. Ví dụ JSONC có syntax lỗi, ma trận sai kích thước, tổng tiền không khớp, excludes=[null]. Fixtures sửa các lỗi đó theo cấu trúc interfaces hiện có. Mọi step contract có schema_version theo mục 10, kể cả ví dụ bỏ qua field.

Các điểm lưu trữ và mâu thuẫn khác vẫn được ghi trong `docs/Backend_ERD.md`.
