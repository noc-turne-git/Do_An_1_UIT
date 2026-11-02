# Travel Planning Backend

Orchestrator Skeleton và API Development/Mock đã được bổ sung. Xem [MOCK_WORKFLOW.md](MOCK_WORKFLOW.md) để chạy demo, kiểm thử, xem các trạng thái và giới hạn của fixtures. Các mô tả skeleton ban đầu bên dưới là bối cảnh giai đoạn trước.

Backend độc lập Python 3.11+ / FastAPI / Pydantic v2 / SQLAlchemy 2 / Alembic / PostgreSQL (psycopg 3). Có shared models, fixtures và Constraint Planner thuần Python. Chưa có Orchestrator, Agent thật, Planning Engine hoặc Validator. Không sửa Frontend, dependency npm hay Vite.

Quy tắc đã triển khai, cách gọi planner, fixtures và các điểm schema chưa rõ: [PLANNING_CONTRACTS.md](PLANNING_CONTRACTS.md). `tzdata` cung cấp dữ liệu múi giờ IANA cho Windows.

## Cài đặt và chạy bằng Windows PowerShell

Từ root repository:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.[test]'
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Không cần activate venv hay đổi ExecutionPolicy. Chỉ copy `.env` khi chưa có file cấu hình; không ghi đè file đang dùng. Mở http://127.0.0.1:8000/docs, gọi health:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health
```

Health trả `{"status":"ok"}` là liveness, không kiểm tra DB/LLM. API chạy khi không có DATABASE_URL. CORS mặc định cho localhost/127.0.0.1:5173; đặt CORS_ORIGINS bằng JSON array trong .env nếu Frontend dùng port khác. Backend không được kết nối vào Frontend trong phạm vi này.

## Cấu hình

`.env` được tìm theo thư mục backend, không phụ thuộc working directory. Environment variables ưu tiên hơn `.env`. Xem `.env.example` cho APP_NAME, LOG_LEVEL, CORS_ORIGINS, DATABASE_URL, LLM_PROVIDER, LLM_MODEL, LLM_API_KEY, LLM_TIMEOUT_SECONDS. URL và key dùng SecretStr, không hardcode/log. `.env` và venv được gitignore riêng trong backend.

LLM mặc định mock; `create_llm_client` từ chối provider khác với lỗi rõ ràng. Mock trả fixture JSON qua Pydantic validation, không gọi mạng. LLMClient là Protocol thay thế được; adapter tương lai đọc cấu hình model/key/timeout, xử lý timeout và chuẩn hóa lỗi. Chưa tích hợp SDK provider.

## Database và migration

Tạo PostgreSQL database hoặc chọn Supabase database, điền DATABASE_URL vào `.env` bằng connection string của bạn. Ví dụ placeholder đã có trong `.env.example`; URL-encode password. Dùng `sslmode=require` khi kết nối Supabase. URL `postgresql://` được chuyển sang driver psycopg; không dùng SQLite thay PostgreSQL. Với migrations nên dùng direct connection hoặc session pooler phù hợp từ dự án Supabase của bạn.

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic current
.\.venv\Scripts\python.exe -m alembic check
```

Không tự tạo bảng khi startup. Session dependency mở transaction, commit khi thành công, rollback khi lỗi, luôn đóng session; engine đóng khi app shutdown. Engine tạo lazy, không có nghĩa đã kết nối thành công. Session đồng bộ: endpoint sử dụng DB nên là `def` để FastAPI chạy trong thread pool; không gọi blocking DB trong async event loop.

Migration đầu tạo trips/workflows/artifacts và trigger bất biến cho artifacts. ERD, quyết định lưu trữ và các điểm schema cần xác nhận: [Backend_ERD.md](../docs/Backend_ERD.md). Muốn tạo migration mới:

```powershell
.\.venv\Scripts\python.exe -m alembic revision --autogenerate -m 'describe change'
```

Offline SQL không kiểm chứng DB thật; có thể dùng URL placeholder chỉ cho lệnh `--sql`:

```powershell
$env:DATABASE_URL = 'postgresql+psycopg://placeholder:placeholder@localhost:5432/placeholder'
.\.venv\Scripts\python.exe -m alembic upgrade head --sql
Remove-Item Env:DATABASE_URL
```

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q -rs
```

Tests mặc định kiểm health/CORS, exception handling, config env/dotenv, secret masking, mock output, models/fixtures và Constraint Planner (nguồn giá trị, defaults, hard/soft, thiếu dữ liệu, xung đột và biên). Connection test đọc TEST_DATABASE_URL hoặc DATABASE_URL từ **environment của tiến trình**; không tự dùng `.env` để tránh kết nối ngoài ý muốn. Nếu không có URL sẽ skip.

Để kiểm migration, tạo database test **riêng, rỗng và có thể hủy** rồi đặt:

```powershell
$env:TEST_DATABASE_URL = 'postgresql+psycopg://USER:PASSWORD@localhost:5432/travel_test'
.\.venv\Scripts\python.exe -m pytest -m postgres -q -rs
Remove-Item Env:TEST_DATABASE_URL
```

Migration test từ chối database có bảng; chạy upgrade, kiểm bảng/insert/trigger và Alembic metadata check, rồi downgrade base và xóa bảng alembic_version do chính test tạo để có thể chạy lại. Không chạy trên database thật/production. URL đã cấu hình nhưng kết nối lỗi là test fail, không skip. Nếu chưa chạy thành công các test PostgreSQL thì chưa xác nhận kết nối, FK, JSONB, trigger hay migration hoạt động trên server thật.

Kết quả kiểm thử skeleton trước khi mở rộng: **8 passed, 2 skipped**. Kết quả bộ models/planner được ghi trong PLANNING_CONTRACTS.md. PostgreSQL tests cần DATABASE_URL/TEST_DATABASE_URL; chưa kiểm thử trên server khi thiếu cấu hình. Bộ dependencies đã cài phát cảnh báo Starlette về việc TestClient dùng httpx; chưa chuyển sang httpx2 trong phạm vi này.

## Cấu trúc và file được tạo

```text
backend/
  pyproject.toml, .env.example, .gitignore, README.md, alembic.ini
  app/
    main.py                    # app factory, lifespan, CORS, logging, errors
    api/health.py              # GET /api/v1/health
    core/config.py, errors.py  # environment settings, shared errors
    models/contracts.py       # shared Pydantic contracts and WorkflowState data
    agents/interfaces.py      # 9 async Protocols, no agent implementations
    services/llm.py           # LLM abstraction + deterministic mock
    db/base.py, models.py, session.py
    repositories/artifacts.py # append-only artifact API
  alembic/env.py, script.py.mako, versions/0001_initial.py
  fixtures/trip_request.json
  tests/test_basic.py, test_database.py
docs/Backend_ERD.md
```

Các thư mục app và module có `__init__.py`. Không có endpoint lập lịch trình hay thuật toán tối ưu ở giai đoạn này. Database schema là đề xuất tối thiểu; schema nghiệp vụ còn điểm cần xác nhận trong ERD trước triển khai Agent thật.
