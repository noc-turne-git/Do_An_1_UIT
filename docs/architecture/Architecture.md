# Bản đồ kiến trúc và điều hướng code

Tài liệu này chỉ ra nơi bắt đầu điều tra và ranh giới trách nhiệm hiện tại. Đọc hàm liên quan và caller trực tiếp trước khi mở rộng phạm vi. Chi tiết chính sách nằm trong các tài liệu liên kết ở cuối.

## Entry point và luồng chính

| Đường vào | Bắt đầu đọc | Vai trò |
| --- | --- | --- |
| Giao diện | `frontend/src/main.tsx`, `frontend/src/app/App.tsx`, `frontend/src/app/routes.tsx` | Khởi tạo React, providers và route; trang ghép các feature. |
| Chat | `backend/app/api/chat.py:send_message`, `ai/interface.py:run_turn` | Nhận lượt hội thoại, dựng ngữ cảnh và gọi graph; parser trích xuất đầu vào cho graph. |
| Mock có lưu DB | `backend/app/api/workflows.py:persist_mock_run`, `backend/app/services/workflow_factory.py:get_graph_orchestrator` | Kiểm tra request/resume, nạp snapshot và gắn `WorkflowPersistence` trước khi chạy. |
| Mock một lượt, trong bộ nhớ | `backend/app/api/dev_workflows.py:mock_run` | Gọi `LangGraphOrchestrator.run`; không lưu workflow vào DB. |
| Python nội bộ | `ai/interface.py:build_orchestrator`, `ai/orchestration/graph_workflow.py:LangGraphOrchestrator.run_turn` | Lắp component theo cấu hình và chạy một lượt. `run` là adapter tương thích. |

Luồng thực thi: đầu vào có cấu trúc hoặc văn bản qua `ai/interface.py:run_turn` → `LangGraphOrchestrator.run_turn` → các node LangGraph trong `graph_workflow.py` → kiểm tra output theo `shared/contracts.py` → artifact và trạng thái mới → `WorkflowPersistence.sync/save_graph` nếu có DB. Thứ tự thông thường là Parser → Destination → Constraint Planner → Places → Budget → Planning Input Builder → Engine → Validator → Explainer. `_route` có thể quay về bước trước hoặc dừng chờ người dùng theo kết quả domain. Đường dev chỉ dùng mock component; Engine và Validator mock không thực hiện tối ưu hay kiểm định nghiệp vụ đầy đủ.

## Trách nhiệm và quyền cập nhật

| Module | Trách nhiệm cần theo dõi |
| --- | --- |
| `shared/contracts.py` | Hợp đồng `TripRequest`, `WorkflowState`, câu hỏi, câu trả lời, episode và provenance. `TripRequest.clear_declined_values`, `daily_days` và `RequestMeta.normalize_decisions` còn chuẩn hóa dữ liệu cũ, suy ra collection state, `missing_fields` và `parser_status` khi validate. |
| `ai/orchestration/request_parser.py` | Trích xuất lượt văn bản thành bản nháp `TripRequest`; không sở hữu lịch sử câu trả lời, bộ đếm hay quyết định route. |
| `ai/orchestration/graph_workflow.py` | `GraphRun`, lập lịch qua `_route`, invalidation, kiểm tra/lưu output tại `_node` và `_save`, xử lý kết quả tại `_outcome`, vòng đời lượt và resume tại `run_turn/_execute`. |
| `ai/orchestration/workflow_state.py` | `WorkflowRun`, `StateMachine.update/fail/issue_question/clarify`: validate transition, tạo checkpoint, quản lý trạng thái câu hỏi và giới hạn lượt hỏi. |
| `backend/app/services/persistence.py` | `WorkflowPersistence`: giao dịch phát/nhận câu hỏi, artifact, projection, đối chiếu canonical DB với graph, JSON `GraphRun` snapshot và nạp lại. `backend/app/repositories/clarifications.py` giữ dữ liệu episode/câu hỏi/câu trả lời; `backend/app/repositories/workflows.py` giữ request projection. |

`TripRequest` không có một nơi ghi duy nhất: parser tạo đầu vào; `clarification_answers.accept_answer`, `trip_request_defaults.apply_trip_defaults`, `destination_resolution.apply_resolved_destination` và `turns.seed_after_failed` tạo bản cập nhật theo từng tình huống; graph quyết định khi nào áp dụng và lưu artifact; validators trong contract chuẩn hóa/kiểm tra khi `model_validate`. Khi điều tra giá trị bị đổi, bắt đầu từ nguồn cập nhật phù hợp rồi theo `meta.field_sources`, `field_decisions`, selection provenance và artifact ID. Không suy nguồn từ giá trị đơn lẻ.

Trạng thái cũng có ba ranh giới cần đọc cùng nhau: graph quyết định route, invalidation và bộ đếm thực thi; `StateMachine` kiểm tra và ghi transition/checkpoint; Persistence đối chiếu và ghi canonical episode/câu hỏi/câu trả lời, projection, artifact và snapshot. `save_graph/load_graph` dùng JSON application snapshot, không phải LangGraph checkpointer. Resume phải giữ identity của câu hỏi/episode, lịch sử, giới hạn lượt, tham chiếu artifact và tương thích snapshot cũ. Không di chuyển các trách nhiệm này chỉ để gom file.

## Bắt đầu điều tra theo triệu chứng

| Vấn đề | File/hàm đọc trước |
| --- | --- |
| Giá trị `TripRequest`, `missing_fields` hoặc nguồn dữ liệu sai | `shared/contracts.py:TripRequest.clear_declined_values/daily_days/should_ask`, `RequestMeta.normalize_decisions`; sau đó hàm tạo cập nhật tương ứng ở bảng trên. |
| Câu hỏi lặp, answer sai hoặc hết lượt hỏi | `ai/orchestration/workflow_state.py:StateMachine.issue_question/clarify`, `ai/orchestration/clarification_answers.py:accept_answer`; nếu có DB, `WorkflowPersistence.issue_question` và `ClarificationRepository.issue/answer`. |
| Route, replan, invalidation hoặc retry sai | `ai/orchestration/graph_workflow.py:LangGraphOrchestrator._route/_node/_invalidate/_outcome`. |
| Resume, snapshot hoặc artifact lệch DB | `backend/app/services/persistence.py:WorkflowPersistence.load_graph/save_graph/_validate_canonical/sync`; sau đó `graph_workflow.py:LangGraphOrchestrator.run_turn/_execute` và repository liên quan. |
| Chat và mock-run khác nhau | `backend/app/api/chat.py:send_message`, `backend/app/api/workflows.py:persist_mock_run`, `backend/app/api/dev_workflows.py:mock_run`, `ai/interface.py:run_turn/build_orchestrator`. |
| UI, route hoặc dữ liệu frontend | `frontend/src/app/routes.tsx`, trang tại `frontend/src/pages/`, feature tại `frontend/src/features/`, `frontend/src/services/api/client.ts`. |

Với lỗi theo một run cụ thể, dùng quy trình trace trong `AGENTS.md` trước khi đọc log thô.

## Phần frontend còn áp dụng

Frontend dùng React, TypeScript, Vite, React Router, TanStack Query và Zustand. `app/` giữ router/providers; `pages/` ghép feature; `features/` giữ UI và nghiệp vụ theo domain; `components/` và `hooks/` ở gốc dành cho phần dùng chung; `services/api/` là HTTP client. Giữ trạng thái UI cục bộ ở component, dữ liệu server trong TanStack Query và trạng thái client chia sẻ trong store khi cần. Feature gọi API qua service/hook; phần dùng chung không phụ thuộc ngược vào page/feature. Đây là nguyên tắc điều hướng, không phải bảo đảm mọi file hiện tại đều tuân thủ.

## Tài liệu chi tiết

- [GRAPH_WORKFLOW.md](../ai/GRAPH_WORKFLOW.md): route, invalidation, giới hạn, resume và trạng thái graph.
- [CLARIFICATION_POLICY.md](../ai/CLARIFICATION_POLICY.md): provenance, thẩm quyền chọn destination, bộ đếm, lifecycle và tương thích.
- [MOCK_WORKFLOW.md](../ai/MOCK_WORKFLOW.md): phạm vi mock và hai đường chạy demo.
- [PLANNING_CONTRACTS.md](../ai/PLANNING_CONTRACTS.md): contract lập kế hoạch; đọc lưu ý đầu tài liệu về phần mô tả cũ.
- [Backend_ERD.md](Backend_ERD.md), [README.md](../../backend/supabase/README.md): bảng dữ liệu và thiết lập persistence.
