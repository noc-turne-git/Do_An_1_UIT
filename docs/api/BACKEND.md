# Travel Planning Backend

Backend Python 3.11+, FastAPI, Pydantic 2, SQLAlchemy 2 và PostgreSQL/Supabase.
Nguồn schema duy nhất: [supabase/schema.sql](../../backend/supabase/schema.sql), gồm 19 bảng.
ORM khớp cột, kiểu, nullable, server default, FK, unique và index. CHECK, trigger và RLS do SQL quản lý; không dùng create_all() để khởi tạo DB.

LangGraph is the sole workflow orchestrator for HTTP and Python callers. See [workflow architecture](../ai/GRAPH_WORKFLOW.md). Agents, Engine and Validator use mock fixtures; Constraint Planner is deterministic. WorkflowPersistence stores business artifacts, UI projections and a JSON GraphRun snapshot for restart/resume. Native LangGraph checkpointers/PostgresSaver and automatic transient retries are not implemented.

## Cài đặt và cấu hình

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ../shared -e ../ai -e '.[test]'
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Nếu chưa có .env thì copy .env.example, không ghi đè cấu hình hiện có. Bổ sung DATABASE_URL, SUPABASE_URL và SUPABASE_PUBLISHABLE_KEY. Publishable key hoặc legacy anon key dùng để gọi Supabase Auth /auth/v1/user và xác minh bearer access token, không thay thế quyền DB của DATABASE_URL. Không dùng service role API key để xác minh token.

Dependency get_current_user_id lấy UUID từ phản hồi Auth đã xác minh, không tin sub của JWT chưa xác minh và không nhận user_id từ body. Có thể override dependency này trong test.

## API

Swagger: http://127.0.0.1:8000/docs.

| Route | Mục đích |
| --- | --- |
| GET /api/v1/health | Liveness, không kiểm tra DB |
| POST /api/v1/dev/workflows/mock-run | Demo offline, không ghi DB, không yêu cầu token |
| POST /api/v1/trips | Tạo trip; body chỉ có title |
| GET /api/v1/trips/{trip_id} | Đọc trip của mình |
| POST /api/v1/trips/{trip_id}/requests | Tạo request cho trip của mình |
| GET /api/v1/requests/{request_id} | Đọc trạng thái UI |
| GET /api/v1/requests/{request_id}/artifacts/{artifact_type} | Đọc artifact latest |
| POST /api/v1/requests/{request_id}/mock-run | Chạy mock và lưu kết quả |

Mọi API persistence yêu cầu Authorization: Bearer <Supabase access token>. ID không tồn tại hoặc thuộc người khác đều trả 404. Body không được chứa user_id.

Luồng: tạo trip → tạo request → mock-run với body chứa trip_request và answer_raw tùy chọn. Khi clarifying/awaiting_relaxation, gửi TripRequest đã sửa cùng answer_raw để tiếp tục. Request completed/failed không chạy lại; tạo request mới. Chưa có CRUD API cho toàn bộ 19 bảng hoặc endpoint chọn relaxation riêng.

## Persistence và thay đổi tương thích

- WorkflowState chỉ giữ UUID, tham chiếu artifact, trạng thái, bước/field và bộ đếm. pending_questions, answers_history, attempts, errors chuyển ra WorkflowRun và lưu vào pending_items, clarification_rounds, solver_attempts, workflow_errors.
- workflow_requests stores the UI projection and graph_snapshot used for restart/resume; it has no legacy state/revision columns. Artifact payload là object có schema_version; candidates dùng envelope PlaceCandidates.
- Repository luôn nhận user_id đã xác minh và kiểm tra trips.user_id, kể cả kết nối bypass RLS. Khóa request tuần tự hóa writer; SQL trigger chuyển latest, partial unique index bảo vệ một latest mỗi loại. Repository không tự commit.
- Artifact và projection của một node được ghi trong savepoint. Một HTTP mock-run dùng một transaction; UI thấy cập nhật sau commit, chưa có streaming từng node. Lỗi DB rollback transaction.
- Itinerary/validation row dùng cùng UUID với artifact tương ứng để solver_attempts tham chiếu đúng bảng kết quả. places/cache dùng chung; điểm và giá theo request nằm ở request_place_candidates.
- ID trip/request/artifact/itinerary/validation là UUID; place/location IDs vẫn TEXT. trip_id khác request_id. JSON biểu diễn UUID bằng chuỗi chuẩn.
- score_places là StrictInt 0..100, từ chối float kể cả 92.0; admission_price_raw là chuỗi nullable. Itinerary bắt buộc price_status tại summary/ngày/hoạt động, không có mặc định contract. UNKNOWN yêu cầu cost=null; VERIFIED_FREE yêu cầu 0..0; ESTIMATED yêu cầu min>0 và max>=min. Repository không suy provenance từ giá 0.
- Relaxation suggestion yêu cầu constraint_type, description, payload. WorkflowError dùng enum SQL; mã chẩn đoán cũ giữ trong message. Contract kiểm tra tọa độ PlanningPlace và nhất quán status/solver_status.

## Database và migration

Không chạy alembic upgrade head: revision 0001 là schema cũ, giữ nguyên để bảo toàn lịch sử. Chưa có migration dữ liệu cũ. Xem [supabase/README.md](../../backend/supabase/README.md) để khởi tạo schema và xử lý dữ liệu cũ.

Không sửa .env và không áp dụng SQL lên database thật trong đợt này. Production nên dùng role runtime không phải admin với grants/policy phù hợp backend. Auth token chưa được SET thành DB JWT context trong SQLAlchemy.

## Test

```powershell
.\.venv\Scripts\python.exe -m pytest -m "not postgres" -q -rs -p no:cacheprovider --basetemp=.tmp-langgraph-tests
```

Integration chỉ đọc TEST_DATABASE_URL, không fallback DATABASE_URL hoặc .env. Host phải local, tên DB chứa test, public rỗng và chưa có auth schema. Test dựng scaffold Supabase local rồi thực thi nguyên văn schema.sql; không chạy Alembic. Dữ liệu test được giữ để kiểm tra, không tự xóa. Tạo DB disposable mới trước mỗi lần chạy.

```powershell
$env:TEST_DATABASE_URL = 'postgresql+psycopg://postgres@127.0.0.1:55432/travel_test'
.\.venv\Scripts\python.exe -m pytest -q -rs
Remove-Item Env:TEST_DATABASE_URL
```

Kiểm thử local PostgreSQL 17 gồm metadata 19 bảng, FK/index/default/nullable, versioning/latest đồng thời, rollback, bất biến, owner isolation, RLS, resume, replan và API persistence. Token được test bằng mock Auth; chưa gọi Supabase thật.
