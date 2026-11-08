# Canonical clarification policy — lifecycle B

Đây là nguồn thiết kế canonical cho contracts, persistence và orchestration.
Giữ tên selected_region, question, fields; không đổi tên theo ví dụ minh họa.

## Intent và quyền chọn

| selection_intent | Ý nghĩa | selection_authority |
| --- | --- | --- |
| EXPLICIT | User chỉ định điểm đến cụ thể | user |
| ANY_DESTINATION | User nói đâu cũng được | delegated khi có provenance user |
| DELEGATE_SELECTION | User yêu cầu hệ thống chọn giúp | delegated khi có provenance user |
| USER_UNKNOWN | User nói chưa biết chọn đâu | none |
| UNSPECIFIED | Chưa có bằng chứng ý định | none |

selection_mode (explicit/implicit/ambiguous) mô tả cách resolve địa danh,
không phải intent hoặc quyền ủy thác. implicit không suy ra ANY. Một candidate
duy nhất không cấp quyền chọn cho UNKNOWN/UNSPECIFIED. selection_provenance lưu
source, evidence user và question_id/episode_id nếu quyết định từ câu trả lời.
Legacy thiếu intent/authority dùng UNSPECIFIED/none, không suy ra từ city hay
field_sources. Giá trị cũ ANY/UNKNOWN vẫn đọc được; parser mới ghi
ANY_DESTINATION/DELEGATE_SELECTION/USER_UNKNOWN. User chọn option tạo EXPLICIT/user.
Default theo intent delegated giữ provenance; DestinationResult.selection_provenance
ghi default, không giả thành user chọn.
Destination.selection_provenance giữ bằng chứng user đã cấp delegation.

## Ba question kinds, phân loại theo mục đích

| kind | Mục đích | Budget |
| --- | --- | --- |
| trip_request | Hoàn thiện dữ liệu cơ bản để lập chuyến | clarification_round, tối đa 3 |
| destination_info | Thông tin resolve điểm đến hoặc xác nhận đổi constraint | destination_round, tối đa 2 trong episode |
| destination_choice | Chọn candidate trong snapshot options | Cùng budget destination |

Không suy kind từ field path hoặc chỉ từ selection_status. Budget có thể được hỏi
để hoàn thiện chuyến hoặc để phân biệt điểm đến. needs_more_info dùng structured
information_requests (purpose, fields, reason); no_valid_candidate dùng structured
recovery (reason, fields, constraint_proposal). Không route bằng prose trong
selection_reason hoặc placeholder destination.*. Không tự nới hard constraints.

Counter chỉ tăng khi question mới có identity được persist/issued thành công.
Retry cùng question_id và nội dung không tăng; cùng ID khác nội dung bị từ chối.
Agent A chạy lại không tiêu lượt hỏi. Slot duy nhất là (episode_id, counter_group,
round); kind chỉ mô tả mục đích. Một câu có thể gộp nhiều fields. Issuance và cập
nhật budget nằm trong cùng transaction.

Question lưu ID, episode, kind, status, intent/round snapshot, fields, toàn bộ
options (stable option/candidate ID, rank, reason), constraint proposal. Answer
liên kết đúng episode/question; option phải thuộc snapshot đã issued. Reject
stale, cross-episode và retry khác nội dung. Không dựng question từ pending_items
theo field. Question thứ hai đang open vẫn nhận câu trả lời khi counter bằng 2;
chỉ cấm phát câu thứ ba.

## Hết budget và final resolve

Sau câu trả lời cuối hoặc đóng question theo hành động tường minh của user, chạy
đúng một final resolve với dữ liệu mới. Persist operation ID và trạng thái
not_started → claimed → completed cùng result. Restart dùng lại completed result;
claimed không tự chạy lại nghiệp vụ, cần reconcile theo operation ID.

Chỉ ANY_DESTINATION (legacy ANY) với authority delegated
và bằng chứng user mới được default candidate
rank=1 sau final resolve completed, khi candidate vẫn hợp lệ. Rank không phải vị
trí array. UNKNOWN/UNSPECIFIED không default, kể cả chỉ còn một candidate; thiếu
lựa chọn/ủy quyền thì failed. Không có candidate hợp lệ thì failed. EXPLICIT chỉ
xác minh nơi user đã chỉ định, không thay bằng nơi khác.

DELEGATE_SELECTION đủ dữ liệu phải trả về selected, không phát destination_choice.
Nếu Agent A trả choice cho DELEGATE thì graph từ chối kết quả không hợp lệ; không
chọn tùy tiện từ danh sách. DELEGATE không chạy final resolve khi hết budget.
DestinationResult.selection_method do CODE ghi: USER_EXPLICIT / USER_CHOICE có
source=user; DELEGATED / ANY_DEFAULT có source=default. selection_mode không cấp
authority. Option response dùng AnswerHistory có identity và snapshot câu hỏi;
raw option ID không đủ để nhận lựa chọn. Parser-confirmed destination_update được
lưu trong answer và vẫn phải qua Agent A validate trước planning.

GraphRun.awaiting_final_resolve=true biểu thị operation claimed cần reconcile;
workflow giữ trạng thái planning. Retry chỉ đọc lại operation, không gọi provider.
Khi reconcile ghi completed result với cùng operation ID, graph dùng lại result.
WorkflowPersistence commit checkpoint claim trước provider và checkpoint result
trước selection/planning; caller phải dùng session cho phép các commit boundary.

TripRequest hết lượt chỉ áp defaults đã cấu hình: children=0, preferences theo
config; budget.amount giữ null nếu chưa biết. start_date/end_date, adults và city
explicit không default; declared_unknown không bỏ qua các field bắt buộc này.
Declared unknown ở field TripRequest khác destination được loại khỏi câu hỏi tiếp;
destination USER_UNKNOWN vẫn chưa resolved và không cấp quyền chọn. Parser chỉ
trích xuất lựa chọn explicit, Graph sở hữu answer history và counter của episode
không reset khi user đổi ý trong cùng episode.
end_date = start_date + duration_days - 1; ngày mơ hồ phải hỏi lại.

## Lifecycle B và compatibility

Failed luôn terminal. Explicit destination sau failed bắt buộc tạo request_id
mới VÀ episode_id mới, có thể giữ trip_id. Workflow cũ và lịch sử giữ nguyên.
Episode mới có destination_round=0, final resolve not_started; workflow mới có
clarification_round=retry_count=0.

Seed TripRequest mới bằng deep copy TripRequest mới nhất đã validate của workflow
cũ; giữ dữ liệu không thuộc destination và provenance của chúng. Thay toàn bộ
destination bằng input explicit mới có provenance user; xóa metadata destination
cũ, parser_status và missing_fields cache rồi validate lại. Không copy artifact
references, pending questions, answers hoặc final resolve. Persist TripRequest
thành artifact mới thuộc workflow mới trong cùng transaction.

Sau completed, thay đổi yêu cầu có thể resume cùng workflow theo invalidation;
nếu bắt đầu lựa chọn destination mới thì tạo episode mới, giữ lịch sử episode cũ.
Không reset counter trên chính episode cũ. Runtime này còn planned.

Snapshot cũ đọc được nhờ defaults. Thiếu question identity/episode hoặc thiếu
option candidate ID/rank/reason chỉ được đọc lịch sử, không nhận selection.
Migration không tự cấp delegation hay biến legacy thành actionable. Issuance mới
phải dùng budget đã biết, không reset budget legacy để tiếp tục hỏi.

Đề xuất thay hard constraint mang cả `current_values` và `proposed_values` trong
`constraint_proposal`; LLM chỉ diễn đạt câu hỏi. Draft sai kind, coverage, options
hoặc proposal dùng template từ snapshot CODE, không gọi LLM viết lại. Chỉ câu hỏi
đã persist thành công mới tiêu lượt.

## Mốc triển khai

| Mốc | Trạng thái |
| --- | --- |
| Commit 1 — implemented | Policy và tài liệu thống nhất; chưa thay runtime |
| Commit 2 — implemented | Contracts, invariants, serialization và JSON Schema |
| Commit 3 — implemented | Migration mới, atomic episode/question/answer storage, lifecycle factory, final-resolve persistence; kiểm chứng PostgreSQL riêng |
| Commit 8 — implemented | TripRequest defaults từ policy, sau khi câu hỏi cuối đã được xử lý |
| Commit 9 — implemented | Destination routing/authority, structured answers, final resolve durable, constraint consent |
| Planned | Chat UI integration và lifecycle tạo episode mới sau completed |

Ba commit nền tảng không có nghĩa clarification flow đã hoàn tất end-to-end.
Kết quả kiểm chứng và giới hạn migration cũ: [CLARIFICATION_VERIFICATION.md](CLARIFICATION_VERIFICATION.md).
