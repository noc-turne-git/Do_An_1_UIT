# Travelio monorepo

React + TypeScript frontend, FastAPI + Supabase backend và package Python AI độc lập. Backend gọi AI trực tiếp qua `ai.interface`; chưa có AI HTTP service.

## Cấu trúc

```text
frontend/                  React, public, tests, package.json và config FE
backend/
  app/{api,core,db,models,repositories,services}/
  alembic/, supabase/, tests/, pyproject.toml
ai/
  agents/                  runtime, adapters, tools, skills, LLM
  orchestration/           Request Parser, LangGraph Supervisor, workflow state
  planning/                Constraint Planner và các solver placeholder có sẵn
  schemas/, prompts/, logs/, tests/, interface.py, pyproject.toml
shared/
  schemas/                 JSON Schema public
  samples/                 dữ liệu mẫu dùng chung
  contracts.py             một bộ Pydantic contract dùng chung
  validation.py, pyproject.toml
docs/{architecture,api,ai}/
.github/workflows/ci.yml
README.md, .gitignore, .env.example, package.json, pytest.ini
```

## Cài đặt

Yêu cầu Node.js 22.12+ và Python 3.11+ (CI dùng Python 3.13). Chạy tại root:

```powershell
npm --prefix frontend ci
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ./shared -e './ai[test]' -e './backend[test]'
```

Linux/macOS dùng `source .venv/bin/activate`. Có thể dùng lại `backend/.venv` hiện có thay vì tạo môi trường mới. Cài đồng thời các package local để pip không tìm AI/shared trên PyPI.

## Environment

Không ghi đè file environment đang có. Với cài đặt mới, sao chép file `.env.example` ở root thành `.env.local` tại root để cấu hình frontend; sao chép `backend/.env.example` thành `backend/.env` để cấu hình backend. Mỗi phần có một file mẫu riêng; frontend không cần các biến database hoặc LLM của backend.

- Frontend đọc root `.env.local` qua `envDir` trong `frontend/vite.config.ts`: `VITE_SUPABASE_URL`, `VITE_SUPABASE_PUBLISHABLE_KEY`, `VITE_API_BASE_URL`.
- Backend đọc `backend/.env` theo đường dẫn tuyệt đối, không phụ thuộc working directory: `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, CORS và các cấu hình AI.
- Chat LLM thật: `LLM_PROVIDER=openai`, `OPENAI_API_KEY`, `OPENAI_MODEL`; `OPENAI_BASE_URL` tùy chọn. Không dùng service role key để xác thực access token của người dùng.
- `AI_LOG_FILE=logs/execution.jsonl` là đường dẫn tương đối với `ai/`. `LOG_MAX_BYTES`, `LOG_BACKUP_COUNT` điều khiển rotation. `LOG_FILE` cũ không còn tạo file Backend.

Chạy AI độc lập: truyền `AISettings(...)` trực tiếp hoặc đặt environment variables; package AI không tự đọc `.env` của Backend.

## Chạy

Hai terminal tại root, đã activate Python environment:

```powershell
python -m uvicorn app.main:app --app-dir backend --reload --host 127.0.0.1 --port 8001
npm run dev
```

Frontend: http://localhost:5173. API docs: http://127.0.0.1:8001/docs. Vite proxy `/api` sang Backend ở cổng 8001 (tránh cổng 8000 đang được IIS sử dụng). Production đặt `VITE_API_BASE_URL` khi build và cấu hình CORS tương ứng.

AI demo độc lập, không cần FastAPI hoặc database:

```powershell
python -m ai.agents.runtime.demo
```

API, authentication, conversation history và persistence vẫn do Backend quản lý. Chat thu thập yêu cầu qua LLM rồi cập nhật TripRequest; trạng thái ready chưa tự tạo Trip. Workflow tiếp tục qua LangGraph, agents, Planner, Validator và itinerary như trước. Schema database và migration không thay đổi trong refactor này; không tự chạy migration trên database đang có dữ liệu. Xem `backend/supabase/README.md` trước khi thiết lập database.

## Kiểm thử

```powershell
npm run build
npm test
python -m pytest backend/tests -q
python -m pytest ai/tests -q
python -m pytest -q
python -m shared.export_schemas
```

Các test PostgreSQL chỉ chạy khi `TEST_DATABASE_URL` trỏ tới database local rỗng dùng riêng cho test, tên có chữ `test`. Nếu không có biến này, test được skip. Các test auth/LLM thông thường dùng mock; không gọi Supabase/OpenAI thật. CI build FE, chạy test hai phía, kiểm tra schema drift và build wheel cho ba package.

Contract wire nằm trong `shared/schemas/`; `shared/contracts.py` là nguồn Python duy nhất để sinh schema. TripRequest được kiểm tra JSON Schema ở interface AI và đầu vào graph, đồng thời giữ các validator Pydantic về ngày và business invariants. Model API và model runtime AI nội bộ nằm ở component tương ứng.

## Logging và giới hạn hiện tại

Backend chỉ ghi console. AI ghi JSONL trong `ai/logs/` gồm run ID, trip ID (null trước khi tạo Trip), UTC timestamp, bước, trạng thái kết quả và mã lỗi. Log không ghi raw prompt/message/output hoặc exception message của provider; các field nhạy cảm được mask. Log cũ được giữ ở `ai/logs/legacy/` và không đưa lên Git.

Các production agent/solver còn trống từ repo gốc vẫn là placeholder; Planning Engine và Validator của demo vẫn dùng fixture, Constraint Planner là deterministic implementation. Refactor giữ nguyên business behavior, không bổ sung thuật toán ngoài phạm vi.

Chi tiết audit, dependency và danh sách nhóm file di chuyển: [MONOREPO_AUDIT](docs/architecture/MONOREPO_AUDIT.md). Tài liệu [Chat API](docs/api/CHAT_API.md), [Backend](docs/api/BACKEND.md), [LangGraph](docs/ai/GRAPH_WORKFLOW.md), [Planning contracts](docs/ai/PLANNING_CONTRACTS.md).
