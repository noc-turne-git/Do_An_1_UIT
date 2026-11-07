# Schema Supabase cho hệ thống lập lịch trình

`schema.sql` là baseline cho **database Supabase mới**, chạy một lần bằng SQL Editor với quyền database owner. Giữ nguyên SQL và migrations đã commit. Baseline hiện đã chứa conversations; không chạy lại migration conversations trên baseline này. Chạy tiếp `20261107_clarification_round_kinds.sql`, rồi `20261107_canonical_episodes.sql` theo đúng thứ tự phụ thuộc (không sort tên file). Schema hiện có 23 bảng nghiệp vụ.

Đây là lựa chọn **DDL SQL** trong yêu cầu, không phải migration nâng cấp schema hiện tại. Không chạy lên database đã có bảng `trips` của Alembic `0001`. Model và repository đã đồng bộ schema mới; dữ liệu cũ vẫn cần chuyển đổi riêng. Script chưa được áp dụng lên Supabase.

Thứ tự phụ thuộc: profiles → trips → messages → workflow_requests → workflow_artifacts/clarification_rounds/pending_items/workflow_errors → places → travel_time_cache/request_place_candidates → itineraries → itinerary_days → itinerary_activities/itinerary_dropped_places/relaxation_suggestions → validation_results → validation_issues → solver_attempts. FK bổ sung của parent artifact được thêm sau khi tạo bảng.

## Quyền truy cập

| Bảng | Client authenticated | Backend service_role |
| --- | --- | --- |
| profiles | Đọc, sửa profile của mình; tạo tự động bằng trigger | CRUD |
| trips, messages | CRUD trong chuyến của mình | CRUD |
| workflow_requests và toàn bộ bảng thuộc request | Đọc thông qua trips.user_id | Ghi dữ liệu workflow, artifact và kết quả |
| places, travel_time_cache | Đọc, kể cả anon | CRUD |

Mỗi bảng được bật RLS và cấp quyền tường minh. Không cấp client quyền ghi trạng thái solver, kết quả Validator hoặc artifact. Client gửi câu trả lời và lựa chọn relaxation tới backend; backend xác thực chủ sở hữu trước khi ghi bằng service role vì key này bypass RLS. Không đưa service role key vào ứng dụng client.

Trigger profile dùng `SECURITY DEFINER`, search_path rỗng và tên bảng đầy đủ. Có backfill profile cho auth.users đã tồn tại. Profile mới lấy tên/ảnh từ user metadata; preferences mặc định `{}`. Khi dùng preference để điền TripRequest, backend ghi `source = 'default'` trong payload; SQL không tự suy luận nguồn.

## Bất biến và versioning

- `workflow_artifacts` chặn sửa payload và xóa trực tiếp, kể cả service role. Ngoại lệ duy nhất là chuyển `is_latest` từ true sang false. Nếu cần bất biến tuyệt đối từng byte, phải chuyển con trỏ latest sang bảng riêng, khác cấu trúc được yêu cầu.
- Khi insert bản latest mới, truyền `parent_artifact_id` là artifact latest hiện tại. Trigger khóa request bằng `FOR UPDATE`, hạ cờ latest cũ, rồi insert bản mới trong cùng transaction. Partial unique index bảo đảm tối đa một latest cho từng loại trong request. Parent bắt buộc cùng request và loại artifact.
- Itinerary, day, activity, dropped place, validation result và issue chặn UPDATE/DELETE trực tiếp. Bản thay thế dùng ID mới; parent_artifact_id của itinerary/validation_results trỏ đến artifact phiên bản trước cùng loại. Backend ghi artifact và toàn bộ projection con trong cùng transaction. SQL chưa khóa việc bổ sung dòng con sau khi công bố kết quả; backend phải thực hiện quy tắc hoàn tất snapshot này.
- Xóa request/trip/profile vẫn cascade cả kết quả theo yêu cầu. Trigger cho phép xóa kết quả khi request cha đã bị xóa. Không hỗ trợ xóa riêng artifact hay itinerary.
- Các bảng con đều có request_id, index và FK ON DELETE CASCADE. FK ghép bảo đảm request_id của con khớp itinerary/day/validation cha. Các dòng con chuẩn hóa dùng schema_version của kết quả cha; các artifact/kết quả độc lập có schema_version riêng.

## Giả định và phạm vi

- PlanningInput nằm trong `workflow_artifacts.payload`, loại `planning_input`. LangGraph is the sole orchestrator. Application restart/resume uses `workflow_requests.graph_snapshot` through WorkflowPersistence. Native LangGraph checkpointers/PostgresSaver are not configured; see [workflow architecture](../GRAPH_WORKFLOW.md).
- `price_status` giữ đúng contract hiện có: ESTIMATED, UNKNOWN, VERIFIED_FREE. `request_type` gồm EXPLICIT, IMPLICIT, AMBIGUOUS, INSUFFICIENT; hiện nằm trong JSONB destination_result nên enum được khai báo để dùng khi chuẩn hóa sau này.
- UNKNOWN yêu cầu cả hai giá NULL. VERIFIED_FREE yêu cầu cả hai bằng 0. ESTIMATED yêu cầu giá dương và min ≤ max. Thêm price_status vào itinerary/day/activity để thực thi quy tắc giá bằng 0. Không tự điền chi phí chưa biết bằng 0. Tiền dạng cột là BIGINT VND; JSONB price được kiểm tra dạng số nguyên không âm và currency VND.
- candidate_status giữ TEXT nullable vì chưa có danh sách giá trị hợp lệ; không tự sáng tác enum. category, business_status, transport_mode, source, solver_status và constraint_type cũng chưa có bộ giá trị cố định.
- travel_time_cache chỉ được nhắc tên, chưa có danh sách cột: bổ sung cấu trúc MVP có cặp place có hướng, transport_mode, departure_bucket TIMESTAMPTZ, duration_minutes INT, distance_meters INT, source, expiry và schema_version. Backend quyết định kích thước bucket và TTL.
- Bốn JSONB ở places giữ cấu trúc như yêu cầu. Shape chi tiết opening_hours, photos, visit_duration và payload artifact được kiểm tra bởi contract backend; DDL chỉ kiểm tra loại JSON cấp ngoài và tính hợp lệ giá. Không coi CHECK của SQL là thay thế Pydantic/Validator.
- checked_rules phải chứa đủ 14 tên quy tắc từ contract hiện tại khi is_valid=true. Kết quả không hợp lệ có thể ghi danh sách chưa đủ khi validator lỗi giữa chừng. Deferred constraint trigger chặn is_valid=true đi kèm issue loại violation. SQL không thực thi lại thuật toán Validator.
- TIME áp dụng hoạt động trong một ngày. Chuyến qua nửa đêm cần tách hoạt động/ngày; DATE thuộc múi giờ địa phương của chuyến. Các mốc tạo/cập nhật dùng TIMESTAMPTZ.
- Trigger updated_at áp dụng profiles, workflow_requests và places. Không tạo users riêng.

## Backend và quyền production

Backend kết nối SQLAlchemy trực tiếp qua DATABASE_URL; cấu hình hiện tại là postgres/admin, không phải service role API key. Admin có thể bỏ qua RLS. Mọi repository dữ liệu người dùng bắt buộc nhận user_id và kiểm tra trips.user_id cho đọc/ghi.

Production nên dùng role runtime **không phải admin**, được cấp quyền tối thiểu phù hợp backend. SQL hiện chỉ cho authenticated đọc output và service_role ghi output: role không bypass RLS cần grants/policy backend phù hợp, không chỉ đổi username. Không dùng tài khoản migration/owner cho ứng dụng. Access token được xác minh qua Auth để lấy user_id, chưa được SET vào JWT context của kết nối SQLAlchemy.

## Việc cần làm tay

1. Cài dependencies mới (httpx là dependency runtime).
2. Với database Supabase mới/rỗng: chạy schema.sql, sau đó `20261107_clarification_round_kinds.sql` và `20261107_canonical_episodes.sql`. Đăng ký/đăng nhập qua Supabase Auth để có profile; script backfill cho user đã tồn tại.
3. Bổ sung SUPABASE_URL và SUPABASE_PUBLISHABLE_KEY vào backend/.env. Dùng publishable/legacy anon key, không cần service role API key cho xác minh token. DATABASE_URL chỉ ở server.
4. Chuẩn bị role runtime không phải admin và kiểm tra grants/RLS phù hợp triển khai.
5. Nếu giữ dữ liệu cũ: backup, tạo DB đích mới, ánh xạ ID chuỗi → UUID, xác định chủ sở hữu từng trip, trích workflow/artifact và dựng parent/latest. Không tự gán owner hay ép chuỗi tùy ý thành UUID. Chưa có công cụ chuyển dữ liệu trong đợt này.

## Alembic

Alembic có hai branch tách biệt. `0001_initial.py` là legacy, được giữ nguyên để
audit lịch sử và **không** là parent của canonical schema. Canonical branch bắt
đầu tại `20261105_canonical_baseline`: revision này kiểm SHA-256 rồi chạy đúng
baseline `schema.sql`; migration tiếp theo chạy tuần tự trên branch `canonical`.

- Database mới có Supabase Auth scaffold: revision baseline cũ hiện có hash/header
  không khớp schema.sql đã commit. Không bỏ kiểm tra hash hoặc sửa migration cũ.
  Provision bằng baseline SQL trên database rỗng, kiểm chứng schema, rồi stamp
  `20261105_canonical_baseline` và `alembic upgrade canonical@head`.
  Nếu đã áp cả hai SQL migrations, kiểm chứng schema trước khi stamp head.
- Database canonical đã tồn tại ở đúng `schema.sql` nhưng **chưa** có migration
  mới: backup và kiểm chứng cột/constraint hiện hữu, rồi mới
  `alembic stamp 20261105_canonical_baseline` và
  `alembic upgrade canonical@head`. Nếu migration
  `20261107_clarification_round_kinds` đã được chạy thủ công và schema đã khớp
  head, stamp trực tiếp revision đó; không stamp baseline rồi chạy lại. Không
  có thao tác stamp tự động.
- Database đang ở legacy `0001`: không được stamp canonical hoặc chạy canonical
  upgrade. Cần một dự án chuyển dữ liệu riêng (owner/UUID/payload mapping) sau
  backup và đối soát; migration này không tự đoán mapping.

`20261105_canonical_baseline` không hỗ trợ downgrade vì rollback sẽ phá hủy
canonical schema. `20261107_clarification_round_kinds` chỉ downgrade khi chưa
có `destination_choice` history hoặc destination state không-default.

`20261107_canonical_episodes` chạy chính SQL migration Supabase, để hai đường
triển khai không lệch. Downgrade bị từ chối để giữ lịch sử canonical. Alembic env
dùng version_num varchar(128), vì revision đã commit trước đó vượt 32 ký tự.
Migration chỉ bổ sung schema; không tạo question identity hoặc delegation giả
cho legacy. Legacy counters được giữ khi explicit adoption tạo episode đầu tiên.

Repository `ClarificationRepository` cung cấp `start_episode`, `issue`, `answer`,
`close_episode`, `claim_final_resolve`, `complete_final_resolve` và
`new_workflow_after_failed`. Caller giữ transaction; các operation dùng savepoint
và lock workflow. Commit final-resolve claim **trước** khi gọi provider. Nếu nhận
acquired=False sau restart, reconcile theo operation ID hoặc dùng completed result;
không gọi lại provider như một resolve mới. Đây không phải bảo đảm exactly-once
cho external API khi provider chưa hỗ trợ idempotency/reconciliation.

Canonical sync/save_graph kiểm tra dữ liệu phải khớp relational records. Issuance
và answer cập nhật graph snapshot hiện hữu trong cùng transaction. Legacy sync còn
được giữ để runtime cũ hoạt động; nó không nâng question legacy thành actionable.
Orchestrator/parser/Chat chưa được chuyển sang API canonical trong ba commit này.

## Kiểm tra local

Đã thực thi nguyên văn schema.sql trên PostgreSQL 17 local tạm, có scaffold auth.users/auth.uid và roles Supabase dành riêng cho test. Đã kiểm tra metadata 19 bảng, FK/index/nullable/default, profile trigger, parent/latest, writer đồng thời, bất biến, rollback, cascade, owner isolation, RLS và API lưu/khôi phục/replan.

Integration chỉ dùng TEST_DATABASE_URL local, DB mới/rỗng/tên chứa test; không dùng .env hay DATABASE_URL. Không kiểm tra Supabase/Auth thật. Token được test bằng mock HTTP; cần kiểm thử token thật trên development trước triển khai.
