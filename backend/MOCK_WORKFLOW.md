# Orchestrator Skeleton và Mock Integration

Theo `docs/Cấu trúc schema.md`, mục 9.2–9.5. Đây là demo Development/Mock: không gọi LLM, Google Places hay solver; Validator không thực thi 14 quy tắc nghiệp vụ. `checked_rules` trong kết quả là dữ liệu fixture, không chứng minh các quy tắc đã được chạy.

## Thành phần

- `app/services/orchestrator.py`: gọi đủ 9 Protocol theo thứ tự, Pydantic kiểm output trước khi truyền tiếp; `StateMachine` quản lý trạng thái, câu hỏi, lỗi và checkpoint.
- `app/services/mock_workflow.py`: 8 adapter mock; Constraint Planner dùng `DeterministicConstraintPlanner` thật. Thay từng field của `Components` bằng implementation đúng Protocol để mở rộng.
- `app/api/dev_workflows.py`: `POST /api/v1/dev/workflows/mock-run`, tag **Development/Mock** trong OpenAPI.
- `tests/test_mock_workflow.py`: kiểm thử cả workflow và API, không cần mạng hoặc DB.

Luồng: Request Parser → Agent A → Constraint Planner → Agent B → Budget C → Mock Builder → Mock Engine → Mock Validator → Mock Explainer.

Mỗi output được serialize và validate lại để cả model tạo bằng `model_construct`/`model_copy` cũng không bỏ qua validation. Bước sai schema không được ghi completed hoặc lưu artifact; lỗi có step/code/message/retryable. Exception không dự kiến chỉ trả tên loại, không đưa nội dung exception có thể chứa bí mật ra response. Cancellation không bị bắt thành lỗi workflow.

Artifacts là snapshot JSON có UUID riêng; state giữ tham chiếu bản mới nhất. Retry lưu PlanningInput với seed mới, không ghi đè artifact cũ. `checkpoints` giúp kiểm tra trạng thái khi vào/ra từng bước. Dữ liệu chỉ nằm trong response/bộ nhớ mỗi lần chạy, chưa ghi PostgreSQL và chưa có API lưu/khôi phục phiên.

## State và điểm dừng

| Điều kiện | Trạng thái |
|---|---|
| Parser đang chạy | parsing |
| Thiếu trường hoặc Agent A cần chọn/đổi điểm đến | clarifying, trả pending_fields/questions và dừng |
| Agent A đến Engine đang chạy | planning |
| Validator/Explainer đang chạy | validating |
| Có phương án nới lỏng và suggested_action=ask_user | awaiting_relaxation, dừng, không tự đổi ràng buộc |
| feasible, is_valid=true, suggested_action=accept và giải thích thành công | completed |
| Lỗi schema/module, bị từ chối hoặc hết retry | failed |

Infeasible/partial không thể completed dù mock Validator bị cấu hình accept. `fail` từ Validator có ưu tiên hơn nhánh hỏi nới lỏng. Không có phương án nới thì failed. `final_result` chỉ có khi completed; lịch trình bị từ chối vẫn xem được trong artifacts.

`retry_count` chỉ đếm chạy lại Engine do replan. Giới hạn từ `PlanningInput.solver_config.max_retries`; seed = seed gốc + retry_count. Mỗi lần Engine/Validator tạo một Attempt gồm seed, time limit, kết quả, violations và IDs. Lỗi Engine/Validator cũng tạo Attempt error. Không tự retry lỗi kỹ thuật hoặc output mock sai schema; retry ở provider/LLM chưa nằm trong demo này.

Python API `Orchestrator.run(updated_request, current_date=..., previous=previous_run, answer_raw=...)` cho phép tiếp tục khi có câu trả lời rõ ràng. Nếu chưa có answer thì giữ nguyên trạng thái chờ, không gọi module. Mock Parser đọc TripRequest có cấu trúc từ context, không hiểu câu trả lời ngôn ngữ tự nhiên. Caller phải cung cấp request đã cập nhật; field đã trả lời được ghi source=user. Null với source=user được ghi declared_unknown_fields và không bị hỏi lại. answers_history chỉ ghi vòng clarification, không tăng vòng clarification khi chọn nới lỏng.

Tối đa 3 lượt hỏi chung cho Parser và Agent A, theo mục 9.2 (ưu tiên hơn giới hạn riêng mâu thuẫn trong phần Agent A). Sau lượt 3 chỉ áp `clarification_defaults` được caller cấu hình tường minh, ghi source=default, kiểm Pydantic lại; không có default thì failed. Không tự chọn thành phố đầu tiên. Bản skeleton chạy lại toàn bộ downstream khi resume, tạo IDs mới và giữ artifacts cũ; chưa tối ưu tái sử dụng theo mục 9.4. Không có endpoint resume/relaxation trong demo một lần chạy.

## Phạm vi fixtures

Đường chạy thành công mẫu dùng nguyên `fixtures/trip_request.json`: Đà Lạt, 14–16/11/2026, p001/p002/p003, VND. Parser giữ input có cấu trúc; Agent A/B và Budget trả dữ liệu catalog cố định. Builder nối dữ liệu B/C theo place_id, giữ TimeConstraints thật, chỉ resolve endpoint null thành `hotel` và dùng ma trận mock cố định. Engine trả lịch trình viết tay, `objective_value=null`, `optimality_proven=false`, cảnh báo MOCK. Explainer trả chính summary_message.

Engine từ chối bằng `mock_fixture_unsupported` nếu ngày, ràng buộc thời gian hoặc danh sách địa điểm khác mẫu; Destination/Budget từ chối thành phố explicit hoặc tiền tệ ngoài fixture. Các request khác vẫn qua validation và trả state/lỗi có cấu trúc. Mock Validator có thể accept ngân sách hoặc sở thích khác vì chỉ trả fixture; không dùng kết quả demo để quyết định chuyến đi thật. Không có bảo đảm khả thi nghiệp vụ cho input tùy ý.

## Chạy API và test

Từ root repository, PowerShell (cài venv/dependencies theo README nếu chưa có):

```powershell
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Trong terminal khác tại `backend`:

```powershell
$body = Get-Content -Raw -Encoding UTF8 fixtures/trip_request.json
$response = Invoke-RestMethod -Uri http://127.0.0.1:8000/api/v1/dev/workflows/mock-run -Method Post -ContentType 'application/json; charset=utf-8' -Body ([System.Text.Encoding]::UTF8.GetBytes($body))
$response.state
$response.final_result
$response.artifacts
.\.venv\Scripts\python.exe -m pytest tests/test_mock_workflow.py -q
.\.venv\Scripts\python.exe -m pytest -q -rs
```

Swagger tại `http://127.0.0.1:8000/docs`, nhóm Development/Mock. HTTP 200 trả kết quả workflow kể cả clarifying/failed; HTTP 422 khi body không đúng TripRequest. Response gồm mode/notice, state, artifacts, checkpoints, final_result và explanation. Endpoint demo hiện được đăng ký mặc định, không có authentication hoặc environment gate; chỉ chạy local/dev.

## Kết quả test thực tế

Ngày 02/11/2026: toàn bộ backend **116 passed, 2 skipped, 1 warning**. Trong đó có **29 tests mới** (bao gồm parametrization) kiểm workflow/API, đủ 10 nhóm trường hợp yêu cầu, thêm resume, unknown, defaults, giới hạn hỏi lại, thay seed, IDs bất biến và lỗi Engine.

Hai test PostgreSQL skip vì không cấu hình DATABASE_URL/TEST_DATABASE_URL. Warning hiện hữu của Starlette TestClient về httpx. Chưa xác minh DB server, provider thật, tối ưu hóa hoặc 14 quy tắc Validator trong lần chạy này.
