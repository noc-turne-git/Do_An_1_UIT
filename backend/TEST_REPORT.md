# Full Backend Testing — Multi-Agent Travel Planner

Ngày kiểm thử: **02/11/2026 (Asia/Saigon)**. Phạm vi: mã nguồn backend hiện tại; không sửa Frontend, không gọi LLM/Places/maps/provider thật, không migration/reset dữ liệu thật.

## 1. Kết luận và bằng chứng thực thi

**Chưa đạt để tích hợp Agent thật như một hệ thống lập lịch hoàn chỉnh.** Kết quả cuối: **212 passed, 2 failed, 2 skipped, 1 warning; 216 test cases**. Hai skipped được phân loại **BLOCKED** về mặt QA vì thiếu PostgreSQL test database. Hai failed được giữ nguyên, không xóa hoặc xfail để làm xanh suite.

Báo cáo máy đọc được: [pytest-results.xml](pytest-results.xml). Tên test, thời gian, traceback hai failures và lý do skips nằm trong XML. Đây là bằng chứng của lần chạy cuối; không dùng số liệu lịch sử trong README làm kết quả hiện tại.

Các lệnh thực sự chạy từ `backend/`:

```powershell
.venv/Scripts/python.exe -m pytest -q -rs --tb=short --junitxml=pytest-results.xml
.venv/Scripts/python.exe -m compileall -q app alembic fixtures tests
.venv/Scripts/python.exe -m pip check
.venv/Scripts/python.exe -m pip list --format=freeze
```

Kết quả pytest cuối, exit code **1**:

```text
FAILED tests/test_full_backend.py::test_planning_coordinates_reject_out_of_range
FAILED tests/test_full_backend.py::test_itinerary_status_agrees_with_solver_diagnostics
2 failed, 212 passed, 2 skipped, 1 warning in 2.27s
```

Compile: exit 0. `pip check`: exit 0, `No broken requirements found.` Một tiến trình Python mới import thành công **22 modules app** theo thứ tự tên đảo ngược; không phát hiện circular import trong các đường import đã chạy. Alembic offline SQL generation chạy qua pytest, không kết nối server.

Lịch sử kiểm thử: baseline **116 passed, 2 skipped**. Bổ sung **98 cases**, sửa lỗi điều phối ID, chạy lại; sau đó giữ thêm hai regression failures về hợp đồng chưa được chốt. Lần chạy đầu của test mới cũng phát hiện lỗi trong test harness: chặn socketpair loopback khiến Windows asyncio không khởi động. Đã sửa guard để cho phép loopback cần cho asyncio, vẫn chặn kết nối bên ngoài; đây không phải bug backend. Không tính các lỗi harness đã sửa vào kết quả cuối.

## 2. Đầu vào, môi trường, dependencies

- Đã đọc source `backend/app/`, migrations, generator/JSON fixtures, cấu hình, tài liệu backend và các tests hiện hữu. Không đọc toàn bộ thư viện bên thứ ba trong `.venv` như source dự án.
- **Không tồn tại `docs/multi_agent_travel_schema.md`.** Đã dùng `docs/Cấu trúc schema.md` là tài liệu mà source hiện tham chiếu, đối chiếu thêm `docs/Backend_ERD.md`, `backend/PLANNING_CONTRACTS.md`, `backend/MOCK_WORKFLOW.md`. Chưa thể xác nhận tương thích với một phiên bản tài liệu khác mang tên được yêu cầu.
- Python **3.13.5** đáp ứng yêu cầu >=3.11. Môi trường `.venv` đã có dependencies, không cần cài thêm.
- Các bản chính: FastAPI 0.162.0, Starlette 1.10.0, Pydantic 2.14.2, pydantic-settings 2.16.2, SQLAlchemy 2.0.55, Alembic 1.20.1, psycopg 3.3.6, pytest 9.2.0, httpx 0.28.1, tzdata 2026.6. Phạm vi dependencies thỏa `pyproject.toml`; chưa có lockfile Python đảm bảo tái lập chính xác.
- Không có `backend/.env`; `DATABASE_URL` và `TEST_DATABASE_URL` trong process đều chưa cấu hình. `.env.example` chỉ có URL placeholder được comment. Không in secret hoặc tự tìm credential.
- Warning còn lại: Starlette deprecate TestClient dùng httpx. Hiện TestClient vẫn chạy; cần xử lý tương thích thư viện riêng, không tự nâng dependency trong đợt QA này.
- Chạy ở repository root không chỉ định `-c` làm pytest không nhận marker `postgres` từ cấu hình backend; lần chạy cuối dùng cwd `backend/` nên không còn hai UnknownMark warnings này.

## 3. Module và kết quả

| Test module | PASS | FAIL | SKIP/BLOCKED | Phạm vi |
| --- | ---: | ---: | ---: | --- |
| `tests/test_basic.py` | 7 | 0 | 0 | Health, config, CORS, exception handlers, mock LLM |
| `tests/test_database.py` | 1 | 0 | 2 | Không cấu hình DB; connection/migration live bị chặn |
| `tests/test_planning_contracts.py` | 79 | 0 | 0 | Models, fixtures, planner, cross-field constraints |
| `tests/test_mock_workflow.py` | 29 | 0 | 0 | Workflow/API, clarification, retry, artifacts |
| `tests/test_full_backend.py` | 96 | 2 | 0 | Bổ sung 9 contracts, nested limits, từng interface/boundary, API, ORM, offline Alembic |
| **Tổng** | **212** | **2** | **2** | **216 cases** |

### Pydantic models — PASS với hai khoảng trống nêu ở mục 5

Đã kiểm cả **TripRequest, DestinationResult, PlaceCandidate, CostedPlaceCandidate, TimeConstraints, PlanningInput, Itinerary, ValidationResult, WorkflowState**: input hợp lệ, missing required, null không hợp lệ, extra fields, major version sai, JSON roundtrip. Trường nullable được kiểm riêng theo điều kiện (ví dụ selected_region chỉ null khi chưa chọn; budget null không thành 0). Optional mặc định như endpoints và các wrapper được dùng trong fixtures/workflow.

Kiểm nested models, enum và case, kiểu tiền/phút strict (không nhận bool/string/float), is_hard strict, confidence finite và [0,1], rating/tọa độ PlaceCandidate, timezone IANA, datetime có offset và thứ tự theo thời gian tuyệt đối, duration/date inclusive. Kiểm giá UNKNOWN/ESTIMATED/VERIFIED_FREE, min/target/max, soft target, thời lượng ăn/tham quan, matrix vuông/unit/mode/order/unique IDs/endpoints, must/avoid, 14 rule names và severity, câu hỏi chỉ thuộc pending_fields, tối đa ba clarification rounds.

Model validation **không chứng minh** 14 business rules thực sự được chạy. Các trường enum chưa được tài liệu liệt kê đầy đủ vẫn là str theo implementation; không tự đặt một tập enum mới để test.

### Constraint Planner — PASS

Một ngày và nhiều ngày; suy duration từ ngày; daily override so với global preferences; nguồn user/default/inferred và confidence; default phải được caller cấu hình/cho phép; thiếu source; null đã khai chưa biết không bị hỏi lại; missing dates; activity window, count, pace, transport, rest, meal; return_by và ưu tiên hard boundary; conflict time/count/rest/required meal; optional meal không vừa thì bỏ; endpoints vẫn null chờ Builder. Kết quả lặp lại bằng nhau, request/defaults không bị sửa, async interface tương thích. Không gọi LLM.

### Database — PASS offline / BLOCKED live

PASS: SQLAlchemy mapper configuration, ba bảng, PK/FK metadata, relationships hai chiều, check/unique constraints metadata, PostgreSQL DDL compilation, optimistic revision metadata; repository add/get/flush không tự commit; session dùng transaction context và dọn tài nguyên ở đường thành công/lỗi; thiếu config trả ApplicationError; OperationalError giả lập không bị nuốt; URL PostgreSQL được chuẩn hóa driver; Alembic offline SQL có tables/JSONB/FKs/checks/immutable trigger.

**Các phép kiểm session/repository dùng mock và metadata không chứng minh commit/rollback thật.** Chưa chạy PostgreSQL live connection, upgrade/downgrade, metadata check trên server, CRUD/rollback/FK/check/trigger thực tế. Hai integration tests skip vì thiếu URL, được báo **BLOCKED**, không báo PASS.

Đã mở rộng nhánh migration test sẵn có để khi có DB test riêng sẽ kiểm ORM create/read/update/delete, JSONB roundtrip, tăng revision, rollback thật, duplicate PK, missing FK, revision sai, artifact kind sai, trigger từ chối UPDATE/DELETE. Nhánh mới này **chưa thực thi trên server**. Test chỉ migration khi TEST_DATABASE_URL được cung cấp và DB không có bảng; cleanup chỉ sau upgrade thành công. Chưa chứng minh concurrent writer/stale update trên DB thật.

### FastAPI, environment, interfaces — PASS trong TestClient

Startup/shutdown lifespan, dispose engine, health 200, demo success/clarifying/failed, response WorkflowRun roundtrip, malformed/missing/null/list body 422 và error envelope; 404/405/400/503/500 handlers; exception không lộ nội dung RuntimeError; allowed/denied CORS và OPTIONS preflight; env ưu tiên dotenv; secret masking; config sai bị từ chối. HTTP 200 với state failed là hợp đồng hiện có của demo, không có nghĩa chuyến đi lập thành công. Health chỉ liveness, không phải DB readiness.

Đủ chín Protocol được đối chiếu chữ ký async và gọi qua mock workflow; có thể thay component bằng adapter độc lập cùng interface. Kiểm output schema tại từng boundary, cả model_copy có dữ liệu sai; data forwarding; exception ở cả chín bước không gọi bước sau; cancellation truyền ra. Test mới chặn socket connect bên ngoài, TestClient dùng ASGI trong process; loopback được phép để Windows tạo socketpair. Không kiểm endpoint HTTP qua một uvicorn process riêng, tải đồng thời, hiệu năng hay provider thật.

## 4. Ma trận End-to-End bắt buộc

| # | Kịch bản | Kết quả | Bằng chứng/hành vi |
| --- | --- | --- | --- |
| 1 | Happy path | PASS | completed, đủ thứ tự 9 bước, final_result và explanation |
| 2 | Request thiếu dữ liệu | PASS | clarifying, pending fields/questions; không gọi Agent A |
| 3 | Agent A yêu cầu chọn điểm đến | PASS | pending destination.city; không gọi Planner |
| 4 | Agent output sai schema | PASS | parameterized đủ 9 bước; output_schema_invalid; không ghi completed cho bước lỗi |
| 5 | Planner nhận constraint không hợp lệ | PASS | start 13:00 sau end/return_by 12:00: failed tại constraint_planner, không gọi Agent B |
| 6 | Mock Agent exception | PASS | exception tại từng bước được ghi state; không gọi downstream; không lộ sentinel bí mật |
| 7 | Engine infeasible | PASS | failed hoặc awaiting_relaxation khi có gợi ý; không completed |
| 8 | Validator is_valid=false | PASS | fail/replan/ask_user theo action; không Explainer khi chưa accept |
| 9 | Retry vượt giới hạn | PASS | 1 lần đầu + 3 retries, seeds 42–45; retry_exhausted, giữ attempts/artifacts |
| 10 | Nhiều ngày khác constraints | PASS theo phạm vi | Fixture 3 ngày hoàn tất; thêm daily override ngày 3 được giữ nguyên qua Builder, mock Engine từ chối input ngoài fixture. Không chứng minh solver tùy ý hoạt động |
| 11 | place_id không đồng nhất | PASS tại B/C/Builder | ID cost khác place: planning_input_inconsistent, không gọi Engine; ID thiếu/duplicate trong PlanningInput bị từ chối |
| 12 | Completed có đủ artifacts | PASS | 8 snapshots, refs duy nhất, roundtrip state/run, snapshot độc lập final_result |

Kiểm thêm: resume cần answer; không sửa previous run; answers_history, resolved/unknown fields; defaults sau ba vòng; không tự chọn thành phố; replan rồi accept; Engine error không completed dù mock Validator accept; IDs Engine/Builder/Validator sai phải dừng trước lưu artifact. place_id do Engine tự bịa chỉ có Validator thật mới xác minh đầy đủ theo input_integrity; mock Validator không làm việc đó.

## 5. Bugs và xử lý

### Đã sửa — kiểm trip_id quá muộn trong Orchestrator

Engine có thể trả Itinerary hợp lệ về shape nhưng thuộc trip khác. Trước sửa: được lưu artifact, ghi completed và gọi Validator rồi mới phát hiện. Đã tái hiện failure `Expected mock to not have been awaited. Awaited 1 times.`

Sửa `app/services/orchestrator.py`: kiểm ID ngay sau validate output và trước `save()`, áp cho Builder, Engine và Validator. Builder phải giữ trip ID đã được Orchestrator truyền; Engine/Validator phải giữ active PlanningInput.trip_id. Output sai không được lưu/đánh completed/chuyển bước. Ba regression cases PASS sau sửa. Không thay model/schema hay thuật toán lập lịch.

Sửa nhỏ cấu hình: thêm `path_separator = os` trong alembic.ini để loại legacy path parsing warning; offline SQL test PASS.

### Còn FAIL — QA-CONTRACT-01: PlanningPlace bỏ giới hạn tọa độ

`PlaceCandidate.location.latitude` giới hạn [-90,90], nhưng `PlanningInput.candidate_places[].latitude` là float không giới hạn. Probe thực chạy cho latitude=999 vẫn được chấp nhận; test `test_planning_coordinates_reject_out_of_range` FAIL với `DID NOT RAISE ValidationError`.

Rủi ro: dữ liệu qua adapter/Builder khác có thể không còn hợp lệ dù PlanningInput validate thành công. Cần chốt liệu Pydantic phải bảo toàn miền tọa độ của PlaceCandidate hay Validator input_integrity phải từ chối. Đề xuất dùng cùng giới hạn latitude/longitude tại boundary PlanningInput và bổ sung cả longitude. **Chưa tự sửa ràng buộc trong schema contracts.** Test ghi lại kỳ vọng QA; đây không phải yêu cầu đã được implement.

### Còn FAIL — QA-CONTRACT-02: hai trạng thái Itinerary mâu thuẫn

`status=feasible` cùng `diagnostics.solver_status=infeasible` vẫn được Itinerary chấp nhận. Probe tái hiện được; `test_itinerary_status_agrees_with_solver_diagnostics` FAIL với `DID NOT RAISE ValidationError`. Tài liệu yêu cầu solver_status phản ánh trạng thái thật, nhưng chưa quy định rõ tầng nào bắt buộc so sánh hai trường. Orchestrator hiện quyết định theo status, còn Validator mock không kiểm mâu thuẫn.

Đề xuất chốt invariant hai trường giống nhau và tầng chịu trách nhiệm, sau đó thêm cross-field validation hoặc từ chối ở input_integrity trước accept. **Chưa tự thêm quy tắc vào contract.** Không lấy mock Validator accept làm bằng chứng hợp lệ nghiệp vụ.

### Quan sát cần thiết kế, không kết luận thành bug đã định nghĩa

TripRequest nhận children=2 và children_ages=[]; probe xác nhận. Chưa rõ tuổi có bắt buộc đủ cho tất cả trẻ hay có thể chưa biết, nên không áp quy tắc children==len(children_ages). Cần quyết định trước tính giá theo tuổi. Không tự cấm đoàn 0 người, empty strings/lists hoặc tạo enum chưa có đặc tả.

## 6. Chưa triển khai/chưa thể chứng minh

- Request Parser không hiểu ngôn ngữ tự nhiên; nhận structured request từ context. Agent A/B, Budget, Builder, Engine, Validator, Explainer đang mock. Chưa có LLM adapter thực, Places/pricing/maps, DBSCAN, TOPTW/OR-Tools/ALNS.
- Validator chưa thực thi độc lập 14 rules, recompute summary, giá và budget, giờ mở cửa/meal/route/rest/must-visit; checked_rules chỉ fixture. Ngân sách tùy ý hoặc lịch trình có place ID sai không được bảo đảm phát hiện bởi demo.
- Chưa có persistence từ Orchestrator xuống database, endpoint resume/relaxation, tái sử dụng downstream artifacts theo dependency graph, kiểm quyền sở hữu IDs và ghi checkpoint/artifact nguyên tử.
- Chưa có provider timeout/backoff/retry, kiểm factual explanation và fallback theo schema; hiện Explainer exception làm workflow failed.
- Demo endpoint đăng ký mặc định, chưa auth/environment gate. Chưa có ownership, retention, redaction toàn bộ user data; không đánh giá production security hoàn chỉnh trong đợt này.
- PostgreSQL thật, network DB error thật, concurrency, hiệu năng/load và deployment ngoài TestClient: **BLOCKED hoặc chưa thuộc implementation hiện tại**, không suy từ unit mocks thành PASS.

## 7. Điểm chưa thống nhất với tài liệu

1. Tên file schema yêu cầu không tồn tại; nguồn thực tế là `Cấu trúc schema.md`.
2. Agent A có destination_round tối đa 2/chọn mặc định ứng viên đầu, mục 9.2 có chung ba clarification rounds. Code dùng ba vòng chung và không tự chọn điểm đến. Cần chốt policy.
3. `selection_status` được liệt kê khác nhau giữa các phần; code nhận needs_more_info theo phần sau, không dùng pending_fields làm enum.
4. Mục 3 nói user → hard, ví dụ lại có pace/transport user mềm; code theo field_sources, target luôn soft. Daily field source dùng index 0-based (`daily_preferences.0.*`); tài liệu chưa định nghĩa đường dẫn này.
5. Không có bảng pace/default/meal policy chính thức; cấu hình fixture không phải chính sách production. Cần xác nhận xử lý soft end sớm hơn hard return_by và required meal vượt soft window.
6. Mục 7 tính chặng về/chi phí di chuyển, 8.5 dùng cách cộng khác; fixture theo 8.5. Không có solver thật để giải quyết mâu thuẫn.
7. checked_rules ví dụ `day_window`, bảng 8.4 dùng `day_start_window`/`day_end_window`; contract theo bảng 14 rules. Các ví dụ JSONC lỗi cú pháp, ma trận 3 locations nhưng 6×6, totals và excludes=[null] không dùng làm dữ liệu hợp lệ.
8. Shape admission_price_raw/relaxation_suggestions và một số enum chưa chốt; giữ opaque/str. UNKNOWN price bị chặn ở PlanningInput, nhưng Builder mock chưa có pipeline ước tính lại/loại và cảnh báo như thiết kế đầy đủ.
9. Hai khoảng trống cross-field/tọa độ ở mục 5 còn mở. README/ERD có đoạn nói chưa có Orchestrator dù skeleton nay đã có; số test cũ trong tài liệu không phải kết quả QA lần này.
10. `weights.normalized=true` theo mục 7.3 nghĩa là chuẩn hóa các đại lượng mục tiêu, **không yêu cầu tổng trọng số bằng 1**; không coi việc các trọng số cộng khác 1 là bug.

## 8. Việc cần hoàn thành trước tích hợp Agent thật

1. Chốt trách nhiệm validate hai contract failures, quy tắc source/hard/soft, clarification, giá, enum và cách tính cost/travel; xử lý hai test FAIL rồi chạy lại toàn suite.
2. Cấp PostgreSQL test database riêng, rỗng và có thể hủy; đặt TEST_DATABASE_URL rồi chạy lại suite/`-m postgres`. Không dùng database dữ liệu thật. Xác minh CRUD/rollback/constraints/trigger/migration/concurrency trên server.
3. Triển khai Builder và Validator thật trước khi tin output Agent/Engine; Validator phải recompute độc lập đủ 14 rules và bắt ID/tổng tiền/route sai.
4. Tích hợp từng provider qua Protocol, validate boundary, bounded technical retries/timeouts, không mutate input; kiểm từng adapter với recorded fixtures trước external integration được cấp phép.
5. Bổ sung persistence/resume nguyên tử, quản lý revision/ownership và ngăn public access vào demo; hoàn thiện Engine và explanation checks/fallback.

**Mức sẵn sàng:** đủ nền tảng để phát triển adapter trong môi trường dev có mock, chưa đủ chứng nhận nghiệp vụ, database hay vận hành production. Hai failures và hai BLOCKED phải được giải quyết/định nghĩa rõ trước khi tuyên bố hệ thống hoạt động đầy đủ.
